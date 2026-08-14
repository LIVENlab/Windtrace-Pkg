"""Parametric life-cycle inventories for offshore wind turbines and parks.

This module extends :mod:`windtrace.onshore` without performing Brightway
setup at import time. The caller supplies the source, output, and biosphere
databases, as for the onshore model.

Engineering equations originate in the historical ``offshore`` branch of
``WindTrace_public``. Their Brightway integration has been rewritten for the
installable package: databases are explicit, ecoinvent activities use the
versioned selector table where possible, and no local project or data path is
hard-coded.

Distances are kilometres, dimensions are metres, power is MW, and masses are
kilograms unless documented otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional, Sequence

import bw2data as bd
import numpy as np
from geopy.distance import geodesic
from stats_arrays import NormalUncertainty, UniformUncertainty

from . import consts
from .ecoinvent_activity_variables import get_activity_group, get_activity_selector
from .onshore import (
    build_bw_index,
    find_unique_act,
    manipulate_steel_activities,
    materials_mass,
    mva500_transformer,
)


FoundationType = Literal["monopile", "gravity", "tripod", "floating"]
FloatingPlatformType = Literal[
    "semi_sub", "spar_buoy_concrete", "spar_buoy_iron",
    "spar_buoy_steel", "tension_leg", "barge",
]
GeneratorType = Literal["dd_eesg", "dd_pmsg", "gb_pmsg", "gb_dfig"]
ElectricityMix = Literal["Norway", "Europe", "Poland"]
RegressionAdjustment = Literal["D2h", "Hub height"]

FOUNDATION_TYPES = {"monopile", "gravity", "tripod", "floating"}
FLOATING_PLATFORM_TYPES = {
    "semi_sub", "spar_buoy_concrete", "spar_buoy_iron",
    "spar_buoy_steel", "tension_leg", "barge",
}
CONCRETE_DENSITY_KG_M3 = 2400.0
GRAVEL_DENSITY_KG_M3 = 1680.0

# Verified metadata for the activities and biosphere flows that were referenced
# only by code in the historical ecoinvent 3.9.1 offshore implementation. The
# activity codes remain compatibility fallbacks; version-specific selectors in
# the activity variables CSV take precedence.
EI391_IRON_ORE = {
    "code": "e0ad78b195d3be413c9b5792339382b9",
    "name": "market for iron ore concentrate",
    "location": "GLO",
    "reference product": "iron ore concentrate",
}
EI391_VESSEL = {
    "code": "150cb5f77b0346f4f65ba8ec9c178aff",
    "name": "transport, freight, sea, ferry",
    "location": "GLO",
    "reference product": "transport, freight, sea, ferry",
}

BIOSPHERE_FLOWS = {
    "water_unspecified_in_ground": {
        "code": "478e8437-1c21-4032-8438-872a6b5ddcdf",
        "name": "Water, unspecified natural origin",
        "unit": "cubic meter",
        "type": "natural resource",
        "categories": ("natural resource", "in ground"),
    },
    "seabed_occupation_infrastructure": {
        "code": "9db06277-b6d9-4c48-8cfb-de342e928a50",
        "name": "Occupation, seabed, infrastructure",
        "unit": "square meter-year",
        "type": "natural resource",
        "categories": ("natural resource", "land"),
    },
    "seabed_transformation_from_unspecified": {
        "code": "928ba839-d6e5-4d1e-b5fd-122998a9bbe2",
        "name": "Transformation, from seabed, unspecified",
        "unit": "square meter",
        "type": "natural resource",
        "categories": ("natural resource", "land"),
    },
    "seabed_transformation_to_infrastructure": {
        "code": "c7d2cf2d-0d21-45f7-9769-b07f3e53b76a",
        "name": "Transformation, to seabed, infrastructure",
        "unit": "square meter",
        "type": "natural resource",
        "categories": ("natural resource", "land"),
    },
}


@dataclass(frozen=True)
class OffshoreContext:
    """Runtime objects shared by offshore inventory builders."""

    new_db: bd.Database
    source_db: bd.Database
    biosphere_db: bd.Database
    ei_index: dict
    ecoinvent_version: str
    activity_variables_csv: str
    materials: Mapping[str, Mapping[str, Optional[str]]]
    processing: Mapping[str, Mapping[str, Optional[str]]]
    eol: Mapping[str, Mapping[str, Mapping[str, Optional[str]]]]


def _make_context(
    new_db: bd.Database,
    cutoff391: bd.Database,
    biosphere3: bd.Database,
    ecoinvent_version: Optional[str],
    activity_variables_csv: Optional[str],
) -> OffshoreContext:
    version = ecoinvent_version or consts.DEFAULT_EI_VERSION
    csv_path = activity_variables_csv or consts.VARIABLES_CSV_FILE
    return OffshoreContext(
        new_db=new_db,
        source_db=cutoff391,
        biosphere_db=biosphere3,
        ei_index=build_bw_index(cutoff391),
        ecoinvent_version=version,
        activity_variables_csv=csv_path,
        materials=get_activity_group("materials", version, csv_path=csv_path),
        processing=get_activity_group("processing", version, csv_path=csv_path),
        eol=get_activity_group("eol", version, csv_path=csv_path),
    )


def _new_activity(
    ctx: OffshoreContext,
    code: str,
    name: str,
    reference_product: str,
    location: str,
    unit: str = "unit",
    comment: str = "",
):
    try:
        existing = ctx.new_db.get(code)
    except Exception:
        existing = None
    if existing is not None:
        raise ValueError(
            f"Activity '{code}' already exists in '{ctx.new_db.name}'. "
            "Use another park_name or remove the previous inventory."
        )
    activity = ctx.new_db.new_activity(
        code=code, name=name, location=location, unit=unit, comment=comment
    )
    activity["reference product"] = reference_product
    activity.save()
    production = activity.new_exchange(
        input=activity.key, amount=1.0, unit=unit, type="production"
    )
    production.save()
    return activity


def _link(activity, input_activity, amount: float = 1.0, unit: Optional[str] = None):
    kwargs = {"input": input_activity, "amount": amount, "type": "technosphere"}
    if unit:
        kwargs["unit"] = unit
    exchange = activity.new_exchange(**kwargs)
    exchange.save()
    return exchange


def _activity_from_selector(ctx: OffshoreContext, selector: Mapping[str, Optional[str]]):
    name = selector.get("name")
    location = selector.get("location")
    reference_product = selector.get("reference product")
    if not name or not location or not reference_product:
        raise ValueError(f"Incomplete ecoinvent selector: {selector}")
    return find_unique_act(
        index=ctx.ei_index,
        database=ctx.source_db,
        name=name,
        location=location,
        reference_product=reference_product,
    )


def _verified_code_lookup(database, metadata: Mapping[str, Any], description: str):
    """Get an object by code and verify that the code still has the expected meaning."""
    code = metadata["code"]
    try:
        obj = database.get(code)
    except Exception as exc:
        raise ValueError(
            f"Required {description} '{metadata['name']}' ({code}) was not found "
            f"in database '{database.name}'."
        ) from exc

    mismatches = []
    for field, expected in metadata.items():
        if field == "code":
            continue
        actual = obj.get(field)
        if field == "categories" and actual is not None:
            actual = tuple(actual)
        if actual != expected:
            mismatches.append(f"{field}={actual!r}, expected {expected!r}")
    if mismatches:
        raise ValueError(
            f"Code '{code}' in database '{database.name}' does not match the "
            f"expected {description} metadata: {'; '.join(mismatches)}"
        )
    return obj


def _named_activity(
    ctx: OffshoreContext,
    *,
    logical_name: str,
    exact_names: Sequence[str],
    reference_products: Sequence[str] = (),
    exact_locations: Sequence[str] = (),
    preferred_locations: Sequence[str] = (
        "GLO", "RER", "Europe without Switzerland", "RoW"
    ),
    legacy_selector: Optional[Mapping[str, Any]] = None,
):
    """Resolve an offshore-only activity without silently choosing ambiguity."""
    try:
        selector = get_activity_selector(
            group="offshore",
            variable_name=logical_name,
            ecoinvent_version=ctx.ecoinvent_version,
            csv_path=ctx.activity_variables_csv,
        )
        return _activity_from_selector(ctx, selector)
    except (KeyError, ValueError):
        pass

    candidates = []
    for activity in ctx.source_db:
        data = activity._data
        if data.get("name") not in exact_names:
            continue
        if reference_products and data.get("reference product") not in reference_products:
            continue
        if exact_locations and data.get("location") not in exact_locations:
            continue
        candidates.append(activity)
    if len(candidates) > 1:
        for location in preferred_locations:
            located = [a for a in candidates if a._data.get("location") == location]
            if len(located) == 1:
                return located[0]
    if len(candidates) == 1:
        return candidates[0]
    if legacy_selector:
        return _verified_code_lookup(
            ctx.source_db,
            legacy_selector,
            f"ecoinvent {ctx.ecoinvent_version} activity",
        )
    raise ValueError(
        f"Could not uniquely resolve offshore activity '{logical_name}' for "
        f"ecoinvent {ctx.ecoinvent_version}. Add an 'offshore' selector row "
        "or pass the Brightway activity explicitly."
    )


EXTRA_MATERIAL_SELECTORS = {
    "Gravel": (("market for gravel, round", "gravel, round"),
               ("market for gravel", "gravel")),
    "Cement": (("market for cement, Portland", "cement, Portland"),),
    "Lead": (("market for lead", "lead"),),
    "Paper": (("market for kraft paper", "kraft paper"),),
    "PP": (("market for polypropylene, granulate", "polypropylene, granulate"),),
    "Asphalt": (("market for bitumen seal", "bitumen seal"),),
}


def _material_activity(ctx: OffshoreContext, material: str):
    common_name = {"hdpe": "PE"}.get(material, material)
    selector = ctx.materials.get(common_name)
    if selector:
        return _activity_from_selector(ctx, selector)
    pairs = EXTRA_MATERIAL_SELECTORS.get(material)
    if not pairs:
        raise KeyError(f"No selector is defined for offshore material '{material}'.")
    return _named_activity(
        ctx,
        logical_name=f"material_{material.lower()}",
        exact_names=[pair[0] for pair in pairs],
        reference_products=[pair[1] for pair in pairs],
    )


def _processing_activity(ctx: OffshoreContext, variable_name: str):
    try:
        return _activity_from_selector(ctx, ctx.processing[variable_name])
    except KeyError as exc:
        raise KeyError(f"Missing processing selector '{variable_name}'.") from exc


def _steel_activity(
    ctx: OffshoreContext,
    commissioning_year: int,
    recycled_share_steel: Optional[float],
    electricity_mix_steel: Optional[ElectricityMix],
):
    steel, chromium = manipulate_steel_activities(
        new_db=ctx.new_db,
        cutoff391=ctx.source_db,
        ei_index=ctx.ei_index,
        commissioning_year=commissioning_year,
        recycled_share=recycled_share_steel,
        electricity_mix=electricity_mix_steel,
        printed_warning=consts.PRINTED_WARNING_STEEL,
        ecoinvent_version=ctx.ecoinvent_version,
        activity_variables_csv=ctx.activity_variables_csv,
    )
    consts.PRINTED_WARNING_STEEL = True
    return steel, chromium


def _add_uncertainty(exchange, location: float, scale: float, uniform: bool = False):
    if scale <= 0:
        return
    exchange["uncertainty type"] = (
        UniformUncertainty.id if uniform else NormalUncertainty.id
    )
    exchange["loc"] = location
    exchange["scale"] = scale
    exchange["minimum"] = 0
    exchange.save()


def monopile_materials(sea_depth_m: float, turbine_power_mw: float) -> dict[str, float]:
    """Return monopile, transition-piece, grout, and scour materials in kg."""
    power_kw = turbine_power_mw * 1000
    pile_length = 9 + 3 * turbine_power_mw + sea_depth_m
    transition_length = 0.367 * pile_length + 1.147
    transition_mass = max(0.0, (15.23 * transition_length - 73.86) * 1000)
    grout_mass = max(0.0, 2.93 * transition_length - 27.54) * CONCRETE_DENSITY_KG_M3
    scour_mass = (0.192 * power_kw + 1643) * GRAVEL_DENSITY_KG_M3
    diameter_fit = np.poly1d(
        np.polyfit([3000, 3600, 4000, 8000, 10000], [5, 5.5, 5.75, 6.75, 7.75], 1)
    )
    outer_diameter = float(diameter_fit(power_kw))
    thickness = float(np.interp(
        power_kw,
        [2000, 3000, 3600, 4000, 8000, 10000],
        [0.07, 0.10, 0.13, 0.16, 0.19, 0.22],
    ))
    inner_diameter = max(0.0, outer_diameter - 2 * thickness)
    steel_volume = np.pi / 4 * (outer_diameter**2 - inner_diameter**2) * pile_length
    return {
        "Low alloy steel": transition_mass + 8000 * steel_volume,
        "Cement": grout_mass,
        "Gravel": scour_mass,
    }


def gravity_materials(sea_depth_m: float, turbine_power_mw: float) -> dict[str, float]:
    """Return gravity-foundation materials in kg, scaled from a 3 MW case."""
    scale = turbine_power_mw / 3.0
    transition_length = 0.367 * (9 + sea_depth_m) + 1.147
    transition_steel = max(0.0, (15.23 * transition_length - 73.86) * 1000)
    return {
        "Low alloy steel": (336000 + transition_steel) * scale,
        "Concrete_foundations": 1027 * CONCRETE_DENSITY_KG_M3 * scale,
        "Gravel": 12200000 * scale,
    }


def tripod_materials(sea_depth_m: float, turbine_power_mw: float) -> dict[str, float]:
    """Return tripod-foundation materials in kg, scaled from a 3 MW case."""
    power_kw = turbine_power_mw * 1000
    # The historical branch had the intercept and slope reversed, producing
    # penetration depths of tens of kilometres.
    penetration_depth = 19.4002294 + 0.000944015847 * power_kw
    transition_length = 0.367 * (9 + penetration_depth + sea_depth_m) + 1.147
    transition_steel = max(0.0, (15.23 * transition_length - 73.86) * 1000)
    scale = turbine_power_mw / 3.0
    return {
        "Low alloy steel": (807000 + 847000 + transition_steel) * scale,
        "Concrete_foundations": 63900 * scale,
    }


FLOATING_INTENSITIES_KG_PER_MW = {
    "semi_sub": {"Low alloy steel": (479892.33, 66723.18),
                 "Concrete_foundations": (7629.84, 13215.27),
                 "Cast iron": (40388.33, 69954.65), "hdpe": (0.0, 0.0)},
    "spar_buoy_concrete": {"Low alloy steel": (159477.81, 98377.13),
                           "Concrete_foundations": (835105.52, 98377.13),
                           "Cast iron": (0.0, 0.0), "hdpe": (0.0, 0.0)},
    "spar_buoy_iron": {"Low alloy steel": (585909.33, 0.0),
                       "Concrete_foundations": (0.0, 0.0),
                       "Cast iron": (832757.33, 0.0), "hdpe": (0.0, 0.0)},
    "spar_buoy_steel": {"Low alloy steel": (257585.67, 11326.45),
                        "Concrete_foundations": (6539.33, 11326.45),
                        "Cast iron": (0.0, 0.0), "hdpe": (0.0, 0.0)},
    "tension_leg": {"Low alloy steel": (180230.56, 11081.93),
                    "Concrete_foundations": (0.0, 0.0),
                    "Cast iron": (0.0, 0.0), "hdpe": (13668.51, 11081.93)},
    "barge": {"Low alloy steel": (456250.0, 0.0),
              "Concrete_foundations": (2175000.0, 0.0),
              "Cast iron": (30000.0, 0.0), "hdpe": (0.0, 0.0)},
}


def floating_materials(
    turbine_power_mw: float,
    platform_type: FloatingPlatformType,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return floating-platform masses and standard deviations in kg."""
    if platform_type not in FLOATING_PLATFORM_TYPES:
        raise ValueError(f"Unknown floating platform type: {platform_type}")
    data = FLOATING_INTENSITIES_KG_PER_MW[platform_type]
    return (
        {name: values[0] * turbine_power_mw for name, values in data.items()},
        {name: values[1] * turbine_power_mw for name, values in data.items()},
    )


