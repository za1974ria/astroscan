#!/usr/bin/env python3
import base64, gzip, os, shutil, sys

# Charge DATA depuis fichier ou stdin (pour script avec DATA= trop long pour un seul fichier)
out = '/root/astro_scan/templates/observatoire.html'
payload_file = '/root/astro_scan/payload_observatoire.b64'
if os.path.exists(payload_file):
    DATA = open(payload_file).read()
elif not os.isatty(0):
    DATA = sys.stdin.read()
else:
    raise SystemExit(f'Mettre le payload base64 dans {payload_file} ou le passer en stdin.')

if os.path.exists(out):
    shutil.copy(out, out + '.bak')
content = gzip.decompress(base64.b64decode(DATA))
open(out, 'wb').write(content)
lines = len(content.splitlines())
print(f'OK — {lines} lignes')
