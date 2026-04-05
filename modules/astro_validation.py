import re
from typing import Dict, Tuple, Optional


ASTRO_WHITELIST_PROVIDERS = {
    "NASA",
    "HUBBLE",
    "JWST",
    "ESO",
    "SKYVIEW",
    "LCO",
    "MICROOBSERVATORY",
    "SKYNET",
    "NOIRLAB",
}

POSITIVE_KEYWORDS = {
    "nebula",
    "galaxy",
    "cluster",
    "supernova",
    "deep field",
    "deep-field",
    "exoplanet",
    "quasar",
    "star forming region",
    "star-forming region",
    "telescope observation",
    "emission nebula",
    "planetary nebula",
    "dark nebula",
    "globular cluster",
    "open cluster",
    "interstellar",
    "cosmos",
}

NEGATIVE_KEYWORDS = {
    "people",
    "person",
    "portrait",
    "astronaut portrait",
    "ceremony",
    "conference",
    "meeting",
    "event",
    "logo",
    "patch",
    "t-shirt",
    "selfie",
    "group photo",
    "press conference",
}


def _text_from_metadata(metadata: Dict) -> str:
    parts = []
    for key in ("title", "description", "keywords", "collection", "mission", "instrument"):
        val = metadata.get(key)
        if not val:
            continue
        if isinstance(val, (list, tuple)):
            parts.extend(str(x) for x in val if x)
        else:
            parts.append(str(val))
    return " ".join(parts).lower()


def is_valid_astro_image(metadata: Dict) -> Tuple[bool, Optional[str]]:
    """
    Return (True, None) if the image is accepted as astronomical.
    Return (False, reason) otherwise.
    """
    if not isinstance(metadata, dict):
        return False, "metadata_not_dict"

    provider = str(metadata.get("source_provider") or metadata.get("source") or "").upper().strip()
    if provider and provider not in ASTRO_WHITELIST_PROVIDERS:
        return False, f"provider_not_whitelisted:{provider or 'unknown'}"

    text = _text_from_metadata(metadata)

    # Negative keywords have priority: any hit rejects
    for bad in NEGATIVE_KEYWORDS:
        if bad.lower() in text:
            return False, f"negative_keyword:{bad}"

    # Require at least one positive keyword if we have some text
    if text:
        for good in POSITIVE_KEYWORDS:
            if good.lower() in text:
                return True, None
        return False, "no_positive_astro_keyword"

    # If we have no descriptive text at all, be conservative and reject
    return False, "no_descriptive_text"


def normalize_metadata(
    raw_meta: Dict,
    source_provider: str,
    local_filename: str,
    validation_status: str,
    reason: Optional[str] = None,
) -> Dict:
    """
    Build a normalized metadata dict used by AstroScan Digital Lab.
    """
    src = (source_provider or raw_meta.get("source") or "").upper() or "UNKNOWN"
    title = raw_meta.get("title") or raw_meta.get("object_name") or ""
    description = raw_meta.get("description") or ""

    out = {
        "source_provider": src,
        "instrument": raw_meta.get("instrument") or raw_meta.get("telescope") or "",
        "mission": raw_meta.get("mission") or "",
        "title": title,
        "description": description,
        "object_type": raw_meta.get("object_type") or "",
        "object_name": raw_meta.get("object_name") or "",
        "observation_date": raw_meta.get("observation_date") or raw_meta.get("date") or "",
        "original_url": raw_meta.get("original_url") or raw_meta.get("image_url") or "",
        "local_filename": local_filename,
        "validation_status": validation_status,
        "validation_reason": reason or "",
    }
    for key in ("ra", "dec", "exposure_time", "filter"):
        if key in raw_meta and raw_meta[key] is not None:
            out[key] = raw_meta[key]
    return out

