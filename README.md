# WindTrace

WindTrace is a Python package for creating tailor-made life-cycle inventory (LCI) models of onshore wind turbines and wind park fleets using Brightway and ecoinvent.

WindTrace can create customized inventories for wind turbines, cables, transformers, installation, transport, maintenance, end-of-life, land occupation, and wind park electricity production. The package uses a versioned ecoinvent activity-selector table so that the same WindTrace model can be adapted to different ecoinvent releases without hard-coding all activity names inside the Python code.

WindTrace has been funded by the European Commission though the Horizon Europe project "JUSTWIND4ALL" (GA 101083936).

---

## Main features

- Parametric LCI generation for onshore wind turbines and wind parks.
- Brightway/Brightway2.5 integration.
- Config-file based project setup using `windtrace_config.yml`.
- Multi-ecoinvent support using `ecoinvent_activity_variables.csv`.
- Command-line updater utility for adding and validating ecoinvent activity selector columns.
- User-editable CSV activity mapping table.
- Packaged default data files, including:
  - `ecoinvent_activity_variables.csv`
  - `clean_data.xlsx`
- Optional workflow for validating that all required ecoinvent activities exist in the selected Brightway database.
- Separation between:
  - WindTrace package code
  - user-specific configuration
  - licensed ecoinvent data

---

## Important note about ecoinvent

WindTrace does **not** include ecoinvent database files, SPOLD files, database exports, or ecoinvent credentials.

Users must have their own valid ecoinvent license and must download/import ecoinvent separately. WindTrace only stores the names, locations, and reference products of the ecoinvent activities needed by the model.

The recommended workflow is:

1. Install WindTrace.
2. Download ecoinvent using your own license.
3. Import ecoinvent into Brightway manually before running WindTrace.
4. Configure WindTrace using `windtrace_config.yml`.
5. Validate the activity selector CSV.
6. Run WindTrace.

---

## Repository structure

A package-ready WindTrace repository should look like this:

```text
windtrace-package/
│
├── pyproject.toml
├── environment.yml
├── README.md
├── LICENSE
├── windtrace_config.example.yml
├── MANIFEST.in
├── src/
│   └── windtrace/
│       ├── __init__.py
│       ├── config.py
│       ├── consts.py
│       ├── onshore.py
│       ├── helper_functions.py
│       ├── ecoinvent_activity_variables.py
│       ├── ecoinvent_variables_updater.py
│       ├── ecoinvent_activity_variables.csv
│       └── clean_data.xlsx
│
└── notebooks/
    └── WindTrace_guide.ipynb
```

The packaged CSV and Excel files are default/template data files. Users should not edit the installed package copy directly. Instead, they should copy the CSV and config template to their own working project folder.

---

## Installation

### Option 1: Install from a local source folder during development

From the root folder where `pyproject.toml` is located:

```bash
conda env create -f environment.yml
conda activate windtrace_env
pip install -e .
```

The `-e .` option installs WindTrace in editable mode. This is useful during development because changes in `src/windtrace/onshore.py` or other source files are used immediately the next time Python is run.

Test the installation:

```bash
python -c "import windtrace; print(windtrace.__version__)"
windtrace-ecoinvent-updater --help
```

### Option 2: Install from GitHub

```bash
pip install git+https://github.com/YOUR_USERNAME/windtrace.git
```

Or, for development:

```bash
git clone https://github.com/YOUR_USERNAME/windtrace.git
cd windtrace
conda env create -f environment.yml
conda activate windtrace_env
pip install -e .
```

### Option 3: PyPI

If WindTrace is published publicly in the future, users may install it with:

```bash
pip install windtrace
```

The ecoinvent database will still need to be downloaded and imported separately by the user.

---


## User project setup

After installing WindTrace, create a separate project folder. For example:

```bash
mkdir Windtrace_Project
cd Windtrace_Project
```

The user project folder should contain:

```text
Windtrace_Project/
│
├── windtrace_config.yml
├── ecoinvent_activity_variables.csv
└── run_windtrace.py
```

Copy the example config file:

```bash
cp /path/to/windtrace-package/windtrace_config.example.yml windtrace_config.yml
```