def submarine_cable_materials(
    rotor_diameter_m: float,
    distance_to_shore_km: float,
    number_of_turbines: int,
) -> dict[str, float]:
    """Return intra-array and export-cable materials for one park in kg."""
    if number_of_turbines < 1:
        raise ValueError("number_of_turbines must be at least one")
    mvac_120 = {"Aluminium": 0.97, "hdpe": 5.0, "Lead": 6.4, "Low alloy steel": 7.6}
    mvac_500 = {"Aluminium": 4.0, "hdpe": 11.0, "Lead": 16.0, "Low alloy steel": 19.0}
    hvdc = {"Copper": 17.8, "Paper": 6.1, "Lubricating oil": 4.7,
            "Lead": 17.2, "Low alloy steel": 19.2, "Asphalt": 0.73, "PP": 2.2}
    intra_length_m = 7.7 * rotor_diameter_m * max(number_of_turbines - 1, 0)
    export_length_m = distance_to_shore_km * 1000
    output = {
        material: intra_length_m * (0.35 * mvac_120[material] + 0.65 * mvac_500[material])
        for material in mvac_120
    }
    for material, intensity in hvdc.items():
        output[material] = output.get(material, 0.0) + export_length_m * intensity
    return output


def _create_material_activity(
    ctx: OffshoreContext,
    *,
    code: str,
    reference_product: str,
    location: str,
    masses_kg: Mapping[str, float],
    commissioning_year: int,
    recycled_share_steel: Optional[float],
    electricity_mix_steel: Optional[ElectricityMix],
    standard_deviations_kg: Optional[Mapping[str, float]] = None,
):
    activity = _new_activity(ctx, code, code, reference_product, location)
    steel_market = None
    for material, mass in masses_kg.items():
        if mass <= 0:
            continue
        if material == "Low alloy steel":
            if steel_market is None:
                steel_market, _ = _steel_activity(
                    ctx, commissioning_year, recycled_share_steel, electricity_mix_steel
                )
            input_activity, amount, unit = steel_market, mass, "kilogram"
        elif material == "Concrete_foundations":
            input_activity = _material_activity(ctx, material)
            amount, unit = mass / CONCRETE_DENSITY_KG_M3, "cubic meter"
        else:
            input_activity = _material_activity(ctx, material)
            amount, unit = mass, "kilogram"
        exchange = _link(activity, input_activity, amount, unit)
        if standard_deviations_kg:
            std = standard_deviations_kg.get(material, 0.0)
            if material == "Concrete_foundations":
                std /= CONCRETE_DENSITY_KG_M3
            _add_uncertainty(exchange, amount, std)
    return activity


