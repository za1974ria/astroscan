#!/usr/bin/env python3
"""
deploy_europe_live.py
=====================
Déploiement atomique CTO-grade de europe_live.html
sur AstroScan Orbital (Hetzner 5.78.153.17 · /opt/astroscan).

Action :
  1. Backup horodaté du template courant
  2. Écriture atomique du nouveau template (single source of truth)
  3. chown astroscan:astroscan · chmod 644
  4. systemctl reload astroscan (fallback restart)
  5. Health check HTTPS + sanity check markers HTML
  6. Affiche les instructions cache busting navigateur

Exécution :
  sudo python3 /root/astro_scan/scripts/deploy_europe_live.py
"""

from __future__ import annotations

import os
import pwd
import grp
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import ssl
from datetime import datetime
from pathlib import Path

# ─── Paramètres déploiement ───────────────────────────────────────────────────
TARGET     = Path("/opt/astroscan/templates/europe_live.html")
OWNER_USER = "astroscan"
OWNER_GROUP = "astroscan"
FILE_MODE  = 0o644
SERVICE    = "astroscan"
HEALTH_URL = "https://astroscan.space/europe-live"

# ─── Streams HLS (sources publiques, distinctes) ──────────────────────────────
STREAM_A = "https://cph-p2p-msl.akamaized.net/hls/live/2000341/test/master.m3u8"
STREAM_B = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"

# ─── Template HTML — single source of truth ───────────────────────────────────
TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AstroScan — World Live Engine</title>

<!--
  WORLD LIVE ENGINE · AstroScan Orbital
  Architecture HLS native (hls.js) + fallback poster.
  Pour brancher un autre flux : éditer data-hls sur la balise <video data-card>.
-->

<style>
:root{
    --bg:#020b16;
    --cyan:#00d9ff;
    --cyan-soft:#7fdfff;
    --card:#07182a;
    --border:#0f3d5e;
    --live:#00ff9d;
    --standby:#ffb347;
}

*{box-sizing:border-box;}

body{
    margin:0;
    background:var(--bg);
    color:var(--cyan);
    font-family:Arial,Helvetica,sans-serif;
    min-height:100vh;
}

.wrap{
    max-width:1600px;
    margin:auto;
    padding:30px;
}

.title{
    font-size:64px;
    font-weight:800;
    margin-bottom:8px;
    letter-spacing:4px;
}

.subtitle{
    color:var(--cyan-soft);
    font-size:14px;
    letter-spacing:2px;
    margin-bottom:30px;
    opacity:.8;
}

.grid{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:24px;
}

.card{
    background:var(--card);
    border:1px solid var(--border);
    border-radius:18px;
    overflow:hidden;
    box-shadow:0 0 40px rgba(0,217,255,.08);
}

.head{
    display:flex;
    justify-content:space-between;
    align-items:center;
    padding:18px 22px;
    border-bottom:1px solid var(--border);
}

.city{
    font-size:34px;
    font-weight:700;
    letter-spacing:2px;
}

.badge{
    display:inline-flex;
    align-items:center;
    gap:8px;
    border:1px solid var(--live);
    color:var(--live);
    border-radius:999px;
    padding:6px 14px;
    font-size:13px;
    font-weight:700;
    letter-spacing:1px;
}

.badge .dot{
    width:8px;height:8px;border-radius:50%;
    background:var(--live);
    box-shadow:0 0 8px var(--live);
    animation:livepulse 1.4s ease-in-out infinite;
}

.badge[data-state="standby"]{
    border-color:var(--standby);
    color:var(--standby);
}
.badge[data-state="standby"] .dot{
    background:var(--standby);
    box-shadow:0 0 8px var(--standby);
    animation-duration:2.4s;
}

@keyframes livepulse{
    0%,100%{opacity:1;transform:scale(1);}
    50%{opacity:.35;transform:scale(.7);}
}

.stage{
    position:relative;
    width:100%;
    aspect-ratio:16/9;
    background:#000;
    overflow:hidden;
}

.stage video,
.stage .poster{
    position:absolute;
    inset:0;
    width:100%;
    height:100%;
    object-fit:cover;
    display:block;
}

.stage .poster{z-index:1;transition:opacity .4s ease;}
.stage video{z-index:2;opacity:0;transition:opacity .4s ease;}
.stage.playing video{opacity:1;}
.stage.playing .poster{opacity:0;}

.stage .scan{
    position:absolute;inset:0;z-index:3;
    pointer-events:none;
    background:
        linear-gradient(transparent 0%,rgba(0,217,255,.04) 50%,transparent 100%),
        repeating-linear-gradient(
            to bottom,
            rgba(0,217,255,.06) 0,
            rgba(0,217,255,.06) 1px,
            transparent 1px,
            transparent 3px
        );
    mix-blend-mode:screen;
}

.footer{
    display:flex;
    justify-content:space-between;
    align-items:center;
    padding:16px 22px;
    color:var(--cyan-soft);
    font-size:14px;
    letter-spacing:1px;
}

