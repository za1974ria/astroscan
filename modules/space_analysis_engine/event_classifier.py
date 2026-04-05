"""
Space Analysis Engine — Event classifier.
Classify detected objects using simple heuristics (no ML).
"""
import math


def classify_objects(pipeline_result):
    """
    Classify stars and objects from digital_lab pipeline result.
    pipeline_result: dict with keys stars, objects, brightness, anomalies
    Returns: list of dicts { type, label, confidence, details }
    """
    classifications = []
    stars = pipeline_result.get('stars') or []
    objects = pipeline_result.get('objects') or []
    brightness = pipeline_result.get('brightness') or {}
    anomalies = pipeline_result.get('anomalies') or {}

    # Classify point sources (stars) by brightness
    fluxes = brightness.get('star_fluxes') or []
    mean_flux = brightness.get('mean_star_flux') or 0.0
    for i, s in enumerate(stars[:100]):
        peak = s.get('peak', 0)
        flux = fluxes[i] if i < len(fluxes) else peak * 10
        if mean_flux > 0 and flux > mean_flux * 2.5:
            classifications.append({
                'type': 'star',
                'label': 'bright_star',
                'confidence': 0.8,
                'details': {'x': s.get('x'), 'y': s.get('y'), 'flux_ratio': round(flux / mean_flux, 2)},
            })
        elif peak > 0.9:
            classifications.append({
                'type': 'star',
                'label': 'saturated_star',
                'confidence': 0.9,
                'details': {'x': s.get('x'), 'y': s.get('y')},
            })
        else:
            classifications.append({
                'type': 'star',
                'label': 'point_source',
                'confidence': 0.7,
                'details': {'x': s.get('x'), 'y': s.get('y')},
            })

    # Classify extended objects by area and brightness
    for o in objects[:50]:
        area = o.get('area', 0)
        mean_b = o.get('mean_brightness', 0)
        if area > 500 and mean_b > 0.2:
            classifications.append({
                'type': 'object',
                'label': 'extended_bright',
                'confidence': 0.75,
                'details': {'x': o.get('x'), 'y': o.get('y'), 'area': area},
            })
        elif area > 100:
            classifications.append({
                'type': 'object',
                'label': 'extended_source',
                'confidence': 0.6,
                'details': {'x': o.get('x'), 'y': o.get('y'), 'area': area},
            })
        else:
            classifications.append({
                'type': 'object',
                'label': 'faint_extended',
                'confidence': 0.5,
                'details': {'x': o.get('x'), 'y': o.get('y'), 'area': area},
            })

    # Anomaly-based classifications
    for a in anomalies.get('anomalies') or []:
        atype = a.get('type', 'unknown')
        classifications.append({
            'type': 'anomaly',
            'label': atype,
            'confidence': 0.85 if a.get('severity') == 'high' else 0.7,
            'details': {'message': a.get('message'), 'severity': a.get('severity')},
        })

    return classifications