def _create_processing_activity(
    ctx: OffshoreContext,
    *,
    code: str,
    reference_product: str,
    location: str,
    masses_kg: Mapping[str, float],
):
    activity = _new_activity(ctx, code, code, reference_product, location)
    for material, mass in masses_kg.items():
        if mass <= 0:
            continue
        if material in {"Low alloy steel", "Cast iron"}:
            process = _processing_activity(ctx, "Steel_tower_rolling")
        elif material in {"hdpe", "PP", "Asphalt"}:
            process = _processing_activity(ctx, "PVC")
        elif material in {"Copper", "Aluminium", "Lead"}:
            process = _processing_activity(ctx, "Copper")
        else:
            continue
        _link(activity, process, mass)
    return activity


def _create_turbine_materials_and_manufacturing(
    ctx: OffshoreContext,
    *,
    park_name: str,
    park_location: str,
    park_coordinates: tuple,
    manufacturer: str,
    rotor_diameter: float,
    turbine_power: float,
    hub_height: float,
    commissioning_year: int,
    generator_type: GeneratorType,
    recycled_share_steel: Optional[float],
    electricity_mix_steel: Optional[ElectricityMix],
    regression_adjustment: RegressionAdjustment,
):
    masses, uncertainty = materials_mass(
        generator_type=generator_type,
        turbine_power=turbine_power,
        hub_height=hub_height,
        rotor_diameter=rotor_diameter,
        regression_adjustment=regression_adjustment,
    )
    excluded = {
        "Low alloy steel_foundations",
        "Chromium steel_foundations",
        "Concrete_foundations",
    }
    masses = {key: value for key, value in masses.items() if key not in excluded}
    uncertainty = {key: value for key, value in uncertainty.items() if key not in excluded}

    materials_activity = _new_activity(
        ctx,
        f"{park_name}_offshore_turbine_materials",
        f"{park_name}_offshore_turbine_materials",
        "offshore wind turbine, materials excluding foundation",
        park_location,
    )
    steel_market = None
    chromium_market = None
    for material, mass in masses.items():
        if mass <= 0:
            continue
        if material == "Low alloy steel":
            steel_market, chromium = _steel_activity(
                ctx, commissioning_year, recycled_share_steel, electricity_mix_steel
            )
            chromium_market = chromium[0] if chromium else None
            input_activity = steel_market
        elif material == "Chromium steel" and chromium_market is not None:
            input_activity = chromium_market
        else:
            input_activity = _material_activity(ctx, material)
        amount = mass * 1.1 if material == "Fiberglass" else mass
        exchange = _link(materials_activity, input_activity, amount, "kilogram")
        _add_uncertainty(
            exchange,
            amount,
            uncertainty.get(material, 0.0) * 1000,
            uniform=material == "Low alloy steel",
        )

    manufacturing = _new_activity(
        ctx,
        f"{park_name}_offshore_turbine_manufacturing",
        f"{park_name}_offshore_turbine_manufacturing",
        "offshore wind turbine, manufacturing excluding foundation",
        park_location,
    )
    process_map = {
        "Low alloy steel": "Steel_tower_rolling",
        "Chromium steel": "Chromium steel",
        "Cast iron": "Cast iron",
        "Aluminium": "Aluminium",
        "Copper": "Copper",
    }
    for material, process_name in process_map.items():
        if masses.get(material, 0) > 0:
            _link(manufacturing, _processing_activity(ctx, process_name), masses[material])
    _link(manufacturing, _processing_activity(ctx, "Steel_tower_welding"), hub_height * 2)

    diameter_fit = np.poly1d(
        np.polyfit([3, 3.6, 4, 8, 10], [5, 5.5, 5.75, 6.75, 7.75], 1)
    )
    tower_surface = np.pi * float(diameter_fit(turbine_power)) * hub_height
    _link(manufacturing, _processing_activity(ctx, "Zinc coating"), tower_surface)

    selected_manufacturer = manufacturer if manufacturer in consts.MANUFACTURER_LOC else "LM Wind"
    sites = consts.MANUFACTURER_LOC[selected_manufacturer]
    closest = min(
        sites.values(),
        key=lambda site: geodesic(park_coordinates, site["location"]).kilometers,
    )
    country = closest["country"]
    electricity_matches = [
        activity for activity in ctx.source_db
        if "market for electricity, low voltage" in activity._data.get("name", "")
        and activity._data.get("location") == country
    ]
    if len(electricity_matches) != 1:
        raise ValueError(
            f"Expected one low-voltage electricity market for {country}; "
            f"found {len(electricity_matches)}."
        )
    electricity_fit = np.poly1d(
        np.polyfit([0.03, 0.15, 0.6, 0.8, 2], [575, 3987, 17510, 17510, 67500], 1)
    )
    _link(
        manufacturing,
        electricity_matches[0],
        float(electricity_fit(turbine_power)),
        "kilowatt hour",
    )
    return materials_activity, manufacturing, masses


