"""AstroScan cloud bridge subpackage (TB-35).

Holds the outbound HTTP client used by `cloud-pair` and `cloud-run`.
The telescope hardware adapters (mock / alpaca) remain strictly
read-only and untouched; this subpackage talks ONLY to the AstroScan
cloud bridge endpoints on the operator-supplied base URL.
"""
from astroscan_bridge.cloud.client import (
    CloudBridgeClient,
    CloudHttpSession,
    mask_token,
)

__all__ = ["CloudBridgeClient", "CloudHttpSession", "mask_token"]
