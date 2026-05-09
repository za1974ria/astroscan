SATELLITES = {
    "ISS": 25544,
    "NOAA15": 25338,
    "NOAA18": 28654,
    "NOAA19": 33591,
}


def list_satellites():
    return list(SATELLITES.keys())


def get_satellite_tle_name_map():
    return {
        "ISS": "ISS (ZARYA)",
        "NOAA15": "NOAA 15",
        "NOAA18": "NOAA 18",
        "NOAA19": "NOAA 19",
    }
