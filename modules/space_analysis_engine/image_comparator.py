"""
Space Analysis Engine — Image comparator.
Compare pipeline results from different sources (NASA feeds, telescope feeds).
"""
import math


def compare_results(result_a, result_b, source_a='source_a', source_b='source_b'):
    """
    Compare two digital_lab pipeline results.
    result_a, result_b: dicts from modules.digital_lab.analysis_pipeline.run_pipeline
    source_a, source_b: optional labels (e.g. 'nasa_feed', 'telescope_feed')
    Returns: dict with diff metrics and comparison summary.
    """
    def _safe_get(r, *keys, default=0):
        for k in keys:
            if isinstance(r, dict) and k in r:
                r = r[k]
            else:
                return default
        return r

    stars_a = result_a.get('stars') or []
    stars_b = result_b.get('stars') or []
    objects_a = result_a.get('objects') or []
    objects_b = result_b.get('objects') or []
    bright_a = result_a.get('brightness') or {}
    bright_b = result_b.get('brightness') or {}

    mean_a = _safe_get(bright_a, 'global_mean')
    mean_b = _safe_get(bright_b, 'global_mean')
    std_a = _safe_get(bright_a, 'global_std')
    std_b = _safe_get(bright_b, 'global_std')

    diff_summary = {
        'source_a': source_a,
        'source_b': source_b,
        'star_count_a': len(stars_a),
        'star_count_b': len(stars_b),
        'object_count_a': len(objects_a),
        'object_count_b': len(objects_b),
        'brightness_diff': round(abs(mean_a - mean_b), 4) if mean_a and mean_b else None,
        'mean_brightness_a': mean_a,
        'mean_brightness_b': mean_b,
        'structure_similarity': _structure_similarity(stars_a, stars_b, objects_a, objects_b),
    }
    return {
        'comparison': diff_summary,
        'summary': (
            f"{source_a}: {len(stars_a)} stars, {len(objects_a)} objects. "
            f"{source_b}: {len(stars_b)} stars, {len(objects_b)} objects. "
            f"Brightness diff: {diff_summary.get('brightness_diff', 'N/A')}."
        ),
    }


def _structure_similarity(stars_a, stars_b, objects_a, objects_b):
    """Simple similarity score 0..1 based on source counts."""
    na, nb = len(stars_a) + len(objects_a), len(stars_b) + len(objects_b)
    if na + nb == 0:
        return 1.0
    ratio = min(na, nb) / max(na, nb) if max(na, nb) > 0 else 1.0
    return round(ratio, 3)
