# -*- coding: utf-8 -*-
"""
Moteur d'analyse scientifique d'images spatiales.
Détection simple : étoiles, galaxies, nébuleuses, artefacts.
Sans dépendances lourdes (PIL optionnel).
"""

import os
import json


def analyze_space_image(path):
    """
    Analyse une image et retourne un rapport JSON.
    path: chemin vers le fichier image (ex. data/lab_uploads/xxx.png)
    """
    result = {
        "stars": 0,
        "galaxies": 0,
        "nebula": False,
        "anomalies": [],
    }
    if not path or not os.path.isfile(path):
        result["anomalies"].append("Fichier introuvable ou invalide")
        return result

    try:
        from PIL import Image
        import math
    except ImportError:
        result["anomalies"].append("PIL non disponible — analyse limitée")
        result["stars"] = -1
        return result

    try:
        img = Image.open(path)
        img = img.convert("RGB")
        w, h = img.size
        pixels = img.load()

        # Détection de points lumineux (étoiles) : pixels au-dessus d'un seuil
        bright_threshold = 200
        bright_count = 0
        total_lum = 0
        sample_count = 0
        for x in range(0, w, max(1, w // 50)):
            for y in range(0, h, max(1, h // 50)):
                r, g, b = pixels[x, y]
                lum = (r + g + b) / 3
                total_lum += lum
                sample_count += 1
                if lum >= bright_threshold:
                    bright_count += 1

        avg_lum = total_lum / sample_count if sample_count else 0
        # Estimation étoiles : nombre de zones très lumineuses (heuristique)
        result["stars"] = min(999, bright_count * 3)

        # Nébuleuse : image globalement bleue/verte (régions HII)
        if sample_count:
            r_sum = g_sum = b_sum = 0
            for x in range(0, w, max(1, w // 40)):
                for y in range(0, h, max(1, h // 40)):
                    r, g, b = pixels[x, y]
                    r_sum += r
                    g_sum += g
                    b_sum += b
            n = (w // max(1, w // 40)) * (h // max(1, h // 40))
            if n > 0 and b_sum > r_sum and g_sum > r_sum * 0.8:
                result["nebula"] = True

        # Galaxies : forme étendue (ratio luminosité centre / bords) — simplifié
        if w >= 50 and h >= 50:
            cx, cy = w // 2, h // 2
            center_lum = 0
            n_center = 0
            for i in (-1, 0, 1):
                for j in (-1, 0, 1):
                    x, y = cx + i, cy + j
                    if 0 <= x < w and 0 <= y < h:
                        r, g, b = pixels[x, y]
                        center_lum += r + g + b
                        n_center += 1
            center_lum = center_lum / n_center if n_center else 0
            edge_lum = (pixels[0, 0][0] + pixels[0, 0][1] + pixels[0, 0][2] + pixels[w-1, h-1][0] + pixels[w-1, h-1][1] + pixels[w-1, h-1][2]) / 6
            if center_lum > edge_lum * 1.2:
                result["galaxies"] = 1

        # Artefacts / anomalies
        if avg_lum < 5:
            result["anomalies"].append("Image très sombre")
        if w > 5000 or h > 5000:
            result["anomalies"].append("Résolution très élevée")

    except Exception as e:
        result["anomalies"].append("Erreur analyse: " + str(e))

    return result
