# -*- coding: utf-8 -*-
"""
AstroScan — MPC Reporter.

Prepares Minor Planet Center (MPC) submission packages for candidate moving
objects and transients. Does NOT submit to MPC; produces draft/validation-ready
reports only. Does not fake observatory codes; uses draft mode when no real
observatory code is configured.
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Pixel tolerance to match candidate (x,y) to validation matches or track points
_POSITION_MATCH_PX = 10.0


def _get_observatory_config(observatory_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Build observatory configuration from env and optional config dict.
    Env: MPC_OBSERVATORY_CODE, MPC_SUBMITTER_NAME, MPC_SUBMITTER_EMAIL, MPC_ACK_ENABLED.
    """
    out: Dict[str, Any] = {
        "observatory_code": None,
        "submitter_name": None,
        "submitter_email": None,
        "ack_enabled": False,
    }
    out["observatory_code"] = (
        os.environ.get("MPC_OBSERVATORY_CODE") or (observatory_config or {}).get("observatory_code")
    )
    out["submitter_name"] = (
        os.environ.get("MPC_SUBMITTER_NAME") or (observatory_config or {}).get("submitter_name")
    )
    out["submitter_email"] = (
        os.environ.get("MPC_SUBMITTER_EMAIL") or (observatory_config or {}).get("submitter_email")
    )
    ack = os.environ.get("MPC_ACK_ENABLED") or (observatory_config or {}).get("ack_enabled")
    out["ack_enabled"] = str(ack).lower() in ("1", "true", "yes")
    return out