def _foundation_masses(
    foundation_type: FoundationType,
    sea_depth_m: float,
    turbine_power_mw: float,
    floating_platform: Optional[FloatingPlatformType],
) -> tuple[dict[str, float], dict[str, float]]:
    if foundation_type == "monopile":
        return monopile_materials(sea_depth_m, turbine_power_mw), {}
    if foundation_type == "gravity":
        return gravity_materials(sea_depth_m, turbine_power_mw), {}
    if foundation_type == "tripod":
        return tripod_materials(sea_depth_m, turbine_power_mw), {}
    if foundation_type == "floating":
        if floating_platform is None:
            raise ValueError("floating_platform is required for a floating foundation.")
        return floating_materials(turbine_power_mw, floating_platform)
    raise ValueError(f"Unknown foundation_type: {foundation_type}")


def _create_foundation(
    ctx: OffshoreContext,
    *,
    park_name: str,
    park_location: str,
    foundation_type: FoundationType,
    floating_platform: Optional[FloatingPlatformType],
    sea_depth_m: float,
    turbine_power_mw: float,
    commissioning_year: int,
    recycled_share_steel: Optional[float],
    electricity_mix_steel: Optional[ElectricityMix],
):
    masses, deviations = _foundation_masses(
        foundation_type, sea_depth_m, turbine_power_mw, floating_platform
    )
    subtype = floating_platform if foundation_type == "floating" else foundation_type
    activity = _create_material_activity(
        ctx,
        code=f"{park_name}_offshore_foundation_materials",
        reference_product=f"offshore wind turbine foundation, {subtype}",
        location=park_location,
        masses_kg=masses,
        commissioning_year=commissioning_year,
        recycled_share_steel=recycled_share_steel,
        electricity_mix_steel=electricity_mix_steel,
        standard_deviations_kg=deviations,
    )
    manufacturing = _create_processing_activity(
        ctx,
        code=f"{park_name}_offshore_foundation_manufacturing",
        reference_product=f"offshore wind turbine foundation manufacturing, {subtype}",
        location=park_location,
        masses_kg=masses,
    )
    return activity, manufacturing, masses


