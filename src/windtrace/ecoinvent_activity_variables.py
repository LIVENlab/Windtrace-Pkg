import csv
import os
from functools import lru_cache
from typing import Dict, Iterable, Optional, Tuple

from . import consts


SELECTOR_FIELDS = ("name", "location", "reference_product")


def version_prefix(version: str) -> str:
    """Return the CSV column prefix for an ecoinvent version."""
    normalized = str(version).strip().lower()
    if normalized.startswith("ei_"):
        return normalized
    if normalized.startswith("ecoinvent_"):
        normalized = normalized[len("ecoinvent_"):]
    return "ei_" + normalized.replace(".", "_").replace("-", "_")


def version_columns(version: str) -> Tuple[str, str, str]:
    prefix = version_prefix(version)
    return tuple(f"{prefix}_{field}" for field in SELECTOR_FIELDS)


def available_versions(csv_path: Optional[str] = None) -> Iterable[str]:
    rows = _load_rows(csv_path or consts.VARIABLES_CSV_FILE)
    if not rows:
        return []
    versions = set()
    for key in rows[0]:
        if key.startswith("ei_") and key.endswith("_name"):
            versions.add(key[:-len("_name")])
    return sorted(versions)


@lru_cache(maxsize=8)
def _load_rows(csv_path: str) -> Tuple[Dict[str, str], ...]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Activity variables CSV was not found: {csv_path}. "
            "Update consts.VARIABLES_CSV_FILE or generate the table with "
            "ecoinvent_variables_updater.py."
        )
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        return tuple(csv.DictReader(handle))


def _matches(row: Dict[str, str], group: str, variable_name: str, subtype: Optional[str]) -> bool:
    if row.get("group") != group:
        return False
    if row.get("variable_name") != variable_name:
        return False
    if subtype is not None and row.get("subtype") != subtype:
        return False
    return True


def get_activity_selector(
        group: str,
        variable_name: str,
        subtype: Optional[str] = None,
        ecoinvent_version: Optional[str] = None,
        csv_path: Optional[str] = None,
        allow_empty: bool = False) -> Dict[str, Optional[str]]:
    """
    Read one activity selector from the versioned variables CSV.

    The returned dictionary uses the Brightway selector keys:
    ``name``, ``location`` and ``reference product``.
    """
    version = ecoinvent_version or consts.DEFAULT_EI_VERSION
    rows = _load_rows(csv_path or consts.VARIABLES_CSV_FILE)
    matches = [row for row in rows if _matches(row, group, variable_name, subtype)]
    if not matches:
        subtype_text = f", subtype={subtype}" if subtype is not None else ""
        raise KeyError(f"No activity variable found for group={group}, variable={variable_name}{subtype_text}")
    if len(matches) > 1:
        subtype_text = f", subtype={subtype}" if subtype is not None else ""
        raise KeyError(f"Duplicate activity variables for group={group}, variable={variable_name}{subtype_text}")

    row = matches[0]
    columns = version_columns(version)
    missing_columns = [column for column in columns if column not in row]
    if missing_columns:
        available = ", ".join(available_versions(csv_path or consts.VARIABLES_CSV_FILE))
        raise KeyError(
            f"CSV has no selector columns for ecoinvent {version}. "
            f"Missing columns: {missing_columns}. Available version prefixes: {available}"
        )

    selector = {
        "name": _clean_optional(row[columns[0]]),
        "location": _clean_optional(row[columns[1]]),
        "reference product": _clean_optional(row[columns[2]]),
    }
    if not allow_empty and any(value is None for value in selector.values()):
        raise ValueError(
            f"Activity variable {group}/{variable_name}"
            f"{'/' + subtype if subtype else ''} has an empty selector for ecoinvent {version}."
        )
    return selector


def find_activity(
        index: dict,
        database,
        group: str,
        variable_name: str,
        subtype: Optional[str] = None,
        ecoinvent_version: Optional[str] = None,
        csv_path: Optional[str] = None,
        allow_empty: bool = False):
    selector = get_activity_selector(
        group=group,
        variable_name=variable_name,
        subtype=subtype,
        ecoinvent_version=ecoinvent_version,
        allow_empty=allow_empty,
    )
    if any(value is None for value in selector.values()):
        return None
    return _find_unique_act(
        index=index,
        database=database,
        name=selector["name"],
        location=selector["location"],
        reference_product=selector["reference product"],
    )


def get_activity_group(
        group: str,
        ecoinvent_version: Optional[str] = None,
        csv_path: Optional[str] = None) -> Dict[str, Dict[str, Optional[str]]]:
    """Return all selectors in a group as a dictionary keyed by variable name."""
    version = ecoinvent_version or consts.DEFAULT_EI_VERSION
    rows = _load_rows(csv_path or consts.VARIABLES_CSV_FILE)
    result = {}
    for row in rows:
        if row.get("group") != group:
            continue
        variable_name = row["variable_name"]
        subtype = row.get("subtype") or None
        selector = get_activity_selector(
            group=group,
            variable_name=variable_name,
            subtype=subtype,
            ecoinvent_version=version,
            csv_path=csv_path,
            allow_empty=True,
        )
        if subtype:
            result.setdefault(variable_name, {})[subtype] = selector
        else:
            result[variable_name] = selector
    return result


def get_steel_country_data(
        ecoinvent_version: Optional[str] = None,
        csv_path: Optional[str] = None) -> Dict[str, Dict[str, Dict[str, Optional[str]]]]:
    """Return the previous STEEL_DATA_EU27 structure, populated from the CSV."""
    version = ecoinvent_version or consts.DEFAULT_EI_VERSION
    rows = _load_rows(csv_path or consts.VARIABLES_CSV_FILE)
    result = {}
    for row in rows:
        group = row.get("group")
        if group not in {"steel_electricity", "steel_gas"}:
            continue
        country = row["variable_name"]
        result.setdefault(country, {"share": float(row["share"])})
        selector = get_activity_selector(
            group=group,
            variable_name=country,
            ecoinvent_version=version,
            csv_path=csv_path,
        )
        result[country]["elect" if group == "steel_electricity" else "gas"] = selector
    return result


def iter_steel_country_selectors(
        group: str,
        ecoinvent_version: Optional[str] = None,
        csv_path: Optional[str] = None):
    """Yield country, share and selector rows for steel electricity or gas mixes."""
    version = ecoinvent_version or consts.DEFAULT_EI_VERSION
    rows = _load_rows(csv_path or consts.VARIABLES_CSV_FILE)
    for row in rows:
        if row.get("group") != group:
            continue
        selector = get_activity_selector(
            group=group,
            variable_name=row["variable_name"],
            subtype=row.get("subtype") or None,
            ecoinvent_version=version,
            csv_path=csv_path,
        )
        yield row["variable_name"], float(row["share"]), selector


def _clean_optional(value: str) -> Optional[str]:
    text = str(value).strip()
    if text == "" or text.lower() in {"none", "nan"}:
        return None
    return text


def _find_unique_act(index: dict, database, name: str, location: str, reference_product: str):
    lookup = (name, location, reference_product)
    key = index.get(lookup)
    if key is None:
        raise ValueError(
            "\nMissing Ecoinvent activity from variables CSV:\n"
            f"  name: {name}\n"
            f"  location: {location}\n"
            f"  reference product: {reference_product}\n"
        )
    return database.get(key[1])
