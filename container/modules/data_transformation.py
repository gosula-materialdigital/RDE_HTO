"""
Custom rdetoolkit dataset function for the heat-treatment (HTO) pipeline.

Parses furnace-controller CSV exports (recipe header + step program +
time-series sensor data, all in one self-contained file) and writes, per
charge: a plain structured dump, an RDE-validated typed metadata record,
the raw time-series as CSV, and an ontology-mapped canonical JSON.
"""
from pathlib import Path
import io
import re
import pandas as pd
from rdetoolkit.models.rde2types import RdeInputDirPaths, RdeOutputResourcePath
from rdetoolkit.rde2util import Meta
from rdetoolkit.exceptions import StructuredError
from rdetoolkit.fileops import writef_json
from modules.jsontocjson_hto import transform_json_to_canonical


def get_input_files(file_paths: list[Path]) -> list[tuple[str, dict, pd.DataFrame]]:
    """
    Parses every heat-treatment furnace-log CSV in the input folder.
    Returns a list of (process_id, metadata_dict, dataframe).
    """
    results = []

    csv_paths = [f for f in file_paths if f.suffix.lower() == ".csv"]
    for csv_path in csv_paths:
        parsed = parse_heat_treatment_csv(csv_path)
        if parsed is None:
            continue
        results.append(parsed)

    return results


def _read_text_with_fallback(csv_path: Path) -> list[str]:
    """
    Reads a furnace-controller CSV export. These exports come out as
    Latin-1/cp1252, not UTF-8. Decoding as UTF-8 strict either raises
    (most non-ASCII bytes aren't valid UTF-8 on their own) or, for byte
    sequences that happen to form valid-but-wrong UTF-8, silently produces
    mojibake ('Â'/'Ã' prefixed characters) -- so fall back to cp1252 in
    both cases.
    """
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            content = f.readlines()
        if content and ("Â" in content[0] or "Ã" in content[0]):
            raise UnicodeDecodeError("utf-8", b"", 0, 1, "Detected double encoding")
    except UnicodeDecodeError:
        with open(csv_path, 'r', encoding='cp1252', errors='ignore') as f:
            content = f.readlines()
    return content


def _sort_heat_treatment_metadata(metadata: dict[str, str]) -> dict[str, str]:
    """Keeps step_N_* keys in numeric step order, with global keys first."""
    def sort_key(item: tuple[str, str]) -> tuple[int, int, str]:
        key = item[0]
        if key.startswith("step_"):
            try:
                step_num = int(key.split("_")[1])
                return (1, step_num, key)
            except (IndexError, ValueError):
                return (1, 999, key)
        return (0, 0, key)
    return dict(sorted(metadata.items(), key=sort_key))


def parse_heat_treatment_csv(csv_path: Path) -> tuple[str, dict, pd.DataFrame] | None:
    """
    Parses a self-contained heat-treatment furnace log: a recipe header and
    step program (";"-separated key/value lines) followed by a time-series
    measurement table introduced by a line starting with "Date".
    Returns (process_id, metadata_dict, dataframe), or None if the file has
    no measurement section.
    """
    sep = ";"
    content = _read_text_with_fallback(csv_path)

    metadata: dict[str, str] = {}
    current_step = "0"
    header_end_idx = None

    for idx, raw_line in enumerate(content):
        line = raw_line.strip().strip(sep)
        if not line:
            continue

        if line.lower().startswith("date"):
            header_end_idx = idx
            break

        parts = [p.strip() for p in line.split(sep)]

        if parts[0].lower() == "step" and len(parts) >= 3:
            current_step = parts[1]
            metadata[f"step_{current_step}_name"] = parts[2]
        elif parts[0].lower() == "set point" and len(parts) >= 4:
            prop_name = f"{parts[0]}_{parts[1]}"
            if len(parts) == 4 and parts[2] == "=":
                val_string = parts[3]
            else:
                val_string = " ".join(parts[2:])
            metadata[f"step_{current_step}_{prop_name}"] = val_string
        elif len(parts) >= 2:
            if len(parts) == 3:
                prop_name = f"{parts[0]}_{parts[1]}"
                val = parts[2]
            else:
                prop_name = parts[0]
                val = parts[1]

            key = f"step_{current_step}_{prop_name}" if current_step != "0" else prop_name
            metadata[key] = val
        else:
            print(f"Skipping line with insufficient columns in {csv_path.name}: {line}")

    if header_end_idx is None:
        print(f"Skipping {csv_path.name}: no 'Date' measurement section found.")
        return None

    metadata = {k.lower().replace(" ", ""): v for k, v in metadata.items()}

    # --- Determine process_id: use it if the file provided one, otherwise
    #     derive it from the load name (falling back to the filename). ---
    if "process_id" not in metadata:
        loadname = metadata.get("loadname", "").strip()
        process_id = loadname.lower().replace(" ", "_") if loadname else csv_path.stem
        metadata["process_id"] = process_id
    else:
        process_id = metadata["process_id"]

    metadata = _sort_heat_treatment_metadata(metadata)

    # --- Parse the time-series table below the header line ---
    measurement_text = "".join(content[header_end_idx:])
    df = pd.read_csv(io.StringIO(measurement_text), sep=sep, decimal=",")
    df = df.loc[:, ~df.columns.str.contains(r"^Unnamed", regex=True)]
    return process_id, metadata, df


