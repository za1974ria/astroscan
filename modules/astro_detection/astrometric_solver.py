# -*- coding: utf-8 -*-
"""
AstroScan — Astrometric Solver (Astrometry.net).

Solves astronomical images astrometrically to obtain RA/Dec center,
orientation, pixel scale, and WCS status. Supports web API (nova.astrometry.net)
and local solve-field. Does not fake solutions; returns explicit failure when
solve fails. Does not auto-submit unless explicitly configured.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

BASE_URL = "https://nova.astrometry.net"
DEFAULT_TIMEOUT_SEC = 120
POLL_INTERVAL_SEC = 3


def _get_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build solver config from env and optional dict. No secrets hardcoded."""
    c = config or {}
    return {
        "mode": (os.environ.get("ASTROMETRY_MODE") or c.get("mode") or "disabled").strip().lower(),
        "api_key": os.environ.get("ASTROMETRY_NET_API_KEY") or c.get("api_key") or "",
        "timeout_sec": int(os.environ.get("ASTROMETRY_TIMEOUT_SEC") or c.get("timeout_sec") or DEFAULT_TIMEOUT_SEC),
        "solve_field_bin": os.environ.get("ASTROMETRY_LOCAL_SOLVE_FIELD_BIN") or c.get("solve_field_bin") or "solve-field",
        "index_dir": os.environ.get("ASTROMETRY_LOCAL_INDEX_DIR") or c.get("index_dir") or "",
    }


