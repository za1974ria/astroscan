#!/bin/bash
# Sprint 3 — Re-audit ciblé sur les 9 modules touchés
set +e

export PATH="/home/zakaria/.npm-global/bin:$PATH"
export CHROME_PATH="/home/zakaria/.cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome"

AUDIT_DIR="/root/astro_scan/audit"
OUT_DIR="${AUDIT_DIR}/reports/sprint3_quick_check_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"

declare -A BEFORE=(
  [overlord_live]="57/96/100/100"
  [observatoire]="68/90/96/100"
  [carte_du_ciel]="74/93/100/100"
  [aladin]="78/93/100/100"
  [orbital_map]="78/100/96/100"
  [scientific]="79/93/100/100"
  [maintenance]="80/93/100/100"
  [mission_control]="82/92/96/100"
  [nasa_apod]="85/100/100/100"
)

declare -A URLS=(
  [overlord_live]="/overlord_live"
  [observatoire]="/observatoire"
  [carte_du_ciel]="/carte-du-ciel"
  [aladin]="/aladin"
  [orbital_map]="/orbital-map"
  [scientific]="/scientific"
  [maintenance]="/maintenance"
  [mission_control]="/mission-control"
  [nasa_apod]="/nasa-apod"
)

OUT_TABLE="${OUT_DIR}/COMPARISON.md"
cat > "$OUT_TABLE" <<EOF
# Sprint 3 — Quick check Lighthouse (perf)

| Module | URL | AVANT (P/A/BP/SEO) | APRÈS (P/A/BP/SEO) |
|--------|-----|--------------------|--------------------|
EOF

for module in overlord_live observatoire carte_du_ciel aladin orbital_map scientific maintenance mission_control nasa_apod; do
  url="${URLS[$module]}"
  full="https://astroscan.space${url}"
  JSON="${OUT_DIR}/${module}.json"
  echo "🔍 ${module} → ${full}"
  timeout 90 lighthouse "${full}" \
    --output=json \
    --output-path="${JSON}" \
    --chrome-flags="--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage" \
    --preset=desktop --locale=fr --quiet --max-wait-for-load=60000 \
    > /dev/null 2>&1

  if [ ! -f "$JSON" ]; then
    echo "| ${module} | \`${url}\` | ${BEFORE[$module]} | ❌ FAILED |" >> "$OUT_TABLE"
    continue
  fi

  P=$(jq -r '(.categories.performance.score // 0) * 100 | round' "$JSON")
  A=$(jq -r '(.categories.accessibility.score // 0) * 100 | round' "$JSON")
  BP=$(jq -r '(.categories["best-practices"].score // 0) * 100 | round' "$JSON")
  SEO=$(jq -r '(.categories.seo.score // 0) * 100 | round' "$JSON")
  AFTER="${P}/${A}/${BP}/${SEO}"
  echo "  → ${AFTER}"
  echo "| ${module} | \`${url}\` | ${BEFORE[$module]} | ${AFTER} |" >> "$OUT_TABLE"
done

echo ""
echo "📄 $OUT_TABLE"
cat "$OUT_TABLE"