# metadata-def.json declares each per-step field ONCE, by leaf name only
# (e.g. "step_setpoint_temperatur[°c]", no step number) and marks it
# "variable": true -- rdetoolkit's own mechanism for repeated metadata.
# save_metadata() below groups each real "step_<N>_<leaf>" value into a
# per-leaf list (index i-1 = step i), which Meta.assign_vals() consumes
# natively for "variable" fields, writing a "variable": [{step1 fields},
# {step2 fields}, ...] array via the standard Meta.writefile() path -- no
# custom casting needed. Missing values must be "" (not None): Meta stringifies
# every list element with str() before checking for empties, so a literal
# None would become the string "None" instead of being skipped.
STEP_KEY_RE = re.compile(r"^step_(\d+)_(.+)$")


def save_metadata(metadata: dict[str, str], metadata_def_json_path: str | Path, save_path: str | Path):
    """メタデータをmetadata-def.jsonに基づいて保存"""
    meta = Meta(metadata_def_json_path)

    numberofsteps = int(metadata.get("numberofsteps", 0))
    step_leaves = {m.group(2) for k in metadata if (m := STEP_KEY_RE.match(k))}

    entry = {k: v for k, v in metadata.items() if not STEP_KEY_RE.match(k)}
    for leaf in step_leaves:
        entry[f"step_{leaf}"] = [metadata.get(f"step_{i}_{leaf}") or "" for i in range(1, numberofsteps + 1)]

    meta.assign_vals(entry)
    meta.writefile(str(save_path))


def my_hto_func(srcpaths: RdeInputDirPaths, resource_paths: RdeOutputResourcePath):
    """rdetoolkit custom_dataset_function: processes every heat-treatment
    CSV found in the input folder and writes the four output artifacts
    described in the module docstring."""
    try:
        # 1. Get all parsed heat-treatment records from the input folder
        all_experiments = get_input_files(resource_paths.rawfiles)

        if not all_experiments:
            print("No heat-treatment CSV files found.")
            return

        for process_id, metadata, dataframe in all_experiments:
            # 2. Save metadata as [process_id].json in the 'struct' folder
            metadata_filename = f"{process_id}.json"
            writef_json(resource_paths.struct.joinpath(metadata_filename), metadata)

            # 2b. Save the RDE-validated, typed metadata as [process_id]_metadata.json
            #     in the 'meta' folder, per the static metadata-def.json (its
            #     step_N_* fields are declared "variable", so any recipe length
            #     is handled without changing the schema -- see save_metadata()).
            try:
                meta_filename = f"{process_id}_metadata.json"
                metadata_def_path = srcpaths.tasksupport.joinpath("metadata-def.json")
                meta_path = resource_paths.meta.joinpath(meta_filename)
                save_metadata(metadata, metadata_def_path, meta_path)
            except StructuredError as e:
                print(f"Error saving metadata for {process_id}: {e}")
                continue

            # 3. Save the time-series data as [process_id].csv in the 'struct' folder
            csv_filename = f"{process_id}.csv"
            dataframe.to_csv(
                resource_paths.struct.joinpath(csv_filename),
                index=False
            )

            # 4. Save the ontology-mapped canonical JSON as [process_id]_canonical.json
            #    in the 'struct' folder, built from the just-written meta output
            canonical_filename = f"{process_id}_canonical.json"
            transform_json_to_canonical(
                meta_path,
                metadata_def_path,
                resource_paths.struct.joinpath(canonical_filename)
            )

            print(f"Processed and saved: {process_id}")

    except Exception as e:
        raise StructuredError(f"An error occurred during processing: {e}") from e
    