.footer .clock{
    font-variant-numeric:tabular-nums;
    font-weight:700;
    color:var(--cyan);
}

@media(max-width:1000px){
    .grid{grid-template-columns:1fr;}
    .title{font-size:42px;}
    .city{font-size:26px;}
}
</style>
</head>

<body>

<div class="wrap">
    <div class="title">WORLD LIVE ENGINE</div>
    <div class="subtitle">ASTROSCAN ORBITAL · HLS NATIVE STREAM</div>

    <div class="grid">

        <article class="card">
            <div class="head">
                <div class="city">TOKYO CENTRAL</div>
                <div class="badge" data-badge><span class="dot"></span><span data-badge-label>LIVE</span></div>
            </div>
            <div class="stage">
                <img class="poster"
                     src="https://images.unsplash.com/photo-1542051841857-5f90071e7989?q=80&w=1600&auto=format&fit=crop"
                     alt="Tokyo Central standby">
                <video data-card
                       data-hls="__STREAM_A__"
                       autoplay muted loop playsinline
                       preload="none"
                       crossorigin="anonymous"></video>
                <div class="scan"></div>
            </div>
            <div class="footer">
                <span>Tokyo Central · JST</span>
                <span class="clock" data-clock="Asia/Tokyo"></span>
            </div>
        </article>

        <article class="card">
            <div class="head">
                <div class="city">SHIBUYA CROSSING</div>
                <div class="badge" data-badge><span class="dot"></span><span data-badge-label>LIVE</span></div>
            </div>
            <div class="stage">
                <img class="poster"
                     src="https://images.unsplash.com/photo-1503899036084-c55cdd92da26?q=80&w=1600&auto=format&fit=crop"
                     alt="Shibuya Crossing standby">
                <video data-card
                       data-hls="__STREAM_B__"
                       autoplay muted loop playsinline
                       preload="none"
                       crossorigin="anonymous"></video>
                <div class="scan"></div>
            </div>
            <div class="footer">
                <span>Shibuya Crossing · JST</span>
                <span class="clock" data-clock="Asia/Tokyo"></span>
            </div>
        </article>

    </div>
</div>

<!-- hls.js — version pinned, defer, une seule fois -->
<script defer src="https://cdn.jsdelivr.net/npm/hls.js@1.5.17/dist/hls.min.js"></script>

<script>
(function(){
    "use strict";

    function tickClocks(){
        document.querySelectorAll("[data-clock]").forEach(function(el){
            var tz = el.getAttribute("data-clock");
            try{
                el.textContent = new Date().toLocaleTimeString("fr-FR", {timeZone: tz, hour12: false});
            }catch(e){
                el.textContent = "--:--:--";
            }
        });
    }
    tickClocks();
    setInterval(tickClocks, 1000);

    function setBadge(video, state){
        var wrap  = video.closest(".card");
        var badge = wrap && wrap.querySelector("[data-badge]");
        var label = badge && badge.querySelector("[data-badge-label]");
        if(!badge) return;
        if(state === "live"){
            badge.removeAttribute("data-state");
            if(label) label.textContent = "LIVE";
            var stage = video.closest(".stage");
            if(stage) stage.classList.add("playing");
        }else{
            badge.setAttribute("data-state", "standby");
            if(label) label.textContent = "STANDBY";
        }
    }

    function attach(video){
        var src = (video.getAttribute("data-hls") || "").trim();
        if(!src){ setBadge(video, "standby"); return; }

        // Safari / iOS : HLS natif
        if(video.canPlayType("application/vnd.apple.mpegurl")){
            video.src = src;
            video.addEventListener("playing", function(){ setBadge(video, "live"); }, {once:true});
            video.addEventListener("error",   function(){ setBadge(video, "standby"); }, {once:true});
            return;
        }

        // Chrome / Firefox / Edge : hls.js
        if(window.Hls && window.Hls.isSupported()){
            var hls = new window.Hls({lowLatencyMode:true, enableWorker:true});
            hls.loadSource(src);
            hls.attachMedia(video);
            hls.on(window.Hls.Events.MANIFEST_PARSED, function(){
                video.play().then(function(){ setBadge(video, "live"); })
                            .catch(function(){ setBadge(video, "standby"); });
            });
            hls.on(window.Hls.Events.ERROR, function(_, data){
                if(data && data.fatal) setBadge(video, "standby");
            });
            return;
        }

        setBadge(video, "standby");
    }

    function boot(){
        document.querySelectorAll("video[data-card]").forEach(attach);
    }

    if(document.readyState === "complete") boot();
    else window.addEventListener("load", boot);
})();
</script>

