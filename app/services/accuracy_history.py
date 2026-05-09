from collections import deque
import time

# Memoire simple (process)
_history = deque(maxlen=10)


def push_accuracy_sample(distance_km):
    if distance_km is not None:
        _history.append({
            "distance_km": distance_km,
            "ts": int(time.time()),
        })


def get_accuracy_stats():
    if not _history:
        return {
            "count": 0,
            "avg_km": None,
            "min_km": None,
            "max_km": None,
            "status": "warming_up",
        }

    vals = [x["distance_km"] for x in _history]

    return {
        "count": len(vals),
        "avg_km": round(sum(vals) / len(vals), 2),
        "min_km": round(min(vals), 2),
        "max_km": round(max(vals), 2),
    }


def get_accuracy_history():
    """
    Retourne l'historique brut sous forme de liste serialisable.
    """
    return list(_history)