def _eol_treatment(ctx: OffshoreContext, material: str, treatment: str):
    aliases = {
        "hdpe": "PE", "PP": "PE",
        "Cement": "Concrete_foundations", "Gravel": "Concrete_foundations",
        "Lead": "electronics", "Paper": "electronics", "Asphalt": "electronics",
    }
    key = aliases.get(material, material)
    try:
        selector = ctx.eol[key][treatment]
    except KeyError as exc:
        raise KeyError(f"Missing {treatment} EoL selector for '{material}'.") from exc
    return _activity_from_selector(ctx, selector)


def _create_material_eol(
    ctx: OffshoreContext,
    *,
    code: str,
    reference_product: str,
    location: str,
    masses_kg: Mapping[str, float],
    scenario: int,
):
    if scenario not in {1, 2, 3, 4}:
        raise ValueError("eol_scenario must be one of 1, 2, 3, or 4")
    activity = _new_activity(ctx, code, code, reference_product, location)
    ferrous = {"Low alloy steel", "Chromium steel", "Cast iron"}
    rare_earths = {"Praseodymium", "Neodymium", "Dysprosium", "Terbium", "Boron"}
    plastics = {"Rubber", "PUR", "PVC", "PE", "hdpe", "PP"}
    for material, mass in masses_kg.items():
        if mass <= 0:
            continue
        if material in ferrous:
            rate = 0.9 if scenario in {1, 2, 4} else 0.52
            treatment, amount = "landfill", -mass * (1 - rate)
        elif material == "Copper":
            rate = {1: 0.9, 2: 0.53, 3: 0.42, 4: 0.9}[scenario]
            treatment, amount = "landfill", -mass * (1 - rate)
        elif material == "Aluminium":
            rate = {1: 0.9, 2: 0.7, 3: 0.42, 4: 0.9}[scenario]
            treatment, amount = "landfill", -mass * (1 - rate)
        elif material in rare_earths:
            rate = {1: 0.0, 2: 0.21, 3: 0.01, 4: 0.7}[scenario]
            treatment, amount = "landfill", -mass * (1 - rate)
        elif material in plastics:
            treatment, amount = "incineration", -mass
        elif material in {"Epoxy resin", "Fiberglass"}:
            treatment, amount = "incineration", -mass * (0.3 if scenario == 4 else 1.0)
        elif material in {"Lubricating oil", "Ethyleneglycol"}:
            treatment, amount = "incineration", -mass
        elif material in {"Concrete_foundations", "Cement", "Gravel"}:
            treatment, amount = "landfill", -mass * (0.5 if scenario == 4 else 1.0)
        else:
            treatment, amount = "landfill", -mass * (0.5 if scenario == 4 else 1.0)
        _link(activity, _eol_treatment(ctx, material, treatment), amount, "kilogram")
    return activity