On Windows, you can also copy it manually using File Explorer.

Copy the packaged default CSV to your project folder:

```bash
python -c "import shutil, windtrace.consts as c; shutil.copy(c.DEFAULT_VARIABLES_CSV_FILE, 'ecoinvent_activity_variables.csv')"
```

The project copy of `ecoinvent_activity_variables.csv` is the file the user should edit when adding or correcting activity selectors.

---

## Configuration file

WindTrace uses a YAML configuration file instead of asking users to edit `consts.py`.

Create or edit:

```text
windtrace_config.yml
```

Example:

```yaml
brightway:
  project_name: "windtrace_3_12_project"
  source_database: "ecoinvent-3.12-cutoff"
  output_database: "windtrace_results_3_12"
  biosphere_database: "biosphere3"
  spold_files: "C:/path/to/ecoinvent/3.12/cutoff/datasets"

ecoinvent:
  version: "3.12"
  activity_variables_csv: "./ecoinvent_activity_variables.csv"
```

### Meaning of each field

| Field | Meaning |
|---|---|
| `brightway.project_name` | Name of the Brightway project to use. |
| `brightway.source_database` | Name of the imported ecoinvent database in Brightway. |
| `brightway.output_database` | Name of the database where WindTrace will create new activities. |
| `brightway.biosphere_database` | Biosphere database name, usually `biosphere3`. |
| `brightway.spold_files` | Path to the local ecoinvent SPOLD files. Used only when importing ecoinvent. |
| `ecoinvent.version` | Ecoinvent version used to select CSV columns, e.g. `3.12`. |
| `ecoinvent.activity_variables_csv` | Path to the user-editable activity selector CSV. |

Relative paths in the config file should be interpreted relative to the config file location if your `config.py` resolves paths this way.

---

## Ecoinvent setup

Ecoinvent setup is separate from the WindTrace package. The user must download ecoinvent using their own license and import it into Brightway before running WindTrace.

Recommended steps:

1. Download ecoinvent with your own license.
2. Import it into Brightway manually.
3. Confirm the database name in Brightway.
4. Add the database name to `windtrace_config.yml` as `source_database`.

Example:

```yaml
brightway:
  project_name: "windtrace_3_12_project"
  source_database: "ecoinvent-3.12-cutoff"
```

---

## Multi-ecoinvent activity selector CSV

WindTrace uses:

```text
ecoinvent_activity_variables.csv
```

to store ecoinvent activity selectors.

Each row represents one logical WindTrace variable. Examples:

```text
materials / Copper
processing / Steel_tower_rolling
eol / Rubber / incineration
steel_electricity / DE
steel_gas / DE
```

Each ecoinvent version has three selector columns:

```text
ei_3_12_name
ei_3_12_location
ei_3_12_reference_product
```

For another version, the CSV can contain another set:

```text
ei_3_13_name
ei_3_13_location
ei_3_13_reference_product
```

WindTrace uses the version in the config file:

```yaml
ecoinvent:
  version: "3.12"
```

to decide which columns to read.

---

## Ecoinvent activity updater utility

WindTrace includes a command-line utility:

```bash
windtrace-ecoinvent-updater
```

This utility helps maintain the versioned ecoinvent selector CSV.

### Show help

```bash
windtrace-ecoinvent-updater --help
```

### Add a new ecoinvent version to the CSV

For example, to add columns for ecoinvent 3.13 by copying 3.12 selectors as a starting point:

```bash
windtrace-ecoinvent-updater add-version \
  --config windtrace_config.yml \
  --from-version 3.12 \
  --to-version 3.13
```

On Windows CMD:

```cmd
windtrace-ecoinvent-updater add-version ^
  --config windtrace_config.yml ^
  --from-version 3.12 ^
  --to-version 3.13
```

This adds:

```text
ei_3_13_name
ei_3_13_location
ei_3_13_reference_product
```

Then open the CSV and edit the new version columns where activities differ between ecoinvent versions. 
The new version activities names, locations, and reference products should be found in Ecoinvent version change report sheet.

### Validate selectors against a Brightway database

