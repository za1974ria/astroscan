#!/bin/bash
echo "=== CHECK PORT 5003 ==="
ss -tulpn | grep 5003 || echo "OK: aucun conflit"

echo "=== PROCESS GUNICORN ==="
ps aux | grep gunicorn | grep -v grep
