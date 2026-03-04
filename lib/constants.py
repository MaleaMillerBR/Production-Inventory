import os

WORK_AREAS = [
    "Sensors",
    "Sensors-Custom",
    "Sensors-Misc",
    "Thrusters",
    "Thrusters-Custom",
    "ROV",
    "FXTI/SPOOL/TETHER",
    "BlueBoat",
    "FAA",
    "WetLink",
    "Packing",
    "BB120 Packing",
]

WORK_AREA_FIELD = "work_area"
WORK_AREA_MODEL = os.getenv("ODOO_WORK_AREA_MODEL", "mrp.work.area")