```bash
windtrace-ecoinvent-updater validate --config windtrace_config.yml
```

This checks whether every non-empty selector for the selected ecoinvent version exists in the configured Brightway ecoinvent database.

A successful validation prints something similar to:

```text
All non-empty selectors for ecoinvent 3.12 were found in ecoinvent-3.12-cutoff.
```

### Manual validation without config

```bash
windtrace-ecoinvent-updater validate \
  --csv ./ecoinvent_activity_variables.csv \
  --version 3.12 \
  --project windtrace_3_12_project \
  --database ecoinvent-3.12-cutoff
```

On Windows CMD:

```cmd
windtrace-ecoinvent-updater validate ^
  --csv .\ecoinvent_activity_variables.csv ^
  --version 3.12 ^
  --project windtrace_3_12_project ^
  --database ecoinvent-3.12-cutoff
```

### What validation does and does not check

The updater validation checks:

```text
CSV selector → ecoinvent activity exists in Brightway database
```

It does not check:

```text
LCIA methods
biosphere characterization factors
impact assessment calculations
ecoinvent license validity
```
---

## Running WindTrace from a config file

Create a script such as:

```text
run_windtrace.py
```

Example:

```python
from windtrace import load_config, apply_config, setup_brightway
from windtrace import lci_wind_turbine


def main():
    # 1. Load user settings
    config = load_config("windtrace_config.yml")

    # 2. Apply config to legacy constants still used internally
    apply_config(config)

    # 3. Open Brightway databases
    cutoff, new_db, biosphere3 = setup_brightway(config)

    # 4. Run WindTrace
    mass_materials_park, transport_results, occupation_results = lci_wind_turbine(
        new_db=new_db,
        cutoff391=cutoff,
        biosphere3=biosphere3,

        # Wind park information
        park_name="example_park",
        park_power=30,
        number_of_turbines=5,
        park_location="ES",
        park_coordinates=(41.4, 2.1),

        # Turbine information
        manufacturer="Vestas",
        rotor_diameter=120,
        turbine_power=6,
        hub_height=100,
        commissioning_year=2020,
        generator_type="gb_dfig",

        # Optional model settings
        lifetime=20,
        cf=0.24,
        time_adjusted_cf=0.009,
        eol_scenario=1,
        regression_adjustment="D2h",

        # Multi-ecoinvent settings
        ecoinvent_version=config.ecoinvent_version,
        activity_variables_csv=config.activity_variables_csv,

        # Life-cycle stages
        include_life_cycle_stages=True,
        eol=True,
        transportation=True,
        use_and_maintenance=True,
        installation=True,

        comment="Test run using packaged WindTrace and config file."
    )

    print("WindTrace run completed.")
    print("Mass materials park:")
    print(mass_materials_park)


if __name__ == "__main__":
    main()
```

Run it:

```bash
conda activate windtrace_env
cd path/to/Windtrace_Project
python run_windtrace.py
```

---

## Main `lci_wind_turbine()` parameters

The main function for creating customized inventories is:

```python
lci_wind_turbine()
```

Common parameters include:

| Parameter | Description | Default | Type / options |
|---|---|---|---|
| `new_db` | Brightway output database where WindTrace activities are created. | Required | `bd.Database` |
| `cutoff391` | Source ecoinvent database. The name is historical; it can represent any configured ecoinvent version. | Required | `bd.Database` |
| `biosphere3` | Brightway biosphere database. | Required | `bd.Database` |
| `park_name` | Name of the wind park. | Required | `str` |
| `park_power` | Total power of the wind park in MW. | Required | `float` |
| `number_of_turbines` | Number of turbines in the wind park. | Required | `int` |
| `park_location` | Country code using ISO 3166-1 alpha-2. | Required | `str` |
| `park_coordinates` | Latitude and longitude in WGS84. | Required | `tuple` |
| `manufacturer` | Turbine manufacturer. | `LM Wind` | `LM Wind`, `Vestas`, `Siemens Gamesa`, `Enercon`, `Nordex` |
| `rotor_diameter` | Rotor diameter in meters. | Required | `float` |
| `turbine_power` | Nominal power per turbine in MW. | Required | `float` |
| `hub_height` | Turbine hub height in meters. | Required | `float` |
| `commissioning_year` | Year the turbine started operation. | Required | `int` |
| `generator_type` | Gearbox and generator type. | `gb_dfig` | `dd_eesg`, `dd_pmsg`, `gb_pmsg`, `gb_dfig` |
| `regression_adjustment` | Steel mass regression basis. | `D2h` | `D2h`, `Hub height` |
| `recycled_share_steel` | User-defined recycled share of steel. | Uses Eurofer/default data | `float`, optional |
| `electricity_mix_steel` | Electricity mix for steel production. | Eurofer country mix | `Norway`, `Europe`, `Poland`, optional |
| `land_use_permanent` | Permanent land transformation intensity. | package default | `float` |
| `land_cover_type` | Land cover before installation. | model dependent | `str` |
| `eol_scenario` | End-of-life treatment scenario. | `1` | `1`, `2`, `3`, `4` depending on code version |
| `lifetime` | Expected lifetime in years. | `20` | `int` |
| `cf` | Capacity factor. | `0.24` | `float` |
| `time_adjusted_cf` | Annual performance degradation/attrition rate. | `0.009` | `float` |
| `ecoinvent_version` | Ecoinvent version used to select CSV columns. | Config/default | `str` |
| `activity_variables_csv` | Path to the ecoinvent activity selector CSV. | Config/default | `str` |
| `include_life_cycle_stages` | Whether to create separate life-cycle stage activities. | `True` | `bool` |
| `eol` | Include end-of-life stage. | `True` | `bool` |
| `transportation` | Include transportation stage. | `True` | `bool` |
| `use_and_maintenance` | Include maintenance stage. | `True` | `bool` |
| `installation` | Include installation stage. | `True` | `bool` |
| `comment` | Comment stored in created activities. | empty | `str` |

Parameters without defaults must be provided by the user. Parameters with defaults can be adapted to the user’s case.

---

## Running LCA results

WindTrace creates Brightway activities and databases. Depending on the package version, LCA calculation may be available through functions such as:

```python
lca_wind_turbine()
```

LCIA methods are separate from the activity selector validation. Activity validation only checks that inventory activities exist. Actual LCIA calculation requires valid Brightway methods and biosphere flow links.

---


## Troubleshooting

### `database refers to unknown database`

This usually means the output database does not exist yet in the Brightway project.

The setup function should create/register it if missing:

```python
if config.output_database not in bd.databases:
    output_db = bd.Database(config.output_database)
    output_db.write({})
else:
    output_db = bd.Database(config.output_database)
```

### `Missing Ecoinvent activity`

This means a selector from `ecoinvent_activity_variables.csv` was not found in the selected ecoinvent database.

Run:

```bash
windtrace-ecoinvent-updater validate --config windtrace_config.yml
```

Then edit the CSV row reported by the validator.

### `Missing CSV columns for ecoinvent ...`

The selected config version does not have matching columns in the CSV.

For example, if the config says:

```yaml
ecoinvent:
  version: "3.13"
```

the CSV must contain:

```text
ei_3_13_name
ei_3_13_location
ei_3_13_reference_product
```

Add them using:

```bash
windtrace-ecoinvent-updater add-version --config windtrace_config.yml --from-version 3.12 --to-version 3.13
```

```

### Brightway automatic update errors during validation

For activity selector validation, LCIA methods are not needed. The updater can use:

```python
bd.projects.set_current(project_name, update=False)
```

to avoid automatic reprocessing of LCIA methods.

If LCIA errors appear later during actual LCA calculations, recreate or clean the Brightway project and ensure the biosphere database and methods are consistent.

---


## Citing WindTrace

If you use WindTrace for academic work, please cite:

Sierra‐Montoya, M., Muñoz‐Liesa, J., Pérez‐Sánchez, L. À., de Tomás‐Pascual, A., & Madrid‐López, C. (2025). *WindTrace: Assessing the environmental impacts of wind energy designs with a parametric life cycle inventory model*. Journal of Industrial Ecology. https://doi.org/10.1111/jiec.70114

---