def _resolve_vessel(ctx: OffshoreContext, vessel_activity=None):
    if vessel_activity is not None:
        return vessel_activity
    return _named_activity(
        ctx,
        logical_name="vessel_operations",
        exact_names=(EI391_VESSEL["name"],),
        reference_products=(EI391_VESSEL["reference product"],),
        exact_locations=(EI391_VESSEL["location"],),
        preferred_locations=(EI391_VESSEL["location"],),
        legacy_selector=EI391_VESSEL,
    )


def _create_vessel_stage(
    ctx: OffshoreContext,
    *,
    code: str,
    reference_product: str,
    location: str,
    vessel_activity,
    amount: float,
):
    activity = _new_activity(ctx, code, code, reference_product, location)
    _link(activity, vessel_activity, amount)
    return activity


def _create_installation(
    ctx: OffshoreContext,
    *,
    park_name: str,
    park_location: str,
    turbine_power_mw: float,
    lifetime_years: int,
    foundation_type: FoundationType,
    vessel_activity,
    vessel_amount: float,
):
    activity = _create_vessel_stage(
        ctx,
        code=f"{park_name}_offshore_installation",
        reference_product="offshore wind turbine, installation",
        location=park_location,
        vessel_activity=vessel_activity,
        amount=vessel_amount,
    )
    intensities = {
        "monopile": 291.34 / 3,
        "gravity": 1194.59 / 3,
        "tripod": 763.41 / 3,
        "floating": 0.0,
    }
    area = intensities[foundation_type] * turbine_power_mw
    flows = (
        ("seabed_transformation_from_unspecified", area),
        ("seabed_transformation_to_infrastructure", area),
        ("seabed_occupation_infrastructure", area * lifetime_years),
    )
    for flow_name, amount in flows:
        if amount == 0:
            continue
        flow = _verified_code_lookup(
            ctx.biosphere_db,
            BIOSPHERE_FLOWS[flow_name],
            "biosphere flow",
        )
        exchange = activity.new_exchange(input=flow, type="biosphere", amount=amount)
        exchange.save()
    return activity


def _create_substation_materials(
    ctx: OffshoreContext,
    *,
    park_name: str,
    park_location: str,
    commissioning_year: int,
    recycled_share_steel: Optional[float],
    electricity_mix_steel: Optional[ElectricityMix],
    iron_ore_activity=None,
):
    masses = {"Low alloy steel": 4014000.0, "Iron ore concentrate": 2540000.0}
    activity = _new_activity(
        ctx,
        f"{park_name}_offshore_substation_materials",
        f"{park_name}_offshore_substation_materials",
        "offshore substation, materials",
        park_location,
    )
    steel, _ = _steel_activity(
        ctx, commissioning_year, recycled_share_steel, electricity_mix_steel
    )
    _link(activity, steel, masses["Low alloy steel"], "kilogram")
    iron = iron_ore_activity or _named_activity(
        ctx,
        logical_name="iron_ore_concentrate",
        exact_names=(EI391_IRON_ORE["name"],),
        reference_products=(EI391_IRON_ORE["reference product"],),
        exact_locations=(EI391_IRON_ORE["location"],),
        preferred_locations=(EI391_IRON_ORE["location"],),
        legacy_selector=EI391_IRON_ORE,
    )
    _link(activity, iron, masses["Iron ore concentrate"], "kilogram")
    water = _verified_code_lookup(
        ctx.biosphere_db,
        BIOSPHERE_FLOWS["water_unspecified_in_ground"],
        "biosphere flow",
    )
    exchange = activity.new_exchange(
        input=water, type="biosphere", amount=11300000.0 / 1000, unit="cubic meter"
    )
    exchange.save()
    return activity, masses


def _create_component(
    ctx: OffshoreContext,
    *,
    code: str,
    reference_product: str,
    location: str,
    inputs: Sequence[Any],
):
    activity = _new_activity(ctx, code, code, reference_product, location)
    for input_activity in inputs:
        _link(activity, input_activity)
    return activity


