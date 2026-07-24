from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from . import consts


@dataclass(frozen=True)
class WindTraceConfig:
    project_name: str
    source_database: str
    output_database: str
    biosphere_database: str
    spold_files: str
    ecoinvent_version: str
    activity_variables_csv: str


def _resolve_path(path_value: str, base_dir: Path) -> str:
    """
    Resolve relative paths relative to the config file location.
    Absolute paths are returned unchanged.
    """
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())


def load_config(config_path: str | Path) -> WindTraceConfig:
    """
    Load WindTrace user settings from a YAML config file.
    """
    config_path = Path(config_path).expanduser().resolve()
    base_dir = config_path.parent

    with open(config_path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    brightway = data["brightway"]
    ecoinvent = data["ecoinvent"]

    return WindTraceConfig(
        project_name=brightway["project_name"],
        source_database=brightway["source_database"],
        output_database=brightway["output_database"],
        biosphere_database=brightway.get("biosphere_database", "biosphere3"),
        spold_files=_resolve_path(brightway["spold_files"], base_dir),
        ecoinvent_version=str(ecoinvent["version"]),
        activity_variables_csv=_resolve_path(ecoinvent["activity_variables_csv"], base_dir),
    )


def apply_config(config: WindTraceConfig) -> None:
    """
    Apply config values to legacy constants still used by the WindTrace code.
    This keeps the package backward-compatible while avoiding manual edits to consts.py.
    """
    consts.PROJECT_NAME = config.project_name
    consts.SPOLD_FILES = config.spold_files
    consts.NEW_DB_NAME = config.output_database
    consts.DEFAULT_EI_VERSION = config.ecoinvent_version
    consts.VARIABLES_CSV_FILE = config.activity_variables_csv



def setup_brightway(config: WindTraceConfig):
    """
    Set the Brightway project and return the source ecoinvent database,
    output WindTrace database, and biosphere database.
    """
    import bw2data as bd

    bd.projects.set_current(config.project_name, update=False)

    # Check source ecoinvent database
    if config.source_database not in bd.databases:
        raise ValueError(
            f"Source database '{config.source_database}' was not found in Brightway project "
            f"'{config.project_name}'. Available databases: {list(bd.databases)}"
        )

    # Check biosphere database
    if config.biosphere_database not in bd.databases:
        raise ValueError(
            f"Biosphere database '{config.biosphere_database}' was not found in Brightway project "
            f"'{config.project_name}'. Available databases: {list(bd.databases)}"
        )

    source_db = bd.Database(config.source_database)
    biosphere_db = bd.Database(config.biosphere_database)

    # Create/register output database if missing
    if config.output_database not in bd.databases:
        print(f"Creating output database: {config.output_database}")
        output_db = bd.Database(config.output_database)
        output_db.write({})
    else:
        output_db = bd.Database(config.output_database)

    return source_db, output_db, biosphere_db