</body>
</html>
"""

# ─── Utils ────────────────────────────────────────────────────────────────────
GREEN  = "\033[32m"
RED    = "\033[31m"
YEL    = "\033[33m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
OFF    = "\033[0m"

def log(msg, color=""):
    print(f"{color}{msg}{OFF}", flush=True)

def die(msg, code=1):
    log(f"✖ {msg}", RED)
    sys.exit(code)

def run(cmd, check=True, capture=False):
    log(f"  $ {' '.join(cmd)}", DIM)
    res = subprocess.run(cmd, capture_output=capture, text=True)
    if check and res.returncode != 0:
        die(f"commande échouée (exit {res.returncode}) : {' '.join(cmd)}")
    return res

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    if os.geteuid() != 0:
        die("ce script doit être exécuté en root  ·  sudo python3 …")

    if not TARGET.exists():
        die(f"cible introuvable : {TARGET}")

    # 0) résoudre uid/gid astroscan
    try:
        uid = pwd.getpwnam(OWNER_USER).pw_uid
        gid = grp.getgrnam(OWNER_GROUP).gr_gid
    except KeyError as e:
        die(f"user/group inconnu : {e}")

    # 1) backup horodaté
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = TARGET.with_name(f"{TARGET.name}.bak-pre-cto-{stamp}")
    shutil.copy2(TARGET, bak)
    log(f"✓ backup créé · {bak}", GREEN)

    # 2) interpolation streams + écriture atomique
    content = TEMPLATE.replace("__STREAM_A__", STREAM_A).replace("__STREAM_B__", STREAM_B)

    fd, tmp_path = tempfile.mkstemp(prefix=".europe_live.", dir=str(TARGET.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.chown(tmp_path, uid, gid)
        os.chmod(tmp_path, FILE_MODE)
        os.replace(tmp_path, TARGET)
    except Exception as e:
        try: os.unlink(tmp_path)
        except FileNotFoundError: pass
        die(f"écriture atomique impossible : {e}")

    log(f"✓ template écrit · {TARGET}  ({TARGET.stat().st_size} bytes)", GREEN)

    # 3) sanity checks structurels
    raw = TARGET.read_text(encoding="utf-8")
    must = ["<!DOCTYPE html>", "WORLD LIVE ENGINE", "TOKYO CENTRAL", "SHIBUYA CROSSING",
            "hls.min.js", STREAM_A, STREAM_B, "data-card", "data-badge"]
    missing = [m for m in must if m not in raw]
    if missing:
        die(f"sanity check FAIL · markers manquants : {missing}")
    if raw.count("<!DOCTYPE") != 1 or raw.count("</html>") != 1 or raw.count("</body>") != 1:
        die("sanity check FAIL · DOCTYPE/html/body non-uniques")
    if raw.count("hls.min.js") != 1:
        die("sanity check FAIL · plusieurs inclusions hls.js détectées")
    log("✓ sanity checks structurels OK · DOCTYPE unique · streams présents · hls.js unique", GREEN)

    # 4) reload service (fallback restart si reload non supporté)
    log("→ reload astroscan", YEL)
    res = subprocess.run(["systemctl", "reload", SERVICE], capture_output=True, text=True)
    if res.returncode != 0:
        log("  reload non supporté → restart", DIM)
        run(["systemctl", "restart", SERVICE])
    time.sleep(1.5)

    # 5) health checks
    is_active = subprocess.run(["systemctl", "is-active", SERVICE],
                               capture_output=True, text=True).stdout.strip()
    if is_active != "active":
        die(f"service astroscan inactif après reload : {is_active}")
    log(f"✓ service astroscan · {is_active}", GREEN)

    ctx = ssl._create_unverified_context()
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, context=ctx, timeout=8) as r:
            body = r.read().decode("utf-8", errors="replace")
            code = r.status
    except Exception as e:
        die(f"health check HTTP KO : {e}")

    if code != 200:
        die(f"health check HTTP {code} ≠ 200")
    for marker in ("WORLD LIVE ENGINE", "TOKYO CENTRAL", "SHIBUYA CROSSING", "hls.min.js"):
        if marker not in body:
            die(f"markers absents de la réponse HTTP : {marker}")
    log(f"✓ HTTP {code} · {len(body)} bytes · markers présents", GREEN)

    # 6) instructions cache navigateur
    log("", "")
    log(f"{BOLD}─── DÉPLOIEMENT TERMINÉ ─────────────────────────────────────{OFF}", GREEN)
    log(f"  Backup        : {bak}", "")
    log(f"  Template      : {TARGET}", "")
    log(f"  Stream TOKYO  : {STREAM_A}", "")
    log(f"  Stream SHIBUYA: {STREAM_B}", "")
    log("", "")
    log(f"{BOLD}CACHE NAVIGATEUR — purge obligatoire :{OFF}", YEL)
    log("  Chrome / Firefox / Edge desktop  →  Ctrl + Shift + R", "")
    log("  macOS Safari / Chrome            →  Cmd  + Shift + R", "")
    log("  En cas de SW persistant          →  DevTools › Application › Service Workers › Unregister", "")
    log("", "")

if __name__ == "__main__":
    main()
