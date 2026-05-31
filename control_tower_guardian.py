import time
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HEALTH_URL = "http://127.0.0.1:5003/health"
LOG_FILE = Path("/root/astro_scan/logs/guardian_watchdog.log")
KILL_SWITCH = Path("/root/astro_scan/runtime/remediation.disabled")
COOLDOWN_FILE = Path("/root/astro_scan/runtime/guardian_last_restart.txt")
COOLDOWN_SECONDS = 600

def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with open(LOG_FILE, "a") as f:
        f.write(f"{ts} | {msg}\n")

def health_ok():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=5) as r:
            return 200 <= r.status < 300
    except Exception:
        return False

def cooldown_ok():
    if not COOLDOWN_FILE.exists():
        return True
    try:
        last = float(COOLDOWN_FILE.read_text().strip())
        return time.time() - last >= COOLDOWN_SECONDS
    except Exception:
        return True

def restart_astroscan():
    if KILL_SWITCH.exists():
        log("BLOCKED | kill switch active")
        return

    if not cooldown_ok():
        log("BLOCKED | cooldown active")
        return

    log("ACTION | restarting astroscan")
    try:
        subprocess.run(
            ["sudo", "-n", "/usr/bin/systemctl", "restart", "astroscan"],
            timeout=30,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        COOLDOWN_FILE.write_text(str(time.time()))
        log("RESULT | restart success")
    except Exception as e:
        log(f"RESULT | restart failed | {e}")

def main():
    log("START | guardian watchdog online")
    while True:
        if not health_ok():
            log("DETECTED | astroscan health down")
            restart_astroscan()
        time.sleep(10)

if __name__ == "__main__":
    main()