def _failure_result(
    solver_mode: str,
    error: str,
    summary: str,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Standard failure structure; never fake solved=True."""
    return {
        "solved": False,
        "solver_mode": solver_mode,
        "wcs_file": None,
        "new_fits_file": None,
        "ra_center": None,
        "dec_center": None,
        "pixel_scale_arcsec_per_px": None,
        "orientation_deg": None,
        "parity": None,
        "field_width_deg": None,
        "field_height_deg": None,
        "warnings": list(warnings or []),
        "error": error,
        "summary": summary,
    }


def _login_web_api(api_key: str, timeout: int) -> Optional[str]:
    """Login to nova.astrometry.net; return session key or None."""
    if not api_key or not api_key.strip():
        return None
    try:
        import urllib.request
        import urllib.parse
        data = urllib.parse.urlencode({"request-json": '{"apikey": "%s"}' % api_key.replace('"', '\\"')}).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/api/login",
            data=data,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": f"{BASE_URL}/api/login"},
        )
        with urllib.request.urlopen(req, timeout=min(30, timeout)) as resp:
            import json
            out = json.loads(resp.read().decode())
            if out.get("status") == "success":
                return out.get("session")
    except Exception as e:
        log.debug("astrometric_solver: web API login failed: %s", e)
    return None


def _submit_image_web_api(session: str, image_path: Path, timeout: int) -> Optional[int]:
    """Upload image to nova.astrometry.net; return submission id (subid) or None."""
    if not session or not image_path or not image_path.exists():
        return None
    try:
        import urllib.request
        import json
        with open(image_path, "rb") as f:
            img_data = f.read()
        boundary = "----AstroScanBoundary"
        req_json = json.dumps({"session": session})
        body = (
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="request-json"\r\n\r\n'
            + req_json.encode("utf-8") + b"\r\n"
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="file"; filename="image"\r\n'
            b"Content-Type: application/octet-stream\r\n\r\n"
            + img_data + b"\r\n"
            b"--" + boundary + b"--\r\n"
        )
        req = urllib.request.Request(
            f"{BASE_URL}/api/upload",
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Referer": f"{BASE_URL}/api/login",
            },
        )
        with urllib.request.urlopen(req, timeout=min(60, timeout)) as resp:
            out = json.loads(resp.read().decode())
            if out.get("status") == "success" and "subid" in out:
                return int(out["subid"])
    except Exception as e:
        log.debug("astrometric_solver: web API upload failed: %s", e)
    return None


def _poll_job_status(sub_id: int, timeout: int) -> Optional[Dict[str, Any]]:
    """Poll submission until jobs appear and one job completes. Return job info dict or None."""
    try:
        import urllib.request
        import json
        deadline = time.time() + timeout
        job_ids = []
        while time.time() < deadline:
            req = urllib.request.Request(
                f"{BASE_URL}/api/submissions/{sub_id}",
                headers={"Referer": f"{BASE_URL}/api/login"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            jobs = data.get("jobs") or []
            if jobs:
                job_ids = [int(j) for j in jobs]
                break
            time.sleep(POLL_INTERVAL_SEC)
        if not job_ids:
            return None
        for jid in job_ids:
            req = urllib.request.Request(
                f"{BASE_URL}/api/jobs/{jid}",
                headers={"Referer": f"{BASE_URL}/api/login"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                job = json.loads(resp.read().decode())
            status = job.get("status")
            if status == "Success":
                return {"job_id": jid, "job": job}
            if status in ("Failure", "failure"):
                return None
        return None
    except Exception as e:
        log.debug("astrometric_solver: poll job failed: %s", e)
    return None


def _fetch_job_calibration(job_id: int, timeout: int) -> Dict[str, Any]:
    """Fetch calibration/WCS info for a successful job. Return dict with ra, dec, scale, etc. if available."""
    out = {}
    try:
        import urllib.request
        import json
        req = urllib.request.Request(
            f"{BASE_URL}/api/jobs/{job_id}/calibration",
            headers={"Referer": f"{BASE_URL}/api/login"},
        )
        with urllib.request.urlopen(req, timeout=min(30, timeout)) as resp:
            data = json.loads(resp.read().decode())
        if isinstance(data, dict):
            out = data
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            out = data[0]
    except Exception as e:
        log.debug("astrometric_solver: fetch calibration failed: %s", e)
    return out


def _parse_web_calibration(cal: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]:
    """Extract ra_center, dec_center, pixel_scale_arcsec, orientation_deg, width_deg, height_deg from API calibration."""
    ra = dec = scale = orient = w_deg = h_deg = None
    try:
        if "ra" in cal:
            ra = float(cal["ra"])
        if "dec" in cal:
            dec = float(cal["dec"])
        if "pixscale" in cal:
            scale = float(cal["pixscale"])
        if "orientation" in cal:
            orient = float(cal["orientation"])
        if "width" in cal:
            w_deg = float(cal["width"])
        if "height" in cal:
            h_deg = float(cal["height"])
        if "scale" in cal and scale is None:
            scale = float(cal["scale"])
    except (TypeError, ValueError):
        pass
    return ra, dec, scale, orient, w_deg, h_deg


def _solve_web_api(image_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    """Run web API solve; return full result structure."""
    api_key = (config.get("api_key") or "").strip()
    timeout = max(10, config.get("timeout_sec") or DEFAULT_TIMEOUT_SEC)
    if not api_key:
        return _failure_result(
            "web_api",
            "API key missing",
            "Astrometric solving unavailable: web API key not configured (ASTROMETRY_NET_API_KEY).",
            ["Set ASTROMETRY_NET_API_KEY to use nova.astrometry.net"],
        )
    session = _login_web_api(api_key, timeout)
    if not session:
        return _failure_result(
            "web_api",
            "Login failed",
            "Astrometric solution unavailable: web API login failed.",
            [],
        )
    sub_id = _submit_image_web_api(session, image_path, timeout)
    if sub_id is None:
        return _failure_result(
            "web_api",
            "Upload failed",
            "Astrometric solution unavailable: image upload failed.",
            [],
        )
    job_info = _poll_job_status(sub_id, timeout)
    if not job_info:
        return _failure_result(
            "web_api",
            "Solve failed or timeout",
            "Astrometric solution unavailable: web API timeout or solve failure.",
            [],
        )
    cal = _fetch_job_calibration(job_info["job_id"], timeout)
    ra, dec, scale, orient, w_deg, h_deg = _parse_web_calibration(cal)
    parity = None
    try:
        if "parity" in cal:
            parity = int(cal["parity"])
    except (TypeError, ValueError):
        pass
    return {
        "solved": True,
        "solver_mode": "web_api",
        "wcs_file": None,
        "new_fits_file": None,
        "ra_center": ra,
        "dec_center": dec,
        "pixel_scale_arcsec_per_px": scale,
        "orientation_deg": orient,
        "parity": parity,
        "field_width_deg": w_deg,
        "field_height_deg": h_deg,
        "warnings": [] if (ra is not None and dec is not None) else ["Incomplete calibration from API"],
        "error": None,
        "summary": "Astrometric solution completed successfully.",
    }


def _solve_locally(image_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    """Run local solve-field; parse wcsinfo if available. Return full result structure."""
    bin_path = (config.get("solve_field_bin") or "solve-field").strip()
    index_dir = (config.get("index_dir") or "").strip()
    try:
        proc = subprocess.run(
            [bin_path, "--help"],
            capture_output=True,
            timeout=5,
        )
        if proc.returncode != 0 and not (proc.stdout or proc.stderr):
            return _failure_result(
                "local",
                "solve-field not found",
                "Local astrometry.net solver not found.",
                [f"Binary: {bin_path}"],
            )
    except FileNotFoundError:
        return _failure_result(
            "local",
            "solve-field not found",
            "Local astrometry.net solver not found.",
            [f"Binary: {bin_path}"],
        )
    except subprocess.TimeoutExpired:
        pass
    out_dir = image_path.parent
    base = image_path.stem
    wcs_path = out_dir / (base + ".wcs")
    new_fits_path = out_dir / (base + ".new")
    cmd = [bin_path, "--no-plot", "--no-fits2fits", "-o", base, str(image_path)]
    if index_dir:
        cmd.extend(["--index-dir", index_dir])
    try:
        subprocess.run(cmd, cwd=str(out_dir), capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        return _failure_result("local", "Timeout", "Local astrometric solve timed out.", [])
    except Exception as e:
        return _failure_result("local", str(e), "Local astrometric solve failed.", [])
    if not wcs_path.exists():
        return _failure_result(
            "local",
            "No WCS output",
            "Local astrometric solve did not produce a WCS file.",
            [],
        )
    ra = dec = scale = orient = w_deg = h_deg = None
    wcsinfo_bin = "wcsinfo"
    try:
        result = subprocess.run(
            [wcsinfo_bin, str(wcs_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("ra_center"):
                    try:
                        ra = float(line.split(None, 1)[1])
                    except (IndexError, ValueError):
                        pass
                elif line.startswith("dec_center"):
                    try:
                        dec = float(line.split(None, 1)[1])
                    except (IndexError, ValueError):
                        pass
                elif line.startswith("pixscale"):
                    try:
                        scale = float(line.split(None, 1)[1])
                    except (IndexError, ValueError):
                        pass
                elif "orientation" in line.lower():
                    try:
                        parts = line.split()
                        for i, p in enumerate(parts):
                            if i > 0:
                                orient = float(p)
                                break
                    except (IndexError, ValueError):
                        pass
                elif "field_w" in line or "width" in line.lower():
                    try:
                        w_deg = float(line.split(None, 1)[1])
                    except (IndexError, ValueError):
                        pass
                elif "field_h" in line or "height" in line.lower():
                    try:
                        h_deg = float(line.split(None, 1)[1])
                    except (IndexError, ValueError):
                        pass
    except FileNotFoundError:
        pass
    except Exception:
        pass
    parity = None
    return {
        "solved": True,
        "solver_mode": "local",
        "wcs_file": str(wcs_path),
        "new_fits_file": str(new_fits_path) if new_fits_path.exists() else None,
        "ra_center": ra,
        "dec_center": dec,
        "pixel_scale_arcsec_per_px": scale,
        "orientation_deg": orient,
        "parity": parity,
        "field_width_deg": w_deg,
        "field_height_deg": h_deg,
        "warnings": [] if (ra is not None and dec is not None) else ["Incomplete WCS parsing from wcsinfo"],
        "error": None,
        "summary": "Astrometric solution completed successfully.",
    }


def solve_astrometry(
    image_path: Any,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Solve an image astrometrically (Astrometry.net web API or local).

    - If mode is disabled or missing → return safe "disabled" result.
    - If web_api and no API key → return failure with message.
    - If local and binary missing → return failure.
    - Never fabricate RA/Dec, scale, or orientation; leave null on failure or incomplete solve.

    Returns:
        solved, solver_mode, wcs_file, new_fits_file, ra_center, dec_center,
        pixel_scale_arcsec_per_px, orientation_deg, parity, field_width_deg, field_height_deg,
        warnings, error, summary
    """
    path = Path(image_path) if image_path is not None else None
    cfg = _get_config(config)
    mode = (cfg.get("mode") or "disabled").strip().lower()

    if path is None or not path.exists():
        return _failure_result(
            "disabled",
            "Missing or invalid image path",
            "Astrometric solving skipped: no image or path invalid.",
            [],
        )

    if path.suffix.lower() not in (".fits", ".fit", ".png", ".jpg", ".jpeg"):
        return _failure_result(
            "disabled",
            "Unsupported format",
            "Astrometric solving skipped: unsupported image format.",
            [f"Supported: FITS, PNG, JPG. Got: {path.suffix}"],
        )

    if mode not in ("web_api", "local"):
        return _failure_result(
            "disabled",
            None,
            "Astrometric solving disabled by configuration.",
            ["Set ASTROMETRY_MODE=web_api or local to enable."],
        )

    if mode == "web_api":
        return _solve_web_api(path, cfg)
    return _solve_locally(path, cfg)


def astrometry_solution_for_metadata(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the astrometry_solution block to persist in image metadata JSON.
    Does not delete existing metadata fields; merge this under "astrometry_solution".
    """
    r = result or {}
    if r.get("solved"):
        return {
            "solved": True,
            "solver_mode": r.get("solver_mode"),
            "ra_center": r.get("ra_center"),
            "dec_center": r.get("dec_center"),
            "pixel_scale_arcsec_per_px": r.get("pixel_scale_arcsec_per_px"),
            "orientation_deg": r.get("orientation_deg"),
            "field_width_deg": r.get("field_width_deg"),
            "field_height_deg": r.get("field_height_deg"),
            "wcs_file": r.get("wcs_file"),
            "warnings": list(r.get("warnings") or []),
        }
    return {
        "solved": False,
        "solver_mode": r.get("solver_mode"),
        "warnings": list(r.get("warnings") or []),
        "error": r.get("error"),
    }