def _build_offshore_turbine(
    ctx: OffshoreContext,
    *,
    park_name: str,
    park_location: str,
    park_coordinates: tuple,
    manufacturer: str,
    rotor_diameter: float,
    turbine_power: float,
    hub_height: float,
    commissioning_year: int,
    foundation_type: FoundationType,
    sea_depth: float,
    distance_to_shore: float,
    floating_platform: Optional[FloatingPlatformType],
    recycled_share_steel: Optional[float],
    electricity_mix_steel: Optional[ElectricityMix],
    generator_type: GeneratorType,
    lifetime: int,
    eol_scenario: int,
    regression_adjustment: RegressionAdjustment,
    vessel_activity=None,
):
    turbine_materials, turbine_manufacturing, turbine_masses = (
        _create_turbine_materials_and_manufacturing(
            ctx,
            park_name=park_name,
            park_location=park_location,
            park_coordinates=park_coordinates,
            manufacturer=manufacturer,
            rotor_diameter=rotor_diameter,
            turbine_power=turbine_power,
            hub_height=hub_height,
            commissioning_year=commissioning_year,
            generator_type=generator_type,
            recycled_share_steel=recycled_share_steel,
            electricity_mix_steel=electricity_mix_steel,
            regression_adjustment=regression_adjustment,
        )
    )
    foundation, foundation_manufacturing, foundation_masses = _create_foundation(
        ctx,
        park_name=park_name,
        park_location=park_location,
        foundation_type=foundation_type,
        floating_platform=floating_platform,
        sea_depth_m=sea_depth,
        turbine_power_mw=turbine_power,
        commissioning_year=commissioning_year,
        recycled_share_steel=recycled_share_steel,
        electricity_mix_steel=electricity_mix_steel,
    )
    turbine_eol = _create_material_eol(
        ctx,
        code=f"{park_name}_offshore_turbine_material_eol",
        reference_product="offshore wind turbine materials, end of life",
        location=park_location,
        masses_kg=turbine_masses,
        scenario=eol_scenario,
    )
    foundation_eol = _create_material_eol(
        ctx,
        code=f"{park_name}_offshore_foundation_eol",
        reference_product="offshore wind turbine foundation, end of life",
        location=park_location,
        masses_kg=foundation_masses,
        scenario=eol_scenario,
    )

    vessel = _resolve_vessel(ctx, vessel_activity)
    total_mass_kg = sum(turbine_masses.values()) + sum(foundation_masses.values())
    transport_amount = (
        7842117.12 / (43575 * 25) * total_mass_kg / 1000 * distance_to_shore
    )
    installation_amount = 58696743.55 / 43575 * total_mass_kg / 1000
    maintenance_amount = 61059273.48 / (25 * 5) * lifetime
    decommissioning_amount = 58696743.55 / 43575 * total_mass_kg / 1000
    transport = _create_vessel_stage(
        ctx,
        code=f"{park_name}_offshore_transport",
        reference_product="offshore wind turbine, transport",
        location=park_location,
        vessel_activity=vessel,
        amount=transport_amount,
    )
    installation = _create_installation(
        ctx,
        park_name=park_name,
        park_location=park_location,
        turbine_power_mw=turbine_power,
        lifetime_years=lifetime,
        foundation_type=foundation_type,
        vessel_activity=vessel,
        vessel_amount=installation_amount,
    )
    maintenance = _create_vessel_stage(
        ctx,
        code=f"{park_name}_offshore_maintenance",
        reference_product="offshore wind turbine, maintenance",
        location=park_location,
        vessel_activity=vessel,
        amount=maintenance_amount,
    )
    decommissioning = _create_vessel_stage(
        ctx,
        code=f"{park_name}_offshore_decommissioning",
        reference_product="offshore wind turbine, decommissioning operations",
        location=park_location,
        vessel_activity=vessel,
        amount=decommissioning_amount,
    )
    combined_eol = _create_component(
        ctx,
        code=f"{park_name}_offshore_eol",
        reference_product="offshore wind turbine, end of life",
        location=park_location,
        inputs=(turbine_eol, foundation_eol, decommissioning),
    )
    return _create_component(
        ctx,
        code=f"{park_name}_offshore_turbine",
        reference_product="offshore wind turbine",
        location=park_location,
        inputs=(
            turbine_materials,
            turbine_manufacturing,
            foundation,
            foundation_manufacturing,
            transport,
            installation,
            maintenance,
            combined_eol,
        ),
    )


def _validate_offshore_inputs(
    foundation_type: str,
    floating_platform: Optional[str],
    number_of_turbines: Optional[int] = None,
):
    if foundation_type not in FOUNDATION_TYPES:
        raise ValueError(f"foundation_type must be one of {sorted(FOUNDATION_TYPES)}")
    if foundation_type == "floating" and floating_platform not in FLOATING_PLATFORM_TYPES:
        raise ValueError(
            f"floating_platform must be one of {sorted(FLOATING_PLATFORM_TYPES)}"
        )
    if foundation_type != "floating" and floating_platform is not None:
        raise ValueError("floating_platform must be None for fixed-bottom foundations")
    if number_of_turbines is not None and number_of_turbines < 1:
        raise ValueError("number_of_turbines must be at least one")


def lci_offshore_turbine(
    new_db: bd.Database,
    cutoff391: bd.Database,
    biosphere3: bd.Database,
    park_name: str,
    park_location: str,
    park_coordinates: tuple,
    manufacturer: str,
    rotor_diameter: float,
    turbine_power: float,
    hub_height: float,
    commissioning_year: int,
    foundation_type: FoundationType,
    sea_depth: float,
    distance_to_shore: float,
    floating_platform: Optional[FloatingPlatformType] = None,
    recycled_share_steel: Optional[float] = None,
    electricity_mix_steel: Optional[ElectricityMix] = None,
    generator_type: GeneratorType = "gb_dfig",
    lifetime: int = 20,
    eol_scenario: int = 1,
    regression_adjustment: RegressionAdjustment = "D2h",
    ecoinvent_version: str = consts.DEFAULT_EI_VERSION,
    activity_variables_csv: Optional[str] = None,
    vessel_activity=None,
):
    """Create and return the inventory of one offshore turbine.

    ``distance_to_shore`` is in kilometres and ``sea_depth`` is in metres.
    ``vessel_activity`` can be supplied to override automatic activity
    resolution, which is recommended when adding a new ecoinvent version.
    """
    _validate_offshore_inputs(foundation_type, floating_platform)
    ctx = _make_context(
        new_db, cutoff391, biosphere3, ecoinvent_version, activity_variables_csv
    )
    return _build_offshore_turbine(
        ctx,
        park_name=park_name,
        park_location=park_location,
        park_coordinates=park_coordinates,
        manufacturer=manufacturer,
        rotor_diameter=rotor_diameter,
        turbine_power=turbine_power,
        hub_height=hub_height,
        commissioning_year=commissioning_year,
        foundation_type=foundation_type,
        sea_depth=sea_depth,
        distance_to_shore=distance_to_shore,
        floating_platform=floating_platform,
        recycled_share_steel=recycled_share_steel,
        electricity_mix_steel=electricity_mix_steel,
        generator_type=generator_type,
        lifetime=lifetime,
        eol_scenario=eol_scenario,
        regression_adjustment=regression_adjustment,
        vessel_activity=vessel_activity,
    )


