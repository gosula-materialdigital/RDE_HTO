"""
Maps RDE-structured heat-treatment metadata (meta/{process_id}_metadata.json)
to a BFO/PMD Core Ontology-style canonical JSON graph, ready for conversion
to RDF/TTL (e.g. via agnosticmapper).

Field-to-block mapping is data-driven wherever metadata-def.json declares
enough to drive it generically (global "denotes" fields, per-step
"class name"-typed quantities). The furnace equipment scaffolding and the
step-name -> process-type classification are fixed domain knowledge and
stay as explicit Python, the same way jsontocjson_tto.py keeps its own
equipment scaffolding hardcoded.
"""
import json
import re
from datetime import datetime


def _iso(dt_str):
    return f"{datetime.strptime(str(dt_str), '%d.%m.%Y %H:%M:%S').isoformat()}+02:00"


def create_identifier_and_value_blocks(class_name, key, process_id, val, denotes, denotesinstancename):
    """
    Returns a list of blocks representing the semantic chain for identifiers and values.
    """
    datum_block = {
        class_name: {
            "hasIdentifier": f"{process_id}_{key}",
            "label": f"{process_id}_{key}",
            "has value": val
        }}

    if denotes is not None:
        datum_block[class_name]["denotes"] = [{
            denotes: {
                "hasIdentifier": f"{process_id}_{denotesinstancename}",
                "label": f"{process_id}_{denotesinstancename}"
            }}]
    return [datum_block]


def create_scalar_value_spec_block(process_id, slug, numeric_value, unit_id, is_about_class=None, is_about_id=None):
    """
    Generic 'Specification Datum -> Scalar Value Specification' block for a
    per-step quantity. Slug/value/unit come from metadata-def.json's
    declared type+unit for the field (mirrors jsontocjson_tto.py's
    create_quality_blocks, which dispatches on metadata-def.json annotations
    instead of one hardcoded block per named field).
    """
    scalar = {
        "hasIdentifier": f"{process_id}_{slug}_valuespecification",
        "label": f"{process_id}_{slug}_valuespecification",
        "has measurement unit label": [{
            "Measurement Unit Label": {"hasIdentifier": unit_id, "label": unit_id}
        }],
        "has specified numeric value": numeric_value,
    }
    datum = {
        "hasIdentifier": f"{process_id}_{slug}",
        "label": f"{process_id}_{slug}",
        "has value specification": [{"Scalar Value Specification": scalar}]
    }
    if is_about_class:
        datum["is about"] = [{is_about_class: {"hasIdentifier": is_about_id, "label": is_about_id}}]
    return {"Specification Datum": datum}


def create_time_duration_block(process_id, slug, minutes, unit_id, temporal_region_id):
    """Generic 'Specification Datum -> Time Duration' block (a distinct
    shape from Scalar Value Specification, dispatched by metadata-def.json's
    declared 'class name': 'Time Duration')."""
    return {
        "Specification Datum": {
            "hasIdentifier": f"{process_id}_{slug}",
            "label": f"{process_id}_{slug}",
            "has value specification": [{
                "Time Duration": {
                    "hasIdentifier": f"{process_id}_{slug}_valuespecification",
                    "label": f"{process_id}_{slug}_valuespecification",
                    "minutes": minutes,
                    "temporal unit type": unit_id
                }
            }],
            "is about": [{"Temporal Region": {"hasIdentifier": temporal_region_id, "label": temporal_region_id}}]
        }
    }


# Per-step quantity leaves -> the fixed slug used in existing identifiers,
# and (for Scalar Value Specification leaves) which class + chamber-derived
# suffix the value "is about". Chamber is resolved per-step at runtime (the
# same physical parameter can belong to the Heating Chamber or Quenching
# Chamber depending on which step it occurs on), so it can't be a static
# metadata-def.json annotation -- everything else about these blocks
# (whether the leaf exists for this step, its type, and its unit) comes
# straight from metadata-def.json.
STEP_LEAF_SLUGS = {
    "endafter[min]": "durationsetting",
    "setpoint_temperatur[°c]": "targettemperature",
    "setpoint_vak_heizung[mbar]": "targetvacuumpressure",
    "setpoint_öltemp[°c]": "targetoiltemperature",
    "setpoint_zt_in_öl[s]": "targettimeinoil",
}
STEP_LEAF_IS_ABOUT = {
    "setpoint_temperatur[°c]": ("Temperature", "temperature"),
    "setpoint_vak_heizung[mbar]": ("Pressure", "vacuumpressure"),
    "setpoint_öltemp[°c]": ("Temperature", "quenchingoil_temperature"),
}


