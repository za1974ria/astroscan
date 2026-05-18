#!/bin/bash
# Audit Lighthouse batch ASTRO-SCAN
# Usage: ./run_lighthouse_batch.sh

set +e

AUDIT_DIR="/root/astro_scan/audit"
REPORTS_DIR="${AUDIT_DIR}/reports/$(date +%Y%m%d_%H%M%S)"
ROUTES_FILE="${AUDIT_DIR}/lighthouse_routes.txt"
SUMMARY_FILE="${REPORTS_DIR}/SUMMARY.md"
BASE_URL="https://astroscan.space"

export PATH="/home/zakaria/.npm-global/bin:$PATH"
export CHROME_PATH="/home/zakaria/.cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome"

mkdir -p "${REPORTS_DIR}"

cat > "${SUMMARY_FILE}" <<EOF
# ASTRO-SCAN — Audit Lighthouse $(date '+%Y-%m-%d %H:%M:%S')

| Module | URL | Perf | A11y | BP | SEO | Status |
|--------|-----|------|------|----|----|--------|
EOF

TOTAL=0
PERFECT=0
FAILED=0

while IFS='|' read -r nom url categorie; do
    [[ "$nom" =~ ^#.*$ ]] && continue
    [[ -z "$nom" ]] && continue

    TOTAL=$((TOTAL + 1))
    FULL_URL="${BASE_URL}${url}"
    JSON_OUT="${REPORTS_DIR}/${nom}.json"

    echo "🔍 [${TOTAL}] Audit ${nom} → ${FULL_URL}"

    timeout 90 lighthouse "${FULL_URL}" \
        --output=json \
        --output-path="${JSON_OUT}" \
        --chrome-flags="--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage" \
        --preset=desktop \
        --locale=fr \
        --quiet \
        --max-wait-for-load=45000 \
        > /dev/null 2>&1

    if [[ ! -f "${JSON_OUT}" ]]; then
        echo "  ❌ ÉCHEC ${nom}"
        echo "| ${nom} | \`${url}\` | ❌ | ❌ | ❌ | ❌ | FAILED |" >> "${SUMMARY_FILE}"
        FAILED=$((FAILED + 1))
        continue
    fi

    PERF=$(jq -r '(.categories.performance.score // 0) * 100 | round' "${JSON_OUT}" 2>/dev/null)
    A11Y=$(jq -r '(.categories.accessibility.score // 0) * 100 | round' "${JSON_OUT}" 2>/dev/null)
    BP=$(jq -r '(.categories["best-practices"].score // 0) * 100 | round' "${JSON_OUT}" 2>/dev/null)
    SEO=$(jq -r '(.categories.seo.score // 0) * 100 | round' "${JSON_OUT}" 2>/dev/null)

    [[ -z "$PERF" || "$PERF" == "null" ]] && PERF=0
    [[ -z "$A11Y" || "$A11Y" == "null" ]] && A11Y=0
    [[ -z "$BP" || "$BP" == "null" ]] && BP=0
    [[ -z "$SEO" || "$SEO" == "null" ]] && SEO=0

    if [[ "$PERF" == "100" && "$A11Y" == "100" && "$BP" == "100" && "$SEO" == "100" ]]; then
        STATUS="✅ PERFECT"
        PERFECT=$((PERFECT + 1))
    elif [[ "$PERF" -lt 90 || "$A11Y" -lt 90 || "$BP" -lt 90 || "$SEO" -lt 90 ]]; then
        STATUS="🔴 CRITIQUE"
    elif [[ "$PERF" -lt 95 || "$A11Y" -lt 95 || "$BP" -lt 95 || "$SEO" -lt 95 ]]; then
        STATUS="🟠 MOYEN"
    else
        STATUS="🟡 PROCHE"
    fi

    echo "| ${nom} | \`${url}\` | ${PERF} | ${A11Y} | ${BP} | ${SEO} | ${STATUS} |" >> "${SUMMARY_FILE}"
    echo "  → P:${PERF} A:${A11Y} BP:${BP} SEO:${SEO} ${STATUS}"

done < "${ROUTES_FILE}"

PCT="0"
if [[ "$TOTAL" -gt 0 ]]; then
    PCT=$(echo "scale=1; ${PERFECT} * 100 / ${TOTAL}" | bc 2>/dev/null || echo "0")
fi

cat >> "${SUMMARY_FILE}" <<EOF

## 📊 BILAN GLOBAL

- **Total modules auditées** : ${TOTAL}
- **Modules à 100/100/100/100** : ${PERFECT}
- **Modules en échec (timeout/erreur)** : ${FAILED}
- **Taux de perfection** : ${PCT}%

## 🎯 PROCHAINE ÉTAPE
Voir DIAGNOSTICS.md pour l'analyse détaillée par module et le plan de correction transversal.
EOF

echo ""
echo "✅ Audit terminé : ${TOTAL} modules, ${PERFECT} perfect, ${FAILED} failed"
echo "📄 Rapport : ${SUMMARY_FILE}"
echo "📁 Dossier : ${REPORTS_DIR}"
echo "${REPORTS_DIR}" > "${AUDIT_DIR}/last_reports_dir.txt"