def lci_offshore_park(
    new_db: bd.Database,
    cutoff391: bd.Database,
    biosphere3: bd.Database,
    park_name: str,
    park_power: float,
    number_of_turbines: int,
    park_location: str,
    park_coordinates: tuple,
    manufacturer: str,
    rotor_diameter: float,
    turbine_power: float,
    hub_height: float,
    commissioning_year: int,
    foundation_type: FoundationType,
    sea_depth: float,
    distance_to_shore: float,
    floating_platform: Optional[FloatingPlatformType] = None,
    recycled_share_steel: Optional[float] = None,
    electricity_mix_steel: Optional[ElectricityMix] = None,
    generator_type: GeneratorType = "gb_dfig",
    lifetime: int = 20,
    eol_scenario: int = 1,
    regression_adjustment: RegressionAdjustment = "D2h",
    ecoinvent_version: str = consts.DEFAULT_EI_VERSION,
    activity_variables_csv: Optional[str] = None,
    vessel_activity=None,
    iron_ore_activity=None,
):
    """Create and return a complete offshore wind-park inventory.

    The resulting park contains ``number_of_turbines`` turbine inventories,
    one park-level cabling system, one offshore substation, and a transformer
    scaled from the 500 MVA reference activity.
    """
    _validate_offshore_inputs(
        foundation_type, floating_platform, number_of_turbines
    )
    expected_power = number_of_turbines * turbine_power
    if not np.isclose(park_power, expected_power):
        raise ValueError(
            "park_power must equal number_of_turbines * turbine_power; "
            f"received {park_power} versus {expected_power}."
        )
    ctx = _make_context(
        new_db, cutoff391, biosphere3, ecoinvent_version, activity_variables_csv
    )
    turbine = _build_offshore_turbine(
        ctx,
        park_name=park_name,
        park_location=park_location,
        park_coordinates=park_coordinates,
        manufacturer=manufacturer,
        rotor_diameter=rotor_diameter,
        turbine_power=turbine_power,
        hub_height=hub_height,
        commissioning_year=commissioning_year,
        foundation_type=foundation_type,
        sea_depth=sea_depth,
        distance_to_shore=distance_to_shore,
        floating_platform=floating_platform,
        recycled_share_steel=recycled_share_steel,
        electricity_mix_steel=electricity_mix_steel,
        generator_type=generator_type,
        lifetime=lifetime,
        eol_scenario=eol_scenario,
        regression_adjustment=regression_adjustment,
        vessel_activity=vessel_activity,
    )

    cable_masses = submarine_cable_materials(
        rotor_diameter, distance_to_shore, number_of_turbines
    )
    cable_materials = _create_material_activity(
        ctx,
        code=f"{park_name}_offshore_cabling_materials",
        reference_product="offshore wind park cabling, materials",
        location=park_location,
        masses_kg=cable_masses,
        commissioning_year=commissioning_year,
        recycled_share_steel=recycled_share_steel,
        electricity_mix_steel=electricity_mix_steel,
    )
    cable_manufacturing = _create_processing_activity(
        ctx,
        code=f"{park_name}_offshore_cabling_manufacturing",
        reference_product="offshore wind park cabling, manufacturing",
        location=park_location,
        masses_kg=cable_masses,
    )
    cable_eol = _create_material_eol(
        ctx,
        code=f"{park_name}_offshore_cabling_eol",
        reference_product="offshore wind park cabling, end of life",
        location=park_location,
        masses_kg=cable_masses,
        scenario=eol_scenario,
    )
    cabling = _create_component(
        ctx,
        code=f"{park_name}_offshore_cabling",
        reference_product="offshore wind park cabling",
        location=park_location,
        inputs=(cable_materials, cable_manufacturing, cable_eol),
    )

    substation_materials, substation_masses = _create_substation_materials(
        ctx,
        park_name=park_name,
        park_location=park_location,
        commissioning_year=commissioning_year,
        recycled_share_steel=recycled_share_steel,
        electricity_mix_steel=electricity_mix_steel,
        iron_ore_activity=iron_ore_activity,
    )
    substation_manufacturing = _create_processing_activity(
        ctx,
        code=f"{park_name}_offshore_substation_manufacturing",
        reference_product="offshore substation, manufacturing",
        location=park_location,
        masses_kg={"Low alloy steel": substation_masses["Low alloy steel"]},
    )
    substation_eol = _create_material_eol(
        ctx,
        code=f"{park_name}_offshore_substation_eol",
        reference_product="offshore substation, end of life",
        location=park_location,
        masses_kg={"Low alloy steel": substation_masses["Low alloy steel"]},
        scenario=eol_scenario,
    )
    substation = _create_component(
        ctx,
        code=f"{park_name}_offshore_substation",
        reference_product="offshore substation",
        location=park_location,
        inputs=(substation_materials, substation_manufacturing, substation_eol),
    )

    transformer = mva500_transformer(
        new_db=ctx.new_db,
        cutoff391=ctx.source_db,
        ei_index=ctx.ei_index,
        ecoinvent_version=ctx.ecoinvent_version,
        activity_variables_csv=ctx.activity_variables_csv,
    )
    park = _new_activity(
        ctx,
        f"{park_name}_offshore_park",
        f"{park_name}_offshore_park",
        "electricity production, offshore wind park",
        park_location,
        comment=(
            f"Power={park_power} MW; turbines={number_of_turbines}; "
            f"foundation={foundation_type}; lifetime={lifetime} years"
        ),
    )
    _link(park, turbine, number_of_turbines)
    _link(park, cabling)
    _link(park, substation)
    _link(park, transformer, park_power / 500)
    return park


# Historical name retained for older notebooks.
offshore_park = lci_offshore_park


__all__ = [
    "FoundationType",
    "FloatingPlatformType",
    "monopile_materials",
    "gravity_materials",
    "tripod_materials",
    "floating_materials",
    "submarine_cable_materials",
    "lci_offshore_turbine",
    "lci_offshore_park",
    "offshore_park",
]