def transform_json_to_canonical(metadata_json_path, metadata_def_json_path, output_json_path):
    """
    Reads one charge's RDE metadata record (metadata_json_path) plus the
    schema that produced it (metadata_def_json_path), and writes the
    ontology-mapped canonical JSON graph to output_json_path.
    """
    with open(metadata_json_path, 'r', encoding='utf-8') as f:
        full = json.load(f)
    data = full['constant']
    variable = full.get('variable', [])
    with open(metadata_def_json_path, 'r', encoding='utf-8') as f:
        metadata_def = json.load(f)

    def value_of(key):
        entry = data.get(key)
        return entry['value'] if entry else None

    def step_value_of(i, leaf):
        if i - 1 >= len(variable):
            return None
        entry = variable[i - 1].get(f"step_{leaf}")
        return entry['value'] if entry else None

    process_id = str(value_of('process_id'))
    numberofsteps = int(value_of('numberofsteps'))

    canonical_list = []

    # --- Fixed structural scaffolding: same shape for every charge, only
    # the process_id-based identifiers change. Not driven by metadata-def.json.
    canonical_list.append({
        "Quenching And Tempering": {
            "hasIdentifier": f"{process_id}_quenchingandtempering",
            "label": f"{process_id}_quenchingandtempering",
            "starts with": [{"Process": {"hasIdentifier": f"{process_id}_step_1", "label": f"{process_id}_step_1"}}],
            "ends with": [{"Process": {"hasIdentifier": f"{process_id}_step_{numberofsteps}", "label": f"{process_id}_step_{numberofsteps}"}}],
            "has participant": [{"Furnace": {"hasIdentifier": f"{process_id}_furnace", "label": f"{process_id}_furnace"}},
                                 {"Device": {"hasIdentifier": f"{process_id}_measurementdevice", "label": f"{process_id}_measurementdevice"}},
                                 ],
            "has specified input": [{"Object": {"hasIdentifier": f"{process_id}_testpiece", "label": f"{process_id}_testpiece"}}],
            "realizes": [
                {"Test Piece Role": {"hasIdentifier": f"{process_id}_testpiecerole", "label": f"{process_id}_testpiecerole"}},
                {"Austenitizing Point": {"hasIdentifier": f"{process_id}_austenitizingpoint", "label": f"{process_id}_austenitizingpoint"}},
                {"Measuring Function": {"hasIdentifier": f"{process_id}_measuringdevicefunction", "label": f"{process_id}_measuringdevicefunction"}},
                {"Device Role": {"hasIdentifier": f"{process_id}_devicerole", "label": f"{process_id}_devicerole"}},
                {"Device Role": {"hasIdentifier": f"{process_id}_measuringdevicerole", "label": f"{process_id}_measuringdevicerole"}},
                {"Plan": {"hasIdentifier": f"{process_id}_qtplan", "label": f"{process_id}_qtplan"}},
            ],
            "exists at": [{"Temporal Region": {"hasIdentifier": f"{process_id}_temporalregion", "label": f"{process_id}_temporalregion"}}],
            "has specified output": [{"File Data Item": {"hasIdentifier": f"{process_id}_filedataitem", "label": f"{process_id}_filedataitem"}}]
        }
    })

    # --- Generic dispatch for global identifier-type fields (like
    # jsontocjson_tto.py): any global field whose metadata-def.json entry
    # declares "denotes" becomes an Identifier block automatically, instead
    # of a hardcoded per-field config dict.
    for key, entry in data.items():
        field_def = metadata_def.get(key)
        if not field_def or "denotes" not in field_def:
            continue
        val = entry.get('value')
        if val is None or val == "":
            continue
        blocks = create_identifier_and_value_blocks(
            field_def["class name"], field_def.get("instance name", key), process_id,
            val, field_def["denotes"], field_def["denotes instance name"]
        )
        canonical_list.extend(blocks)

    canonical_list.append({
        "Plan": {
            "hasIdentifier": f"{process_id}_qtplan",
            "label": f"{process_id}_qtplan",
            "concretizes": [{
                "Qt Recipe": {
                    "hasIdentifier": f"{process_id}_qtrecipe",
                    "label": f"{process_id}_qtrecipe",
                    "denoted by": [{
                        "Identifier": {
                            "hasIdentifier": f"{process_id}_qtrecipe_type",
                            "label": f"{process_id}_qtrecipe_type"
                        }}]}}]}})

    canonical_list.append({
        "Temporal Region": {
            "hasIdentifier": f"{process_id}_temporalregion",
            "label": f"{process_id}_temporalregion",
            "has first instant": [{
                "Temporal Instant": {
                    "hasIdentifier": f"{process_id}_temporalregion_start",
                    "label": f"{process_id}_temporalregion_start",
                    "time:inXSDDateTimeStamp": _iso(value_of('starttime'))
                }
            }],
            "has last instant": [{
                "Temporal Instant": {
                    "hasIdentifier": f"{process_id}_temporalregion_end",
                    "label": f"{process_id}_temporalregion_end",
                    "time:inXSDDateTimeStamp": _iso(value_of('endtime'))
                }
            }]
        }
    })

    canonical_list.append({
        "Object": {
            "hasIdentifier": f"{process_id}_testpiece",
            "label": f"{process_id}_testpiece",
            "has role": [{
                "Test Piece Role": {
                    "hasIdentifier": f"{process_id}_testpiecerole",
                    "label": f"{process_id}_testpiecerole",
                }}],
            "derives from": [{
                "Steel": {
                    "hasIdentifier": f"{process_id}_steel",
                    "label": f"{process_id}_steel",
                }}],
            "has characteristic": [{
                "Austenitizing Point": {
                    "hasIdentifier": f"{process_id}_austenitizingpoint",
                    "label": f"{process_id}_austenitizingpoint",
                }
            }]
        }})

    canonical_list.append({
        "File Data Item": {
            "hasIdentifier": f"{process_id}_filedataitem",
            "label": f"{process_id}_filedataitem",
            "has url": "https://nextcloud.iwt.zz/apps/files/files/460150",
            "has part": [
                {
                    "Annotated Table": {
                        "hasIdentifier": f"{process_id}_qtresult_table",
                        "label": f"{process_id}_qtresult_table",
                        "is about": [{
                            "Data Item": {
                                "hasIdentifier": f"{process_id}_qtresult",
                                "label": f"{process_id}_qtresult"
                            }
                        }],
                        "table schema": [{
                            "Schema": {
                                "hasIdentifier": f"{process_id}_tableschema",
                                "label": f"{process_id}_tableschema",
                                "column": [{
                                    "Column Description": {
                                        "hasIdentifier": f"{process_id}_result_table_column_1",
                                        "label": f"{process_id}_result_table_column_1",
                                        "Datatype": "time:inXSDDate",
                                        "is about": [{
                                            "Date Value Specification": {
                                                "hasIdentifier": f"{process_id}_date",
                                                "label": f"{process_id}_date"
                                            }
                                        }],
                                        "has measurement unit label": [{
                                            "Measurement Unit Label": {
                                                "hasIdentifier": "unit:DAY",
                                                "label": "unit:DAY"
                                            }}]}},
                                    {
                                    "Column Description": {
                                        "hasIdentifier": f"{process_id}_result_table_column_2",
                                        "label": f"{process_id}_result_table_column_2",
                                        "Datatype": "time:inXSDTime",
                                        "is about": [{
                                            "Date Value Specification": {
                                                "hasIdentifier": f"{process_id}_time",
                                                "label": f"{process_id}_time"
                                            }
                                        }]
                                    }
                                    },
                                    {
                                    "Column Description": {
                                        "hasIdentifier": f"{process_id}_result_table_column_3",
                                        "label": f"{process_id}_result_table_column_3",
                                        "Datatype": "xsd:string"}
                                    },
                                    {
                                    "Column Description": {
                                        "hasIdentifier": f"{process_id}_result_table_column_4",
                                        "label": f"{process_id}_result_table_column_4",
                                        "Datatype": "xsd:double",
                                        "is about": [{
                                            "Temperature": {
                                                "hasIdentifier": f"{process_id}_quenchingchamber_temperature",
                                                "label": f"{process_id}_quenchingchamber_temperature"
                                            }
                                        }],
                                        "has measurement unit label": [{
                                            "Measurement Unit Label": {
                                                "hasIdentifier": "unit:DEG_C",
                                                "label": "unit:DEG_C"
                                            }}]}},

                                    {
                                    "Column Description": {
                                        "hasIdentifier": f"{process_id}_result_table_column_5",
                                        "label": f"{process_id}_result_table_column_5",
                                        "Datatype": "xsd:double",
                                        "is about": [{
                                            "Pressure": {
                                                "hasIdentifier": f"{process_id}_quenchingchamber_vacuumpressure",
                                                "label": f"{process_id}_quenchingchamber_vacuumpressure"
                                            }
                                        }],
                                        "has measurement unit label": [{
                                            "Measurement Unit Label": {
                                                "hasIdentifier": "unit:MilliBAR",
                                                "label": "unit:MilliBAR"
                                            }}]}},

                                    {
                                    "Column Description": {
                                        "hasIdentifier": f"{process_id}_result_table_column_6",
                                        "label": f"{process_id}_result_table_column_6",
                                        "Datatype": "xsd:double",
                                        "is about": [{
                                            "Pressure": {
                                                "hasIdentifier": f"{process_id}_quenchingchamber_pressure",
                                                "label": f"{process_id}_quenchingchamber_pressure"
                                            }
                                        }],
                                        "has measurement unit label": [{
                                            "Measurement Unit Label": {
                                                "hasIdentifier": "unit:MilliBAR",
                                                "label": "unit:MilliBAR"
                                            }}]}},

                                    {
                                    "Column Description": {
                                        "hasIdentifier": f"{process_id}_result_table_column_7",
                                        "label": f"{process_id}_result_table_column_7",
                                        "Datatype": "xsd:double",
                                        "is about": [{
                                            "Pressure": {
                                                "hasIdentifier": f"{process_id}_heatingchamber_vacuumpressure",
                                                "label": f"{process_id}_heatingchamber_vacuumpressure"
                                            }
                                        }],
                                        "has measurement unit label": [{
                                            "Measurement Unit Label": {
                                                "hasIdentifier": "unit:MilliBAR",
                                                "label": "unit:MilliBAR"
                                            }}]}},

                                    {
                                    "Column Description": {
                                        "hasIdentifier": f"{process_id}_result_table_column_8",
                                        "label": f"{process_id}_result_table_column_8",
                                        "Datatype": "xsd:double",
                                        "is about": [{
                                            "Temperature": {
                                                "hasIdentifier": f"{process_id}_heatingchamber_temperature",
                                                "label": f"{process_id}_heatingchamber_temperature"
                                            }
                                        }],
                                        "has measurement unit label": [{
                                            "Measurement Unit Label": {
                                                "hasIdentifier": "unit:DEG_C",
                                                "label": "unit:DEG_C"
                                            }}]}},

                                    {
                                    "Column Description": {
                                        "hasIdentifier": f"{process_id}_result_table_column_10",
                                        "label": f"{process_id}_result_table_column_10",
                                        "Datatype": "xsd:double",
                                        "is about": [{
                                            "Pressure": {
                                                "hasIdentifier": f"{process_id}_heatingchamber_pressure",
                                                "label": f"{process_id}_heatingchamber_pressure"
                                            }
                                        }],
                                        "has measurement unit label": [{
                                            "Measurement Unit Label": {
                                                "hasIdentifier": "unit:MilliBAR",
                                                "label": "unit:MilliBAR"
                                            }}]}},

                                ]}}]}},
                {
                    "Data Format Specification": {
                        "hasIdentifier": f"{process_id}_dataformatspec",
                        "label": f"{process_id}_dataformatspec",
                        "has url": "http://edamontology.org/format_3752"
                    }}]
        }})

    # --- Per-step, data-driven section: step count and content come from
    # the actual charge (see module docstring for what's generic vs fixed).
    prev_step_label = None
    prev_class_name = None
    for i in range(1, numberofsteps + 1):
        chamber = None
        function_value = None
        recipe = None
        oilcirculation = False
        oilcirculationupwards = False
        oilcirculationfast = False
        qkoilgate = None
        programend = None
        programendreached = None
        # "plain": pass the setpoint_temperatur[°c] value straight through as-is.
        # "ramp": parse it as a rate+target ramp instruction (e.g. "+/min 15 End >= 845").
        # "none": this step type has no chamber-temperature target at all.
        temperature_mode = "none"
        # Some raw fields hold placeholder values (e.g. "0") on step types
        # where they're not a real target -- so "does the data have a value"
        # isn't a reliable signal for these two; gate by step type instead.
        include_vacuum_pressure = True
        include_time_in_oil = False

        step_name = str(step_value_of(i, "name"))

        if step_name == "Evakuieren":
            class_name = 'Process'
            chamber = "Heating Chamber"
            function_value = "Evacuation Function"
            recipe = 'Recipe'
            oilcirculation = True
            temperature_mode = "plain"

        elif step_name == "PROG-ENDE":
            class_name = 'Process'
            chamber = "Quenching Chamber"
            recipe = 'Recipe'
            programend = True
            programendreached = True
            qkoilgate = False
            include_vacuum_pressure = False

        elif step_name.split(" ")[0] == "Heizen":
            class_name = 'Heating'
            chamber = "Heating Chamber"
            function_value = "Heating Function"
            recipe = "Heating Recipe"
            oilcirculation = True
            temperature_mode = "ramp"

        elif step_name.split(" ")[0] == "Durchwärmen":
            class_name = 'Soaking'
            chamber = "Heating Chamber"
            function_value = "Holding Function"
            recipe = "Soaking Recipe"
            oilcirculation = True
            temperature_mode = "plain"

        elif step_name.split(" ")[0] == "Absenken":
            class_name = 'Cooling'
            chamber = "Heating Chamber"
            function_value = "Cooling Function"
            recipe = "Cooling Recipe"
            oilcirculation = True
            temperature_mode = "ramp"

        elif step_name.split(" ")[0] == "Ölabschrecken":
            class_name = 'Quenching'
            chamber = "Quenching Chamber"
            function_value = "Quenching Function"
            recipe = "Quenching Recipe"
            qkoilgate = True
            oilcirculation = True
            oilcirculationupwards = True
            oilcirculationfast = True
            programend = False
            programendreached = False
            include_vacuum_pressure = False
            include_time_in_oil = True

        else:
            class_name = 'Process'
            chamber = "Heating Chamber"
            recipe = 'Recipe'
            temperature_mode = "plain"

        step_data = {
            "hasIdentifier": f"{process_id}_step_{i}",
            "label": f"{process_id}_step_{i}",
            "denoted by": [{"Identifier": {"hasIdentifier": f"{process_id}_step_{i}_name", "label": f"{process_id}_step_{i}_name", "has value": step_name}}],
            "proper occurrent part of": [{"Quenching And Tempering": {"hasIdentifier": f"{process_id}_qt", "label": f"{process_id}_qt", }}],
            "exists at": [{
                "Temporal Region": {
                    "hasIdentifier": f"{process_id}_step_{i}_temporalregion",
                    "label": f"{process_id}_step_{i}_temporalregion",
                    "has first instant": [{
                        "Temporal Instant": {
                            "hasIdentifier": f"{process_id}_step_{i}_temporalinterval_start",
                            "label": f"{process_id}_step_{i}_temporalinterval_start",
                            "time:inXSDDateTimeStamp": _iso(step_value_of(i, "starttime"))
                        }
                    }],
                    "has last instant": [{
                        "Temporal Instant": {
                            "hasIdentifier": f"{process_id}_step_{i}_temporalinterval_end",
                            "label": f"{process_id}_step_{i}_temporalinterval_end",
                            "time:inXSDDateTimeStamp": _iso(step_value_of(i, "endtime"))
                        }}]}}],
            "has participant": [{
                "Furnace": {
                    "hasIdentifier": f"{process_id}_furnace",
                    "label": f"{process_id}_furnace",
                }
            }],
            "realizes": []
        }

        if function_value:
            step_data["realizes"].append({
                function_value: {
                    "hasIdentifier": f"{process_id}_{function_value.lower().replace(' ', '')}",
                    "label": f"{process_id}_{function_value.lower().replace(' ', '')}",
                }
            })

        if recipe:
            recipe_slug = recipe.lower().replace(' ', '')
            if step_name == "Evakuieren":
                recipe_hasid = f"{process_id}_evacuatingrecipe"
            elif step_name == "PROG-ENDE":
                recipe_hasid = f"{process_id}_processendrecipe"
            else:
                recipe_hasid = f"{process_id}_{recipe_slug}"

            recipe_content = {
                "hasIdentifier": recipe_hasid,
                "label": recipe_hasid,
                "part of": [{
                    "Qt Recipe": {
                        "hasIdentifier": f"{process_id}_qtrecipe",
                        "label": f"{process_id}_qtrecipe",
                    }
                }]
            }

            # --- Generic per-leaf dispatch (like jsontocjson_tto.py): loop
            # over every step_<leaf> field metadata-def.json declares with a
            # "unit", check whether THIS step actually has that key, and
            # build the block shape its declared "class name" calls for --
            # instead of one hardcoded `if <flag>:` block per named field.
            has_part_list = []
            for leaf_key, leaf_def in metadata_def.items():
                if not leaf_key.startswith("step_") or "unit" not in leaf_def:
                    continue
                leaf = leaf_key[len("step_"):]
                if leaf == "setpoint_vak_heizung[mbar]" and not include_vacuum_pressure:
                    continue
                if leaf == "setpoint_zt_in_öl[s]" and not include_time_in_oil:
                    continue

                raw_value = step_value_of(i, leaf)
                if raw_value is None or raw_value == "":
                    continue

                slug = f"{recipe_slug}_{STEP_LEAF_SLUGS.get(leaf, leaf.split('[')[0].rstrip('_'))}"
                unit_id = leaf_def["unit"]

                if leaf_def["class name"] == "Time Duration":
                    has_part_list.append(create_time_duration_block(
                        process_id, slug, int(raw_value), unit_id,
                        f"{process_id}_step_{i}_temporalregion"
                    ))
                    continue

                if leaf == "setpoint_temperatur[°c]":
                    if temperature_mode == "none":
                        continue
                    chamber_slug = chamber.lower().replace(' ', '')
                    if temperature_mode == "ramp":
                        # e.g. "+/min 15 End >= 845" -- a rate and a target,
                        # both real numbers once parsed out of the instruction.
                        rate_match = re.search(r'[+-]?/min\s*(\d+)', raw_value)
                        target_match = re.search(r'[<>]=?\s*(\d+)', raw_value)
                        value_specs = []
                        if rate_match:
                            value_specs.append({
                                "Scalar Value Specification": {
                                    "hasIdentifier": f"{process_id}_{recipe_slug}_temperaturechangeratespecification_valuespecification",
                                    "label": f"{process_id}_{recipe_slug}_temperaturechangeratespecification_valuespecification",
                                    "has measurement unit label": [{"Measurement Unit Label": {"hasIdentifier": "unit:DEG_C_PER_MIN", "label": "unit:DEG_C_PER_MIN"}}],
                                    "has specified numeric value": int(rate_match.group(1))
                                }
                            })
                        if target_match:
                            value_specs.append({
                                "Scalar Value Specification": {
                                    "hasIdentifier": f"{process_id}_{recipe_slug}_targettemperature_valuespecification",
                                    "label": f"{process_id}_{recipe_slug}_targettemperature_valuespecification",
                                    "has measurement unit label": [{"Measurement Unit Label": {"hasIdentifier": unit_id, "label": unit_id}}],
                                    "has specified numeric value": int(target_match.group(1)),
                                    "is about": [{"Temperature": {"hasIdentifier": f"{process_id}_{chamber_slug}_temperature", "label": f"{process_id}_{chamber_slug}_temperature"}}]
                                }
                            })
                        if value_specs:
                            has_part_list.append({
                                "Specification Datum": {
                                    "hasIdentifier": f"{process_id}_{recipe_slug}_temperaturechangeratespecification",
                                    "label": f"{process_id}_{recipe_slug}_temperaturechangeratespecification",
                                    "has value specification": value_specs
                                }
                            })
                    else:  # "plain": a bare target temperature, cast to int
                        has_part_list.append(create_scalar_value_spec_block(
                            process_id, slug, int(raw_value), unit_id,
                            "Temperature", f"{process_id}_{chamber_slug}_temperature"
                        ))
                    continue

                # Temperature, pressure, and time-valued leaves are always numeric.
                try:
                    numeric_value = int(raw_value)
                except (TypeError, ValueError):
                    continue

                is_about_class = is_about_id = None
                is_about = STEP_LEAF_IS_ABOUT.get(leaf)
                if is_about:
                    is_about_class, suffix = is_about
                    chamber_slug = chamber.lower().replace(' ', '')
                    is_about_id = f"{process_id}_{chamber_slug}_{suffix}"

                has_part_list.append(create_scalar_value_spec_block(process_id, slug, numeric_value, unit_id, is_about_class, is_about_id))

            # --- Device on/off state blocks: driven by furnace digital
            # outputs, which have no metadata-def.json entry (out of scope
            # for now), so these stay explicit per step-type, same as before.
            def device_state(name_slug, on):
                state = "ON" if on else "OFF"
                ident = "hto:HTO_0000035" if on else "hto:HTO_0000036"
                return {
                    "Device Operation State": {
                        "hasIdentifier": f"{process_id}_{recipe_slug}_{name_slug}",
                        "label": f"{process_id}_{recipe_slug}_{name_slug}",
                        "has part": [{
                            "Device Operation State Value": {
                                "hasIdentifier": f"{process_id}_{recipe_slug}_{name_slug}_value",
                                "label": f"{process_id}_{recipe_slug}_{name_slug}_value",
                                "specified by value": [{state: {"hasIdentifier": ident, "label": ident}}]
                            }
                        }]
                    }
                }

            has_part_list.append(device_state("oilcirculation", oilcirculation))
            has_part_list.append(device_state("oilcirculationupwards", oilcirculationupwards))
            has_part_list.append(device_state("oilcirculationfast", oilcirculationfast))
            if qkoilgate is not None:
                has_part_list.append(device_state("qkoilgate", qkoilgate))
            if programend is not None:
                has_part_list.append(device_state("programend", programend))
            if programendreached is not None:
                has_part_list.append(device_state("programendreached", programendreached))

            if has_part_list:
                recipe_content["has part"] = has_part_list

            step_data["realizes"].append({
                "Plan": {
                    "hasIdentifier": f"{process_id}_{class_name.lower().replace(' ', '')}plan",
                    "label": f"{process_id}_{class_name.lower().replace(' ', '')}plan",
                    "concretizes with": [{
                        recipe: recipe_content
                    }]
                }
            })

        if i > 1:
            step_data["preceded by"] = [{
                prev_class_name: {
                    "hasIdentifier": prev_step_label,
                    "label": prev_step_label,
                }
            }]
        canonical_list.append({class_name: step_data})

        prev_step_label = f"{process_id}_step_{i}"
        prev_class_name = class_name

    # --- Fixed structural scaffolding again: the furnace/equipment tree. ---
    canonical_list.append({
        "Furnace": {
            "hasIdentifier": f"{process_id}_furnace",
            "label": f"{process_id}_furnace",
            "denoted by": [{"Identifier": {"hasIdentifier": f"{process_id}_furnace_identifier", "label": f"{process_id}_furnace_identifier", "has value": f"{process_id}_furnace_name"}}],
            "has part": [
                {"Heating Chamber": {
                    "hasIdentifier": f"{process_id}_heatingchamber",
                    "label": f"{process_id}_heatingchamber",
                    "denoted by": [{"Identifier": {"hasIdentifier": f"{process_id}_heatingchamber_identifier", "label": f"{process_id}_heatingchamber_identifier", "has value": f"{process_id}_heatingchamber_name"}}],
                    "has part": [{
                        "Fluid (Object)": {
                            "hasIdentifier": f"{process_id}_atmosphere",
                            "label": f"{process_id}_atmosphere",
                            "has quality": [
                                {"Temperature": {"hasIdentifier": f"{process_id}_heatingchamber_temperature", "label": f"{process_id}_heatingchamber_temperature", }},
                                {"Pressure": {"hasIdentifier": f"{process_id}_heatingchamber_pressure", "label": f"{process_id}_heatingchamber_pressure", }},
                                {"Pressure": {"hasIdentifier": f"{process_id}_heatingchamber_vacuumpressure", "label": f"{process_id}_heatingchamber_vacuumpressure", }},
                            ]}}]
                }},

                {"Quenching Chamber": {
                    "hasIdentifier": f"{process_id}_quenchingchamber",
                    "label": f"{process_id}_quenchingchamber",
                    "denoted by": [{"Identifier": {"hasIdentifier": f"{process_id}_quenchingchamber_identifier", "label": f"{process_id}_quenchingchamber_identifier", "has value": f"{process_id}_quenchingchamber_name"}}],
                    "has part": [{
                        "Quenchant": {
                            "hasIdentifier": f"{process_id}_quenchant",
                            "label": f"{process_id}_quenchant",
                            "has quality": [
                                {"Temperature": {"hasIdentifier": f"{process_id}_quenchingchamber_temperature", "label": f"{process_id}_quenchingchamber_temperature", }},
                                {"Temperature": {"hasIdentifier": f"{process_id}_quenchingoil_temperature", "label": f"{process_id}_quenchingoil_temperature", }},
                                {"Pressure": {"hasIdentifier": f"{process_id}_quenchingchamber_pressure", "label": f"{process_id}_quenchingchamber_pressure", }},
                                {"Pressure": {"hasIdentifier": f"{process_id}_quenchingchamber_vacuumpressure", "label": f"{process_id}_quenchingchamber_vacuumpressure", }},
                            ]}}]
                }},

                {"Device": {
                    "hasIdentifier": f"{process_id}_quenchingpump",
                    "label": f"{process_id}_quenchingpump",
                    "denoted by": [{"Identifier": {"hasIdentifier": f"{process_id}_quenchingpump_identifier", "label": f"{process_id}_quenchingpump_identifier", "has value": f"{process_id}_quenchingpump_name"}}],
                }},

                {"Device": {
                    "hasIdentifier": f"{process_id}_vacuumpump",
                    "label": f"{process_id}_vacuumpump",
                    "denoted by": [{"Identifier": {"hasIdentifier": f"{process_id}_vacuumpump_identifier", "label": f"{process_id}_vacuumpump_identifier", "has value": f"{process_id}_vacuumpump_name"}}],
                }},

                {"Device": {
                    "hasIdentifier": f"{process_id}_measurementdevice",
                    "label": f"{process_id}_measurementdevice",
                    "denoted by": [{"Identifier": {"hasIdentifier": f"{process_id}_measurementdevice_identifier", "label": f"{process_id}_measurementdevice_identifier", "has value": f"{process_id}_measurementdevice_name"}}],
                    "has function": [{"Measuring Function": {"hasIdentifier": f"{process_id}_measuringdevicefunction", "label": f"{process_id}_measuringdevicefunction"}}, ],
                    "has role": [{"Device Role": {"hasIdentifier": f"{process_id}_measuringdevicerole", "label": f"{process_id}_measuringdevicerole"}}],
                }}
            ],

            "has function": [{"Heating Function": {"hasIdentifier": f"{process_id}_heatingfunction", "label": f"{process_id}_heatingfunction"}},
                              {"Holding Function": {"hasIdentifier": f"{process_id}_holdingfunction", "label": f"{process_id}_holdingfunction"}},
                              {"Cooling Function": {"hasIdentifier": f"{process_id}_coolingfunction", "label": f"{process_id}_coolingfunction"}},
                              {"Quenching Function": {"hasIdentifier": f"{process_id}_quenchingfunction", "label": f"{process_id}_quenchingfunction"}},
                              {"Mechanical Function": {"hasIdentifier": f"{process_id}_convectionpumpfunction", "label": f"{process_id}_convectionpumpfunction"}}
                              ],

            "has role": [{
                "Device Role": {
                    "hasIdentifier": f"{process_id}_furnacerole",
                    "label": f"{process_id}_furnacerole"
                }}],
        }})

    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(canonical_list, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    transform_json_to_canonical(
        '/home/gosula@iwt.zz/DigitalMaterial/rde-hto/container/data/meta/charge_3467_metadata.json',
        '/home/gosula@iwt.zz/DigitalMaterial/rde-hto/container/data/tasksupport/metadata-def.json',
        '/home/gosula@iwt.zz/DigitalMaterial/rde-hto/container/data/structured/canonical_json_file.json'
    )
