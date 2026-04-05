"""
Digital Lab — Analysis report generator.
Builds a structured report from pipeline result.
"""


def generate_report(pipeline_result):
    """
    Generate analysis report dict from run_pipeline() result.
    """
    if pipeline_result.get("error"):
        return {
            "summary": f"Pipeline error: {pipeline_result['error']}",
            "sections": [],
            "status": "error",
        }
    brightness = pipeline_result.get("brightness", {})
    anomalies = pipeline_result.get("anomalies", {})
    stars = pipeline_result.get("stars", [])
    objects = pipeline_result.get("objects", [])

    sections = [
        {
            "title": "Image",
            "content": {
                "loaded": pipeline_result.get("image_loaded"),
                "preprocessed": pipeline_result.get("preprocessed"),
                "shape": pipeline_result.get("shape"),
            },
        },
        {
            "title": "Detection",
            "content": {
                "stars_detected": len(stars),
                "objects_detected": len(objects),
            },
        },
        {
            "title": "Brightness",
            "content": {
                "global_mean": round(brightness.get("global_mean", 0), 4),
                "global_std": round(brightness.get("global_std", 0), 4),
                "global_max": round(brightness.get("global_max", 0), 4),
                "mean_star_flux": round(brightness.get("mean_star_flux", 0), 4),
                "mean_object_flux": round(brightness.get("mean_object_flux", 0), 4),
            },
        },
        {
            "title": "Anomalies",
            "content": {
                "count": anomalies.get("anomaly_count", 0),
                "items": anomalies.get("anomalies", []),
            },
        },
    ]

    summary_parts = [
        f"Stars: {len(stars)}, Objects: {len(objects)}.",
        f"Global mean brightness: {brightness.get('global_mean', 0):.4f}.",
    ]
    if anomalies.get("anomaly_count", 0) > 0:
        summary_parts.append(f"Anomalies: {anomalies['anomaly_count']}.")

    return {
        "summary": " ".join(summary_parts),
        "sections": sections,
        "status": "success",
    }
