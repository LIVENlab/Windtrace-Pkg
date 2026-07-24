import argparse
import csv
import importlib.util
from pathlib import Path
try:
    from .config import load_config
except ImportError:
    from config import load_config

BASE_COLUMNS = ["variable_name", "group", "subtype", "share"]
SELECTOR_FIELDS = ("name", "location", "reference_product")

def apply_config_defaults(args):
    """
    If --config is provided, fill missing updater arguments from windtrace_config.yml.
    Explicit command-line arguments still take priority.
    """
    if not getattr(args, "config", None):
        return args

    config = load_config(args.config)

    if hasattr(args, "csv") and not args.csv:
        args.csv = config.activity_variables_csv

    if hasattr(args, "version") and not args.version:
        args.version = config.ecoinvent_version

    if hasattr(args, "project") and not args.project:
        args.project = config.project_name

    if hasattr(args, "database") and not args.database:
        args.database = config.source_database

    return args

def version_prefix(version):
    return "ei_" + str(version).strip().replace(".", "_").replace("-", "_")


def version_columns(version):
    prefix = version_prefix(version)
    return [f"{prefix}_{field}" for field in SELECTOR_FIELDS]


def load_legacy_consts(path):
    spec = importlib.util.spec_from_file_location("legacy_consts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def add_selector(row, version, selector):
    prefix = version_prefix(version)
    row[f"{prefix}_name"] = selector.get("name")
    row[f"{prefix}_location"] = selector.get("location")
    row[f"{prefix}_reference_product"] = selector.get("reference product")


def make_row(variable_name, group, subtype="", share=""):
    return {"variable_name": variable_name, "group": group, "subtype": subtype, "share": share}


def init_from_legacy(args):
    legacy = load_legacy_consts(Path(args.legacy_consts))
    rows = []

    def append_row(group, variable_name, selector, subtype="", share=""):
        row = make_row(variable_name, group, subtype, share)
        for version in args.versions:
            add_selector(row, version, selector)
        rows.append(row)

    for variable_name, selector in legacy.MATERIALS_EI_ACTIVITY_CODES.items():
        append_row("materials", variable_name, selector)

    for variable_name, treatment_map in legacy.EOL_EI_ACTIVITY_CODES.items():
        for treatment, selector in treatment_map.items():
            append_row("eol", variable_name, selector, subtype=treatment)

    for variable_name, selector in legacy.MATERIAL_PROCESSING_EI_ACTIVITY_CODES.items():
        append_row("processing", variable_name, selector)

    for country, values in legacy.STEEL_DATA_EU27.items():
        append_row("steel_electricity", country, values["elect"], share=values["share"])
        append_row("steel_gas", country, values["gas"], share=values["share"])

    fieldnames = BASE_COLUMNS[:]
    for version in args.versions:
        fieldnames.extend(version_columns(version))
    write_csv(args.out, fieldnames, rows)


def add_version(args):
    args = apply_config_defaults(args)

    if not args.csv:
        raise SystemExit("Missing CSV path. Provide --csv or set ecoinvent.activity_variables_csv in the config file.")

    fieldnames, rows = read_csv(args.csv)
    new_columns = version_columns(args.to_version)
    for column in new_columns:
        if column not in fieldnames:
            fieldnames.append(column)

    source_columns = version_columns(args.from_version) if args.from_version else None
    for row in rows:
        for target_column in new_columns:
            if source_columns:
                source_column = target_column.replace(version_prefix(args.to_version), version_prefix(args.from_version))
                row[target_column] = row.get(source_column, "")
            else:
                row[target_column] = ""
    write_csv(args.csv, fieldnames, rows)


def validate(args):
    args = apply_config_defaults(args)

    if not args.csv:
        raise SystemExit("Missing CSV path. Provide --csv or set ecoinvent.activity_variables_csv in the config file.")
    if not args.version:
        raise SystemExit("Missing ecoinvent version. Provide --version or set ecoinvent.version in the config file.")
    if not args.database:
        raise SystemExit("Missing database name. Provide --database or set brightway.source_database in the config file.")

    import bw2data as bd

    fieldnames, rows = read_csv(args.csv)
    columns = version_columns(args.version)
    missing = [column for column in columns if column not in fieldnames]
    if missing:
        raise SystemExit(f"Missing CSV columns for ecoinvent {args.version}: {missing}")

    if args.project:
        bd.projects.set_current(args.project, update=False)
    database = bd.Database(args.database)
    index = {
        (value["name"], value["location"], value["reference product"])
        for value in database.load().values()
    }

    failed = []
    for row in rows:
        selector = tuple(row[column].strip() for column in columns)
        if not all(selector):
            continue
        if selector not in index:
            failed.append((row["group"], row["variable_name"], row["subtype"], selector))

    if failed:
        print(f"{len(failed)} activity variables were not found in {args.database}:")
        for group, variable_name, subtype, selector in failed:
            subtype_text = f"/{subtype}" if subtype else ""
            print(f"- {group}/{variable_name}{subtype_text}: {selector}")
        raise SystemExit(1)
    print(f"All non-empty selectors for ecoinvent {args.version} were found in {args.database}.")


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames), list(reader)


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path}")


def build_parser():
    parser = argparse.ArgumentParser(description="Maintain versioned WindTrace ecoinvent activity variables.")
    subparsers = parser.add_subparsers(required=True)

    init_parser = subparsers.add_parser("init-from-legacy", help="Create the variables CSV from legacy consts.py.")
    init_parser.add_argument("--legacy-consts", required=True)
    init_parser.add_argument("--out", required=True)
    init_parser.add_argument("--versions", nargs="+", default=["3.12"])
    init_parser.set_defaults(func=init_from_legacy)

    add_parser = subparsers.add_parser("add-version", help="Add columns for a new ecoinvent version.")
    add_parser.add_argument("--config")
    add_parser.add_argument("--csv")
    add_parser.add_argument("--to-version", required=True)
    add_parser.add_argument("--from-version", help="Copy selectors from this existing version as a starting point.")
    add_parser.set_defaults(func=add_version)

    validate_parser = subparsers.add_parser("validate", help="Validate selectors against a Brightway database.")
    validate_parser.add_argument("--config")
    validate_parser.add_argument("--csv")
    validate_parser.add_argument("--version")
    validate_parser.add_argument("--database")
    validate_parser.add_argument("--project")
    validate_parser.set_defaults(func=validate)

    return parser


def main():
    parsed_args = build_parser().parse_args()
    parsed_args.func(parsed_args)


if __name__ == "__main__":
    main()