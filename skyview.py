"""skyview.py — Stub de compatibilité (source supprimée, rechargée depuis pyc).

Ce fichier existe parce que le source original a été supprimé mais le .pyc
existe dans __pycache__. La logique réelle est dans skyview_module.py.
"""
import importlib.util
import os
import sys

_pyc = os.path.join(os.path.dirname(__file__), '__pycache__', 'skyview.cpython-312.pyc')

if os.path.exists(_pyc):
    _spec = importlib.util.spec_from_file_location('_skyview_from_pyc', _pyc)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    OBJETS_TLEMCEN = _mod.OBJETS_TLEMCEN
    SURVEYS = _mod.SURVEYS
    SKYVIEW_URL = _mod.SKYVIEW_URL
    get_object_image = _mod.get_object_image
    get_image_url = _mod.get_image_url
else:
    # Fallback minimaliste si le pyc aussi disparaît
    SKYVIEW_URL = "https://skyview.gsfc.nasa.gov/cgi-bin/images"
    OBJETS_TLEMCEN = []
    SURVEYS = {}

    def get_object_image(name, survey="DSS2+Red", size=0.5):
        return None

    def get_image_url(name, survey="DSS2+Red", size=0.5):
        return None
