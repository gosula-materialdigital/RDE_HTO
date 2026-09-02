# rde-hto

An [RDE Toolkit](https://github.com/nims-mdpf/rdetoolkit) (NIMS's Research Data Express structuring framework) pipeline for heat-treatment furnace data — parsing raw furnace-controller CSV exports, structuring them into RDE-standard metadata, and mapping that metadata onto a BFO/PMD Core Ontology-style semantic graph.

This is the practical, working proof of concept behind the NIMS↔Platform MaterialDigital collaboration on bridging RDE's data structuring with application ontologies in the MSE (Materials Science and Engineering) domain.

## What it does

Given a raw furnace-controller CSV (a heat-treatment recipe — quenching & tempering, carburizing, etc. — recorded as a step-by-step program plus time-series sensor data, in whatever step count that particular charge actually used), the pipeline:

1. **Parses** the raw file into a flat metadata dict — global fields (treatment type, timestamps) plus per-step fields (setpoints, durations), handling the furnace controller's Latin-1/cp1252 encoding correctly.
2. **Validates and types** that metadata against a schema (`metadata-def.json`), producing an RDE-standard structured metadata record.
3. **Maps** the structured metadata onto ontology classes (Process, Heating, Soaking, Cooling, Quenching, Temperature, Pressure, Specification Datum, etc.) grounded in real ontology IRIs (PMD Core Ontology, BFO, OWL-Time), producing a canonical JSON-LD-style graph.

The design goal throughout: **works for any recipe length or step ordering without touching code** — a 5-step charge and a 9-step charge run through the exact same schema and code path.

## Pipeline flow

```
Raw furnace CSV (any step count)
        │  get_input_files() / parse_heat_treatment_csv()
        ▼
Flat metadata dict  (process_id, treatmenttype, step_N_<leaf>, ...)
        │  save_metadata()
        ▼
data/meta/{process_id}_metadata.json
        {"constant": {...global fields...}, "variable": [{step 1}, {step 2}, ...]}
        │  transform_json_to_canonical()
        ▼
data/structured/{process_id}_canonical.json
        (BFO/PMD-style ontology graph)
```

Alongside this, each run also writes a plain structured dump (`data/structured/{process_id}.json`/`.csv`) and validates `data/invoice/invoice.json` against `data/tasksupport/invoice.schema.json` — the submission-level identifying info for the charge (separate from the detailed measurement metadata).

## Repository layout

```
container/
├── main.py                          # rdetoolkit entry point
├── requirements.txt
├── modules/
│   ├── data_transformation.py       # CSV parsing + the custom_dataset_function
│   └── jsontocjson_hto.py           # metadata → ontology graph mapping
└── data/
    ├── inputdata/                   # raw furnace CSVs go here
    ├── invoice/invoice.json         # per-charge submission metadata (input)
    ├── tasksupport/
    │   ├── metadata-def.json        # per-field schema: type, unit, ontology class + IRI
    │   ├── invoice.schema.json      # schema for invoice.json
    │   └── rdeconfig.yml
    ├── meta/                        # output: typed structured metadata (per charge)
    └── structured/                  # output: plain dump, CSV, and canonical ontology JSON
```

## Setup

Requires Python 3.12 and a virtual environment (`.venv/`, kept out of git).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r container/requirements.txt
```

`requirements.txt` currently pins `rdetoolkit==1.6.3`; `pandas` is also used directly by the CSV parser and comes in as a dependency of `rdetoolkit`.

## Running it

rdetoolkit resolves all its paths (`data/`, `data/tasksupport/`, etc.) relative to the **current working directory**, not to `main.py`'s location — so you must run it from inside `container/`:

```bash
cd container
python main.py
```

Drop one or more furnace CSVs into `container/data/inputdata/` first; every `.csv` found there gets processed in a single run. Output lands in `container/data/meta/` and `container/data/structured/`, named per charge (`{process_id}_metadata.json`, `{process_id}_canonical.json`, etc.).

## Key files, and the design decisions behind them

- **`metadata-def.json`** declares each field's type, unit, and (where meaningful) an ontology `class name` + real `iri`, plus a `denotes`/`denotes iri` for identifier-type fields. Per-step fields (`step_setpoint_temperatur[°c]`, etc.) are declared **once**, by leaf name only — no step number — and marked `"variable": true`, rdetoolkit's own mechanism for repeated metadata. This is what makes the schema step-count-agnostic: a 5-step and a 9-step charge use the identical file.
- **`jsontocjson_hto.py`** dispatches most of the field-to-ontology-block mapping generically, driven by what `metadata-def.json` declares (its `class name`, whether it has a `denotes`). The furnace equipment scaffolding and the step-name → process-type classification (which furnace step names mean "Heating" vs "Quenching", etc.) are fixed domain knowledge and stay as explicit Python, since that's genuinely code, not field metadata.
- **Ontology IRIs** in `metadata-def.json` were resolved directly from the actual ontology TTL files (PMD Core Ontology, BFO, OWL-Time, HTO) by label-matching against the raw ontology graphs — not hand-guessed.

## Known limitations / open items

- Digital-output fields (oil circulation, gas gates, etc.) aren't declared in `metadata-def.json`; they're still driven by step-type classification in Python.
- `catalog.schema.json` (dataset-level cataloging metadata — title, creator, etc., a layer NIMS's own RDE template convention includes) hasn't been built yet.