def _observation_time_utc_from_metadata(metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return observation time as ISO UTC string, or None if missing/invalid."""
    if not metadata:
        return None
    obs = (
        metadata.get("observation_date")
        or metadata.get("date")
        or metadata.get("timestamp")
        or metadata.get("observation_date_utc")
    )
    if not obs:
        return None
    if isinstance(obs, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(obs), tz=timezone.utc)
            return dt.isoformat()
        except (OSError, ValueError):
            return None
    if isinstance(obs, str):
        try:
            from dateutil import parser as date_parser
            dt = date_parser.parse(obs)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(obs[:19], fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                continue
    return None


def _pixel_to_ra_dec(
    x_px: float,
    y_px: float,
    metadata: Optional[Dict[str, Any]],
) -> Tuple[Optional[float], Optional[float], str]:
    """
    Convert pixel (x, y) to RA/Dec using metadata. Prefers astrometry_solution when solved.
    Returns (ra_deg, dec_deg, astrometry_source) where source is "solved" | "approximate" | "missing".
    Does not fabricate; (None, None, "missing") if calibration missing.
    """
    if not metadata:
        return None, None, "missing"
    astro = metadata.get("astrometry_solution")
    if isinstance(astro, dict) and astro.get("solved"):
        ra_c = astro.get("ra_center")
        dec_c = astro.get("dec_center")
        scale_arcsec = astro.get("pixel_scale_arcsec_per_px")
        scale_deg = float(scale_arcsec) / 3600.0 if scale_arcsec is not None else None
        if scale_deg is None or scale_deg <= 0:
            scale_deg = metadata.get("scale_deg")
            if scale_deg is None and metadata.get("scale_arcsec") is not None:
                try:
                    scale_deg = float(metadata["scale_arcsec"]) / 3600.0
                except (TypeError, ValueError):
                    scale_deg = None
        w = metadata.get("image_width") or metadata.get("width")
        h = metadata.get("image_height") or metadata.get("height")
        if ra_c is None:
            ra_c = metadata.get("ra_center") or metadata.get("ra")
        if dec_c is None:
            dec_c = metadata.get("dec_center") or metadata.get("dec")
        source = "solved" if (astro.get("ra_center") is not None and astro.get("dec_center") is not None) else "approximate"
    else:
        ra_c = metadata.get("ra_center") or metadata.get("ra")
        dec_c = metadata.get("dec_center") or metadata.get("dec")
        scale_deg = metadata.get("scale_deg")
        if scale_deg is None and metadata.get("scale_arcsec") is not None:
            try:
                scale_deg = float(metadata["scale_arcsec"]) / 3600.0
            except (TypeError, ValueError):
                scale_deg = None
        w = metadata.get("image_width") or metadata.get("width")
        h = metadata.get("image_height") or metadata.get("height")
        source = "approximate"
    if ra_c is None or dec_c is None:
        return None, None, "missing"
    if scale_deg is None or scale_deg <= 0 or w is None or h is None:
        return None, None, "missing"
    try:
        ra_c = float(ra_c)
        dec_c = float(dec_c)
        scale = float(scale_deg)
        width = int(w)
        height = int(h)
    except (TypeError, ValueError):
        return None, None, "missing"
    cos_dec = math.cos(math.radians(dec_c))
    dx_deg = (x_px - width / 2.0) * scale
    dy_deg = (height / 2.0 - y_px) * scale
    ra_deg = ra_c + dx_deg / cos_dec if cos_dec != 0 else ra_c
    dec_deg = dec_c + dy_deg
    return ra_deg, dec_deg, source


def _position_matched_in_validation(x: float, y: float, validation: Dict[str, Any]) -> bool:
    """True if (x,y) is within tolerance of any satellite or asteroid match."""
    for key in ("satellite_crosscheck", "asteroid_crosscheck"):
        check = validation.get(key) or {}
        matches = check.get("matches") if isinstance(check, dict) else []
        if not isinstance(matches, list):
            continue
        for m in matches:
            try:
                mx = float(m.get("x", 0) or 0)
                my = float(m.get("y", 0) or 0)
                if abs(x - mx) <= _POSITION_MATCH_PX and abs(y - my) <= _POSITION_MATCH_PX:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _track_acceptable_for_report(track: Dict[str, Any], validation: Dict[str, Any]) -> bool:
    """Strict: not artifact, 3+ points, not matched to satellite/asteroid, confidence medium/high."""
    if track.get("classification_hint") == "likely_artifact":
        return False
    if track.get("rejection_reason") in ("insufficient_points", "aberrant_speed"):
        return False
    points = track.get("points") or []
    if len(points) < 3:
        return False
    conf = (track.get("confidence") or "").lower()
    if conf not in ("medium", "high"):
        return False
    last = points[-1] if points else {}
    x = float(last.get("x", 0) or 0)
    y = float(last.get("y", 0) or 0)
    if _position_matched_in_validation(x, y, validation):
        return False
    return True


def _transient_acceptable_for_report(change: Dict[str, Any]) -> bool:
    """Strict: possible_supernova or new_object (unknown_transient), confidence medium/high."""
    cl = (change.get("classification") or "").strip()
    if cl not in ("possible_supernova", "new_object"):
        return False
    conf = (change.get("confidence") or "").lower()
    return conf in ("medium", "high")


def build_mpc_candidate_report(
    image_metadata: Optional[Dict[str, Any]],
    motion_tracking: Optional[Dict[str, Any]],
    moving_object_validation: Optional[Dict[str, Any]],
    discovery_engine_result: Optional[Dict[str, Any]],
    observatory_config: Optional[Dict[str, Any]] = None,
    source_image: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build an MPC candidate report from pipeline outputs.

    - If no observatory code → status "draft".
    - If observatory code "XXX" → draft / observatory-code-request mode.
    - If real code → "ready_for_validation" (submission still requires explicit enable later).

    Only includes candidates that pass strict filters (not satellite/asteroid, 3+ points
    for motion, confidence medium/high, etc.).
    """
    empty_report: Dict[str, Any] = {
        "status": "draft",
        "observatory_code": None,
        "candidate_count": 0,
        "candidates": [],
        "submission_format": "ADES_PSV",
        "ack_requested": False,
        "summary": "No MPC-ready candidates.",
    }
    try:
        image_metadata = image_metadata or {}
        motion_tracking = motion_tracking or {}
        moving_object_validation = moving_object_validation or {}
        discovery_engine_result = discovery_engine_result or {}
    except Exception:
        return empty_report

    cfg = _get_observatory_config(observatory_config)
    obs_code = (cfg.get("observatory_code") or "").strip()
    ack = bool(cfg.get("ack_enabled"))

    if not obs_code:
        status = "draft"
        summary_note = "Draft only: no observatory code configured (set MPC_OBSERVATORY_CODE)."
    elif obs_code.upper() == "XXX":
        status = "draft"
        summary_note = "Draft only: observatory code XXX indicates request-support / new-site mode."
    else:
        status = "ready_for_validation"
        summary_note = "Report validation-ready; do not submit to MPC unless explicitly enabled."

    obs_time_utc = _observation_time_utc_from_metadata(image_metadata)
    candidates_out: List[Dict[str, Any]] = []
    seen_ids: set = set()
    candidate_idx = 0

    # From discovery_engine_result, keep only candidates that pass strict filters
    discovery_candidates = discovery_engine_result.get("candidates") or []
    if not isinstance(discovery_candidates, list):
        discovery_candidates = []

    for c in discovery_candidates:
        if not isinstance(c, dict):
            continue
        ctype = (c.get("type") or "unknown_object").strip()
        confidence = (c.get("confidence") or "low").lower()
        x = float(c.get("x", 0) or 0)
        y = float(c.get("y", 0) or 0)

        if _position_matched_in_validation(x, y, moving_object_validation):
            continue
        if confidence not in ("medium", "high"):
            continue

        if ctype == "candidate_asteroid":
            # Verify a track exists with 3+ points and not artifact
            tracks = motion_tracking.get("tracks") or []
            found_ok_track = False
            if isinstance(tracks, list):
                for t in tracks:
                    if isinstance(t, dict) and _track_acceptable_for_report(t, moving_object_validation):
                        pts = t.get("points") or []
                        if len(pts) >= 3:
                            last_pt = pts[-1]
                            lx = float(last_pt.get("x", 0) or 0)
                            ly = float(last_pt.get("y", 0) or 0)
                            if abs(lx - x) <= _POSITION_MATCH_PX and abs(ly - y) <= _POSITION_MATCH_PX:
                                found_ok_track = True
                                break
            if not found_ok_track and tracks:
                continue
        elif ctype in ("candidate_supernova", "unknown_transient"):
            pass
        else:
            ctype = "unknown_object"

        candidate_idx += 1
        cid = f"ASTROSCAN-C{candidate_idx}"
        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        ra_deg, dec_deg, astrometry_source = _pixel_to_ra_dec(x, y, image_metadata)
        mag_est = None  # No fabrication; leave null if not available

        candidates_out.append({
            "candidate_id": cid,
            "object_type": "candidate_asteroid" if ctype == "candidate_asteroid" else ("candidate_transient" if ctype == "candidate_supernova" else "unknown_object"),
            "observation_time_utc": obs_time_utc or "",
            "ra_deg": ra_deg,
            "dec_deg": dec_deg,
            "magnitude_estimate": mag_est,
            "confidence": confidence,
            "source_image": source_image or "",
            "notes": "",
            "astrometry_source": astrometry_source,
        })

    return {
        "status": status,
        "observatory_code": obs_code or None,
        "candidate_count": len(candidates_out),
        "candidates": candidates_out,
        "submission_format": "ADES_PSV",
        "ack_requested": ack,
        "summary": summary_note if not candidates_out else f"{len(candidates_out)} candidate(s); {summary_note}",
    }


def validate_report_readiness(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check whether the report is ready for validation/submission.
    Returns { "ready": bool, "missing_fields": [...], "warnings": [...] }.
    """
    missing: List[str] = []
    warnings: List[str] = []
    try:
        report = report or {}
    except Exception:
        return {"ready": False, "missing_fields": ["report invalid"], "warnings": []}

    if not report.get("observatory_code"):
        missing.append("observatory_code")
    elif (report.get("observatory_code") or "").upper() == "XXX":
        warnings.append("Observatory code XXX is for request-support only; not for submission.")

    candidates = report.get("candidates") or []
    if not candidates:
        warnings.append("No candidates in report.")
    any_approximate_or_missing = False
    for i, c in enumerate(candidates):
        if not isinstance(c, dict):
            continue
        if not c.get("observation_time_utc"):
            missing.append(f"candidates[{i}].observation_time_utc")
        if c.get("ra_deg") is None and c.get("dec_deg") is None:
            missing.append(f"candidates[{i}].ra_dec (astrometric calibration)")
        if c.get("confidence") == "low":
            warnings.append(f"Candidate {c.get('candidate_id', i)} has low confidence.")
        src = c.get("astrometry_source") or "missing"
        if src in ("approximate", "missing"):
            any_approximate_or_missing = True
    if any_approximate_or_missing:
        warnings.append("Astrometry is approximate; plate-solving recommended before submission.")

    ready = len(missing) == 0 and bool(report.get("observatory_code")) and (report.get("observatory_code") or "").upper() != "XXX"
    return {
        "ready": ready,
        "missing_fields": missing,
        "warnings": warnings,
    }


def export_ades_psv(report: Dict[str, Any], output_path: Any) -> None:
    """
    Write an ADES-style PSV (pipe-separated) draft file.
    Does not claim full ADES compliance; marks draft/incomplete when required fields missing.
    Includes observatory code, submitter info if available, AC2/ACK option, and observation rows.
    """
    path = Path(output_path) if output_path is not None else None
    if path is None:
        return
    try:
        report = report or {}
    except Exception:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    # Header: AC2 / ACK if requested
    if report.get("ack_requested"):
        lines.append("# ACK")
    lines.append("# ADES PSV draft — generated by AstroScan. Do not submit without validation.")
    obs_code = report.get("observatory_code") or ""
    if not obs_code or obs_code.upper() == "XXX":
        lines.append("# DRAFT ONLY — no valid observatory code")
    lines.append("# observatory_code|submitter_name|submitter_email")
    # Submitter from config (we don't store it in report; could be added to report in build_mpc_candidate_report)
    submitter_name = os.environ.get("MPC_SUBMITTER_NAME") or ""
    submitter_email = os.environ.get("MPC_SUBMITTER_EMAIL") or ""
    lines.append(f"{obs_code}|{submitter_name}|{submitter_email}")
    lines.append("# permID|provID|trkSub|mode|stn|trk|obsTime|ra|dec|mag|band|astCat|remarks")
    # Minimal ADES-like columns for each candidate
    candidates = report.get("candidates") or []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        perm_id = c.get("candidate_id") or ""
        obs_time = (c.get("observation_time_utc") or "").replace(" ", "T")[:19]
        ra = c.get("ra_deg")
        dec = c.get("dec_deg")
        ra_s = str(ra) if ra is not None else ""
        dec_s = str(dec) if dec is not None else ""
        mag = c.get("magnitude_estimate")
        mag_s = str(mag) if mag is not None else ""
        # stn = observatory code
        row = f"{perm_id}|||S|{obs_code}||||{obs_time}|{ra_s}|{dec_s}|{mag_s}||||"
        lines.append(row)
    if not candidates:
        lines.append("# No observation rows — incomplete draft")
    text = "\n".join(lines)
    try:
        path.write_text(text, encoding="utf-8")
    except Exception as e:
        log.warning("mpc_reporter: export_ades_psv write failed: %s", e)
