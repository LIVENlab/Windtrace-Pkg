import os
from pathlib import Path


# Package paths
MODULE_DIR = Path(__file__).resolve().parent

# Default packaged data files
DEFAULT_VARIABLES_CSV_FILE = MODULE_DIR / "ecoinvent_activity_variables.csv"
DEFAULT_VESTAS_FILE = MODULE_DIR / "clean_data.xlsx"

# Backward-compatible defaults.
# These can be overwritten at runtime by windtrace.config.apply_config().
PROJECT_NAME = None
SPOLD_FILES = None
NEW_DB_NAME = None
DEFAULT_EI_VERSION = "3.12"

VARIABLES_CSV_FILE = str(DEFAULT_VARIABLES_CSV_FILE)
VESTAS_FILE = str(DEFAULT_VESTAS_FILE)

# When possible, RER or Europe without Switzerland locations have been selected
MANUFACTURER_LOC = {'Vestas': {1: {'country': 'DK', 'location': (54.8291253662034, 11.1212115492466)},
                               2: {'country': 'DK', 'location': (56.0227841143509, 8.38093375265438)},
                               3: {'country': 'DK', 'location': (56.0883528380133, 8.23514084205859)},
                               4: {'country': 'DK', 'location': (55.4688414575748, 10.5463625927981)},
                               5: {'country': 'DK', 'location': (56.0874350071926, 8.23751960633171)},
                               6: {'country': 'DE', 'location': (53.9353019822524, 10.8436417188164)},
                               7: {'country': 'IT', 'location': (40.5044941341608, 17.2287358289053)},
                               8: {'country': 'ES', 'location': (39.04397684446477, -3.584957140536688)},
                               9: {'country': 'GB', 'location': (50.722088190989055, -1.2868432968480525)}},
                    'Siemens Gamesa': {1: {'country': 'DK', 'location': (55.95591820576292, 9.122436361699371)},
                                       2: {'country': 'DK', 'location': (57.04323306831486, 10.033956589032089)},
                                       3: {'country': 'DE', 'location': (53.8432663362179, 8.751820362596261)},
                                       4: {'country': 'ES', 'location': (41.84642998231027, -1.9375829067207992)},
                                       5: {'country': 'ES', 'location': (43.288703816235945, -2.8593248806708322)},
                                       6: {'country': 'TR', 'location': (38.451039935268916, 27.17844981452182)},
                                       7: {'country': 'GB', 'location': (53.744468006219314, -0.30480462006378034)}},
                    'Enercon': {1: {'country': 'DE', 'location': (53.46900866545183, 7.461912729754879)},
                                2: {'country': 'DE', 'location': (52.198664285069384, 11.67724373576914)},
                                3: {'country': 'PT', 'location': (41.75127343145981, -8.688698916614396)}},
                    'Nordex': {1: {'country': 'DE', 'location': (53.67607989480183, 10.00207222593792)},
                               2: {'country': 'ES', 'location': (42.611427316908355, -1.6381422745701957)}},
                    'LM Wind': {1: {'country': 'ES', 'location': (42.56581346608258, -6.554743222531039)},
                                2: {'country': 'ES', 'location': (40.28628952931124, 0.08687809123315436)},
                                3: {'country': 'FR', 'location': (49.64941639036492, -1.5976205757000064)},
                                4: {'country': 'PL', 'location': (53.55423722170504, 14.789982179973517)},
                                5: {'country': 'TR', 'location': (39.08046596169773, 27.05453305967944)}}
                    }

# Mean share of steel production in Europe by country between 2017 and 2021 according to the
# European Steel in Figures Report 2022 (by Eurofer). Countries without gas inventory in Ecoinvent were assigned the
# inventory of a nearby country. Croatia and Slovenia were assigned Italy's inventory,
# Luxembourg was assigned Belgium's and Bulgaria was assigned Romania's.
# Europe is a net importer since 2017, but was a clear net exporter until then. Therefore, it is assumed
# that all the steel used in the turbines is European-made.
# Share of secondary steel production (electric furnace)
SECONDARY_STEEL = {'other': 0.4162, '2012': 0.4304, '2013': 0.4172, '2014': 0.4080, '2015': 0.4094,
                   '2016': 0.4058, '2017': 0.4135, '2018': 0.4240, '2019': 0.4191, '2020': 0.4365, '2021': 0.4360}

PRINTED_WARNING_STEEL = False

# rare earth shares
RARE_EARTH_DICT = {'Praseodymium': {'dd_eesg': 9, 'dd_pmsg': 35, 'gb_pmsg': 4, 'gb_dfig': 0},
                   'Neodymium': {'dd_eesg': 28, 'dd_pmsg': 180, 'gb_pmsg': 51, 'gb_dfig': 12},
                   'Dysprosium': {'dd_eesg': 6, 'dd_pmsg': 17, 'gb_pmsg': 6, 'gb_dfig': 2},
                   'Terbium': {'dd_eesg': 1, 'dd_pmsg': 7, 'gb_pmsg': 1, 'gb_dfig': 0},
                   'Boron': {'dd_eesg': 0, 'dd_pmsg': 6, 'gb_pmsg': 1, 'gb_dfig': 0}
                   }

# scenarios lifetime extension, replacement, repowering
LONG_EXTENSION = {'steel': 0.08, 'c_steel': 0.08, 'iron': 1, 'aluminium': 0.65, 'copper': 0.81,
                  'plastics': 1, 'others': 1, 'foundations': 0, 'electronics_and_electrics': 0}
SHORT_EXTENSION = {'steel': 0.01, 'c_steel': 0.01, 'iron': 0.34, 'aluminium': 0, 'copper': 0,
                   'plastics': 0.91, 'others': 0, 'foundations': 0, 'electronics_and_electrics': 0}
REPLACEMENT_BASELINE = {'steel': 0.84, 'c_steel': 0.84, 'iron': 1, 'aluminium': 0.65, 'copper': 0.81,
                        'plastics': 1, 'others': 1, 'foundations': 0, 'electronics_and_electrics': 0}

# vestas_file path
VESTAS_FILE = os.path.join(MODULE_DIR, 'clean_data.xlsx')
