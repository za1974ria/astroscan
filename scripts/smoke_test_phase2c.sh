#!/bin/bash
# AstroScan-Chohra Phase 2C — Smoke test des routes Blueprints
# Généré: 2026-05-07
set -u
BASE='http://127.0.0.1:5003'
OK=0; KO=0; FAIL_LINES=()
echo '=== SMOKE TEST PHASE 2C ==='
echo "Base URL: $BASE"
echo

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/aegis/claude-test")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] ai::api_aegis_claude_test /api/aegis/claude-test"); fi
printf '  [%s] %-15s %s\n' "$code" "ai" "/api/aegis/claude-test"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/aegis/groq-ping")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] ai::api_aegis_groq_ping /api/aegis/groq-ping"); fi
printf '  [%s] %-15s %s\n' "$code" "ai" "/api/aegis/groq-ping"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/aegis/status")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] ai::api_aegis_status /api/aegis/status"); fi
printf '  [%s] %-15s %s\n' "$code" "ai" "/api/aegis/status"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/jwst/images")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] ai::api_jwst_images /api/jwst/images"); fi
printf '  [%s] %-15s %s\n' "$code" "ai" "/api/jwst/images"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/telescope/live")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] ai::api_telescope_live /api/telescope/live"); fi
printf '  [%s] %-15s %s\n' "$code" "ai" "/api/telescope/live"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/guide-stellaire")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] ai::guide_stellaire_page /guide-stellaire"); fi
printf '  [%s] %-15s %s\n' "$code" "ai" "/guide-stellaire"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/oracle-cosmique")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] ai::oracle_cosmique_page /oracle-cosmique"); fi
printf '  [%s] %-15s %s\n' "$code" "ai" "/oracle-cosmique"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/analytics")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] analytics::analytics_dashboard /analytics"); fi
printf '  [%s] %-15s %s\n' "$code" "analytics" "/analytics"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/analytics/summary")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] analytics::api_analytics_summary /api/analytics/summary"); fi
printf '  [%s] %-15s %s\n' "$code" "analytics" "/api/analytics/summary"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/visitors/connection_time")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] analytics::api_visitors_connection_time /api/visitors/connection_time"); fi
printf '  [%s] %-15s %s\n' "$code" "analytics" "/api/visitors/connection_time"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/visitors/connection-time")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] analytics::api_visitors_connection_time_legacy /api/visitors/connection-time"); fi
printf '  [%s] %-15s %s\n' "$code" "analytics" "/api/visitors/connection-time"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/visitors/geo")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] analytics::api_visitors_geo /api/visitors/geo"); fi
printf '  [%s] %-15s %s\n' "$code" "analytics" "/api/visitors/geo"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/visitors/globe-data")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] analytics::api_visitors_globe_data /api/visitors/globe-data"); fi
printf '  [%s] %-15s %s\n' "$code" "analytics" "/api/visitors/globe-data"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/visitors/snapshot")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] analytics::api_visitors_snapshot /api/visitors/snapshot"); fi
printf '  [%s] %-15s %s\n' "$code" "analytics" "/api/visitors/snapshot"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/visitors/stats")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] analytics::api_visitors_stats /api/visitors/stats"); fi
printf '  [%s] %-15s %s\n' "$code" "analytics" "/api/visitors/stats"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/visitors/stream")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] analytics::api_visitors_stream /api/visitors/stream"); fi
printf '  [%s] %-15s %s\n' "$code" "analytics" "/api/visitors/stream"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/visits")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] analytics::api_visits_get /api/visits"); fi
printf '  [%s] %-15s %s\n' "$code" "analytics" "/api/visits"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/visits/count")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] analytics::get_visits /api/visits/count"); fi
printf '  [%s] %-15s %s\n' "$code" "analytics" "/api/visits/count"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/accuracy/history")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_accuracy_history /api/accuracy/history"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/accuracy/history"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/admin/circuit-breakers")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_admin_circuit_breakers /api/admin/circuit-breakers"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/admin/circuit-breakers"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/cache/status")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_cache_status /api/cache/status"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/cache/status"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/catalog")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_catalog /api/catalog"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/catalog"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/docs")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_docs /api/docs"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/docs"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/modules-status")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_modules_status /api/modules-status"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/modules-status"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/owner-ips")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_owner_ips_get /api/owner-ips"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/owner-ips"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/satellites")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_satellites /api/satellites"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/satellites"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/spec.json")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_spec_json /api/spec.json"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/spec.json"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/tle/active")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_tle_active /api/tle/active"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/tle/active"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/tle/full")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_tle_full /api/tle/full"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/tle/full"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/tle/status")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_tle_status /api/tle/status"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/tle/status"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/v1/asteroids")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_v1_asteroids /api/v1/asteroids"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/v1/asteroids"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/v1/catalog")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_v1_catalog /api/v1/catalog"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/v1/catalog"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/v1/iss")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_v1_iss /api/v1/iss"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/v1/iss"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/v1/planets")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_v1_planets /api/v1/planets"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/v1/planets"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/version")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::api_version /api/version"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/api/version"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/ready")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] api::ready /ready"); fi
printf '  [%s] %-15s %s\n' "$code" "api" "/ready"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/apod")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] apod::apod_fr_json /apod"); fi
printf '  [%s] %-15s %s\n' "$code" "apod" "/apod"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/apod/view")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] apod::apod_fr_view /apod/view"); fi
printf '  [%s] %-15s %s\n' "$code" "apod" "/apod/view"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/nasa-apod")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] apod::page_nasa_apod /nasa-apod"); fi
printf '  [%s] %-15s %s\n' "$code" "apod" "/nasa-apod"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/classification/stats")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] archive::api_classification_stats /api/classification/stats"); fi
printf '  [%s] %-15s %s\n' "$code" "archive" "/api/classification/stats"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/mast/targets")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] archive::api_mast_targets /api/mast/targets"); fi
printf '  [%s] %-15s %s\n' "$code" "archive" "/api/mast/targets"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/microobservatory")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] archive::api_microobservatory /api/microobservatory"); fi
printf '  [%s] %-15s %s\n' "$code" "archive" "/api/microobservatory"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/shield")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] archive::api_shield /api/shield"); fi
printf '  [%s] %-15s %s\n' "$code" "archive" "/api/shield"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/ephemerides/tlemcen")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] astro::api_ephemerides_tlemcen /api/ephemerides/tlemcen"); fi
printf '  [%s] %-15s %s\n' "$code" "astro" "/api/ephemerides/tlemcen"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/hilal")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] astro::api_hilal /api/hilal"); fi
printf '  [%s] %-15s %s\n' "$code" "astro" "/api/hilal"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/hilal/calendar")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] astro::api_hilal_calendar /api/hilal/calendar"); fi
printf '  [%s] %-15s %s\n' "$code" "astro" "/api/hilal/calendar"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/moon")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] astro::api_moon /api/moon"); fi
printf '  [%s] %-15s %s\n' "$code" "astro" "/api/moon"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/tonight")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] astro::api_tonight /api/tonight"); fi
printf '  [%s] %-15s %s\n' "$code" "astro" "/api/tonight"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/v1/tonight")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] astro::api_v1_tonight /api/v1/tonight"); fi
printf '  [%s] %-15s %s\n' "$code" "astro" "/api/v1/tonight"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/ephemerides")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] astro::page_ephemerides /ephemerides"); fi
printf '  [%s] %-15s %s\n' "$code" "astro" "/ephemerides"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/audio-proxy")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] cameras::api_audio_proxy /api/audio-proxy"); fi
printf '  [%s] %-15s %s\n' "$code" "cameras" "/api/audio-proxy"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/microobservatory/images")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] cameras::api_microobservatory_images /api/microobservatory/images"); fi
printf '  [%s] %-15s %s\n' "$code" "cameras" "/api/microobservatory/images"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/observatory/status")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] cameras::api_observatory_status /api/observatory/status"); fi
printf '  [%s] %-15s %s\n' "$code" "cameras" "/api/observatory/status"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/sky-camera/simulate")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] cameras::api_sky_camera_simulate /api/sky-camera/simulate"); fi
printf '  [%s] %-15s %s\n' "$code" "cameras" "/api/sky-camera/simulate"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/observatory/status")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] cameras::observatory_status_page /observatory/status"); fi
printf '  [%s] %-15s %s\n' "$code" "cameras" "/observatory/status"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/sky-camera")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] cameras::sky_camera /sky-camera"); fi
printf '  [%s] %-15s %s\n' "$code" "cameras" "/sky-camera"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/skyview/list")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] cameras::skyview_list /api/skyview/list"); fi
printf '  [%s] %-15s %s\n' "$code" "cameras" "/api/skyview/list"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/skyview/targets")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] cameras::skyview_targets /api/skyview/targets"); fi
printf '  [%s] %-15s %s\n' "$code" "cameras" "/api/skyview/targets"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/visiteurs-live")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] cameras::visiteurs_live_page /visiteurs-live"); fi
printf '  [%s] %-15s %s\n' "$code" "cameras" "/visiteurs-live"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/apod-history.json")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] export::apod_history_json /apod-history.json"); fi
printf '  [%s] %-15s %s\n' "$code" "export" "/apod-history.json"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/ephemerides.json")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] export::ephemerides_json /ephemerides.json"); fi
printf '  [%s] %-15s %s\n' "$code" "export" "/ephemerides.json"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/observations.json")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] export::observations_json /observations.json"); fi
printf '  [%s] %-15s %s\n' "$code" "export" "/observations.json"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/visitors.csv")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] export::visitors_csv /visitors.csv"); fi
printf '  [%s] %-15s %s\n' "$code" "export" "/visitors.csv"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/visitors.json")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] export::visitors_json /visitors.json"); fi
printf '  [%s] %-15s %s\n' "$code" "export" "/visitors.json"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/alerts/all")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_alerts_all /api/alerts/all"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/alerts/all"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/apod")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_apod_alias /api/apod"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/apod"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/alerts/asteroids")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_asteroids /api/alerts/asteroids"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/alerts/asteroids"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/bepi/telemetry")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_bepi /api/bepi/telemetry"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/bepi/telemetry"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/feeds/all")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_feeds_all /api/feeds/all"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/feeds/all"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/feeds/apod_hd")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_feeds_apod_hd /api/feeds/apod_hd"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/feeds/apod_hd"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/feeds/mars")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_feeds_mars /api/feeds/mars"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/feeds/mars"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/feeds/neo")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_feeds_neo /api/feeds/neo"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/feeds/neo"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/feeds/solar")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_feeds_solar /api/feeds/solar"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/feeds/solar"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/feeds/solar_alerts")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_feeds_solar_alerts /api/feeds/solar_alerts"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/feeds/solar_alerts"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/feeds/voyager")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_feeds_voyager /api/feeds/voyager"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/feeds/voyager"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/flights")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_flights /api/flights"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/flights"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/live/all")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_live_all /api/live/all"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/live/all"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/live/iss-passes")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_live_iss_passes /api/live/iss-passes"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/live/iss-passes"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/live/mars-weather")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_live_mars_weather /api/live/mars-weather"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/live/mars-weather"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/mars/weather")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_mars_weather /api/mars/weather"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/mars/weather"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/missions/overview")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_missions_overview /api/missions/overview"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/missions/overview"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/nasa/apod")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_nasa_apod /api/nasa/apod"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/nasa/apod"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/nasa/neo")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_nasa_neo /api/nasa/neo"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/nasa/neo"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/nasa/solar")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_nasa_solar /api/nasa/solar"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/nasa/solar"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/neo")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_neo /api/neo"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/neo"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/news")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_news /api/news"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/news"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/orbits/live")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_orbits_live /api/orbits/live"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/orbits/live"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/alerts/solar")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_solar /api/alerts/solar"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/alerts/solar"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/sondes")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_sondes /api/sondes"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/sondes"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/sondes/live")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_sondes_live /api/sondes/live"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/sondes/live"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/live/news")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_space_news /api/live/news"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/live/news"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/space-weather/alerts")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_space_weather_alerts /api/space-weather/alerts"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/space-weather/alerts"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/live/spacex")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_spacex /api/live/spacex"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/live/spacex"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/survol")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_survol /api/survol"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/survol"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/voyager-live")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] feeds::api_voyager_live /api/voyager-live"); fi
printf '  [%s] %-15s %s\n' "$code" "feeds" "/api/voyager-live"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/flight-radar/aircraft")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] flight_radar::api_aircraft_list /api/flight-radar/aircraft"); fi
printf '  [%s] %-15s %s\n' "$code" "flight_radar" "/api/flight-radar/aircraft"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/flight-radar/airports")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] flight_radar::api_airports /api/flight-radar/airports"); fi
printf '  [%s] %-15s %s\n' "$code" "flight_radar" "/api/flight-radar/airports"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/flight-radar/health")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] flight_radar::api_health /api/flight-radar/health"); fi
printf '  [%s] %-15s %s\n' "$code" "flight_radar" "/api/flight-radar/health"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/flight-radar")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] flight_radar::flight_radar_page /flight-radar"); fi
printf '  [%s] %-15s %s\n' "$code" "flight_radar" "/flight-radar"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/ground-assets/events")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] ground_assets::api_events /api/ground-assets/events"); fi
printf '  [%s] %-15s %s\n' "$code" "ground_assets" "/api/ground-assets/events"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/ground-assets/health")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] ground_assets::api_health /api/ground-assets/health"); fi
printf '  [%s] %-15s %s\n' "$code" "ground_assets" "/api/ground-assets/health"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/ground-assets/network")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] ground_assets::api_network /api/ground-assets/network"); fi
printf '  [%s] %-15s %s\n' "$code" "ground_assets" "/api/ground-assets/network"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/ground-assets")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] ground_assets::ground_assets_page /ground-assets"); fi
printf '  [%s] %-15s %s\n' "$code" "ground_assets" "/ground-assets"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/health")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] health::api_health /api/health"); fi
printf '  [%s] %-15s %s\n' "$code" "health" "/api/health"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/status")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] health::api_status /status"); fi
printf '  [%s] %-15s %s\n' "$code" "health" "/status"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/system-alerts")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] health::api_system_alerts /api/system-alerts"); fi
printf '  [%s] %-15s %s\n' "$code" "health" "/api/system-alerts"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/system-notifications")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] health::api_system_notifications /api/system-notifications"); fi
printf '  [%s] %-15s %s\n' "$code" "health" "/api/system-notifications"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/system-status")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] health::api_system_status /api/system-status"); fi
printf '  [%s] %-15s %s\n' "$code" "health" "/api/system-status"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/system-status/cache")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] health::api_system_status_cache /api/system-status/cache"); fi
printf '  [%s] %-15s %s\n' "$code" "health" "/api/system-status/cache"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/system/status")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] health::api_system_status_orbital /api/system/status"); fi
printf '  [%s] %-15s %s\n' "$code" "health" "/api/system/status"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/health")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] health::health_check /health"); fi
printf '  [%s] %-15s %s\n' "$code" "health" "/health"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/selftest")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] health::selftest /selftest"); fi
printf '  [%s] %-15s %s\n' "$code" "health" "/selftest"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/system/server-info")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] health::server_info /api/system/server-info"); fi
printf '  [%s] %-15s %s\n' "$code" "health" "/api/system/server-info"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/stream/status")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] health::stream_status_sse /stream/status"); fi
printf '  [%s] %-15s %s\n' "$code" "health" "/stream/status"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/system/diagnostics")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] health::system_diagnostics /api/system/diagnostics"); fi
printf '  [%s] %-15s %s\n' "$code" "health" "/api/system/diagnostics"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/cities/search")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] hilal::cities_search /cities/search"); fi
printf '  [%s] %-15s %s\n' "$code" "hilal" "/cities/search"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/events")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] hilal::events /events"); fi
printf '  [%s] %-15s %s\n' "$code" "hilal" "/events"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/prayers")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] hilal::prayers /prayers"); fi
printf '  [%s] %-15s %s\n' "$code" "hilal" "/prayers"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/ramadan")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] hilal::ramadan /ramadan"); fi
printf '  [%s] %-15s %s\n' "$code" "hilal" "/ramadan"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/today")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] hilal::today /today"); fi
printf '  [%s] %-15s %s\n' "$code" "hilal" "/today"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/iss")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::api_iss /api/iss"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/api/iss"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/iss/crew")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::api_iss_crew /api/iss/crew"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/api/iss/crew"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/iss/ground-track")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::api_iss_ground_track /api/iss/ground-track"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/api/iss/ground-track"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/iss/orbit")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::api_iss_orbit /api/iss/orbit"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/api/iss/orbit"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/iss-passes")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::api_iss_passes_n2yo /api/iss-passes"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/api/iss-passes"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/iss/passes")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::api_iss_passes_tlemcen /api/iss/passes"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/api/iss/passes"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/passages-iss")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::api_passages_iss /api/passages-iss"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/api/passages-iss"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/iss/stream")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::iss_stream /api/iss/stream"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/api/iss/stream"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/iss-tracker")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::iss_tracker_page /iss-tracker"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/iss-tracker"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/orbital")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::orbital_dashboard /orbital"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/orbital"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/orbital-map")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::orbital_map_page /orbital-map"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/orbital-map"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/tle/catalog")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::tle_catalog /api/tle/catalog"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/api/tle/catalog"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/tle/sample")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] iss::tle_sample /api/tle/sample"); fi
printf '  [%s] %-15s %s\n' "$code" "iss" "/api/tle/sample"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/analysis/discoveries")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] lab::api_analysis_discoveries /api/analysis/discoveries"); fi
printf '  [%s] %-15s %s\n' "$code" "lab" "/api/analysis/discoveries"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/lab/images")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] lab::api_lab_images /api/lab/images"); fi
printf '  [%s] %-15s %s\n' "$code" "lab" "/api/lab/images"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/lab/report")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] lab::api_lab_report /api/lab/report"); fi
printf '  [%s] %-15s %s\n' "$code" "lab" "/api/lab/report"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/lab")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] lab::digital_lab /lab"); fi
printf '  [%s] %-15s %s\n' "$code" "lab" "/lab"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/lab/skyview/sync")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] lab::force_skyview_sync /api/lab/skyview/sync"); fi
printf '  [%s] %-15s %s\n' "$code" "lab" "/api/lab/skyview/sync"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/lab/dashboard")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] lab::lab_dashboard /lab/dashboard"); fi
printf '  [%s] %-15s %s\n' "$code" "lab" "/lab/dashboard"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/lab/images")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] lab::lab_images /lab/images"); fi
printf '  [%s] %-15s %s\n' "$code" "lab" "/lab/images"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/a-propos")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] main::a_propos /a-propos"); fi
printf '  [%s] %-15s %s\n' "$code" "main" "/a-propos"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/about")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] main::a_propos /about"); fi
printf '  [%s] %-15s %s\n' "$code" "main" "/about"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/data")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] main::data_portal /data"); fi
printf '  [%s] %-15s %s\n' "$code" "main" "/data"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/favicon.ico")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] main::favicon /favicon.ico"); fi
printf '  [%s] %-15s %s\n' "$code" "main" "/favicon.ico"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/manifest.json")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] main::manifest_json /manifest.json"); fi
printf '  [%s] %-15s %s\n' "$code" "main" "/manifest.json"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/en")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] main::portail_en /en"); fi
printf '  [%s] %-15s %s\n' "$code" "main" "/en"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/en/")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] main::portail_en /en/"); fi
printf '  [%s] %-15s %s\n' "$code" "main" "/en/"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/en/portail")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] main::portail_en /en/portail"); fi
printf '  [%s] %-15s %s\n' "$code" "main" "/en/portail"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/sw.js")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] main::sw_js /sw.js"); fi
printf '  [%s] %-15s %s\n' "$code" "main" "/sw.js"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/apod")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] nasa_proxy::apod /apod"); fi
printf '  [%s] %-15s %s\n' "$code" "nasa_proxy" "/apod"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/insight-weather")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] nasa_proxy::insight_weather /insight-weather"); fi
printf '  [%s] %-15s %s\n' "$code" "nasa_proxy" "/insight-weather"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/aladin")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::aladin_page /aladin"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/aladin"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/carte-du-ciel")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::aladin_page /carte-du-ciel"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/carte-du-ciel"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/demo")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::astroscan_demo_page /demo"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/demo"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/ce_soir")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::ce_soir_page /ce_soir"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/ce_soir"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/dashboard")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::dashboard /dashboard"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/dashboard"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/europe-live")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::europe_live /europe-live"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/europe-live"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/galerie")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::galerie /galerie"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/galerie"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/globe")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::globe /globe"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/globe"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::index /"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/landing")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::landing /landing"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/landing"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/observatoire")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::observatoire /observatoire"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/observatoire"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/overlord_live")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::overlord_live /overlord_live"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/overlord_live"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/portail")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::portail /portail"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/portail"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/research")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::research /research"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/research"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/scientific")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::scientific /scientific"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/scientific"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/sondes")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::sondes /sondes"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/sondes"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/space")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::space /space"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/space"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/space-intelligence")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::space_intelligence /space-intelligence"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/space-intelligence"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/space-intelligence-page")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::space_intelligence_page /space-intelligence-page"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/space-intelligence-page"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/technical")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::technical_page /technical"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/technical"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/telemetrie-sondes")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::telemetrie_sondes /telemetrie-sondes"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/telemetrie-sondes"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/vision")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::vision /vision"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/vision"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/vision-2026")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] pages::vision_2026 /vision-2026"); fi
printf '  [%s] %-15s %s\n' "$code" "pages" "/vision-2026"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/research/events")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] research::api_research_events /api/research/events"); fi
printf '  [%s] %-15s %s\n' "$code" "research" "/api/research/events"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/research/logs")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] research::api_research_logs /api/research/logs"); fi
printf '  [%s] %-15s %s\n' "$code" "research" "/api/research/logs"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/research/summary")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] research::api_research_summary /api/research/summary"); fi
printf '  [%s] %-15s %s\n' "$code" "research" "/api/research/summary"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/research-center")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] research::research_center_page /research-center"); fi
printf '  [%s] %-15s %s\n' "$code" "research" "/research-center"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/satellite/passes")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] satellites::api_satellite_passes /api/satellite/passes"); fi
printf '  [%s] %-15s %s\n' "$code" "satellites" "/api/satellite/passes"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/satellites/tle")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] satellites::api_satellites_tle /api/satellites/tle"); fi
printf '  [%s] %-15s %s\n' "$code" "satellites" "/api/satellites/tle"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/satellites/tle/debug")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] satellites::debug_tle /api/satellites/tle/debug"); fi
printf '  [%s] %-15s %s\n' "$code" "satellites" "/api/satellites/tle/debug"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/scan-signal/health")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] scan_signal::api_health /api/scan-signal/health"); fi
printf '  [%s] %-15s %s\n' "$code" "scan_signal" "/api/scan-signal/health"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/scan-signal/ports")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] scan_signal::api_ports /api/scan-signal/ports"); fi
printf '  [%s] %-15s %s\n' "$code" "scan_signal" "/api/scan-signal/ports"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/scan-signal/stats")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] scan_signal::api_stats /api/scan-signal/stats"); fi
printf '  [%s] %-15s %s\n' "$code" "scan_signal" "/api/scan-signal/stats"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/scan-signal/vessel/recent")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] scan_signal::api_vessel_recent /api/scan-signal/vessel/recent"); fi
printf '  [%s] %-15s %s\n' "$code" "scan_signal" "/api/scan-signal/vessel/recent"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/scan-signal/vessel/search")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] scan_signal::api_vessel_search /api/scan-signal/vessel/search"); fi
printf '  [%s] %-15s %s\n' "$code" "scan_signal" "/api/scan-signal/vessel/search"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/scan-signal")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] scan_signal::scan_signal_page /scan-signal"); fi
printf '  [%s] %-15s %s\n' "$code" "scan_signal" "/scan-signal"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/sdr/captures")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] sdr::api_sdr_captures /api/sdr/captures"); fi
printf '  [%s] %-15s %s\n' "$code" "sdr" "/api/sdr/captures"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/sdr/passes")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] sdr::api_sdr_passes /api/sdr/passes"); fi
printf '  [%s] %-15s %s\n' "$code" "sdr" "/api/sdr/passes"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/sdr/stations")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] sdr::api_sdr_stations /api/sdr/stations"); fi
printf '  [%s] %-15s %s\n' "$code" "sdr" "/api/sdr/stations"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/sdr/status")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] sdr::api_sdr_status /api/sdr/status"); fi
printf '  [%s] %-15s %s\n' "$code" "sdr" "/api/sdr/status"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/orbital-radio")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] sdr::orbital_radio /orbital-radio"); fi
printf '  [%s] %-15s %s\n' "$code" "sdr" "/orbital-radio"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/robots.txt")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] seo::robots_txt /robots.txt"); fi
printf '  [%s] %-15s %s\n' "$code" "seo" "/robots.txt"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/robots.txt")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] seo::robots_txt /robots.txt"); fi
printf '  [%s] %-15s %s\n' "$code" "seo" "/robots.txt"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/sitemap.xml")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] seo::sitemap_xml /sitemap.xml"); fi
printf '  [%s] %-15s %s\n' "$code" "seo" "/sitemap.xml"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/sitemap.xml")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] seo::sitemap_xml /sitemap.xml"); fi
printf '  [%s] %-15s %s\n' "$code" "seo" "/sitemap.xml"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/dsn")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] system::api_dsn /api/dsn"); fi
printf '  [%s] %-15s %s\n' "$code" "system" "/api/dsn"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/latest")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] system::api_latest /api/latest"); fi
printf '  [%s] %-15s %s\n' "$code" "system" "/api/latest"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/sync/state")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] system::api_sync_state_get /api/sync/state"); fi
printf '  [%s] %-15s %s\n' "$code" "system" "/api/sync/state"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/telescope/sources")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] system::api_telescope_sources /api/telescope/sources"); fi
printf '  [%s] %-15s %s\n' "$code" "system" "/api/telescope/sources"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/hubble/images")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::api_hubble_images /api/hubble/images"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/api/hubble/images"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/image")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::api_image /api/image"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/api/image"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/mission-control")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::api_mission_control /api/mission-control"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/api/mission-control"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/stellarium")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::api_stellarium /api/stellarium"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/api/stellarium"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/telescope/catalogue")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::api_telescope_catalogue /api/telescope/catalogue"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/api/telescope/catalogue"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/telescope-hub")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::api_telescope_hub /api/telescope-hub"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/api/telescope-hub"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/telescope/image")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::api_telescope_image /api/telescope/image"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/api/telescope/image"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/telescope/nightly")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::api_telescope_nightly /api/telescope/nightly"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/api/telescope/nightly"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/telescope/proxy-image")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::api_telescope_proxy_image /api/telescope/proxy-image"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/api/telescope/proxy-image"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/title")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::api_title /api/title"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/api/title"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/mission-control")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::mission_control /mission-control"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/mission-control"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/telescope")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::telescope /telescope"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/telescope"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/telescope/status")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::telescope_status /api/telescope/status"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/api/telescope/status"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/telescope/stream")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::telescope_stream /api/telescope/stream"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/api/telescope/stream"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/telescopes")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] telescope::telescopes_page /telescopes"); fi
printf '  [%s] %-15s %s\n' "$code" "telescope" "/telescopes"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/build")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] version::build /api/build"); fi
printf '  [%s] %-15s %s\n' "$code" "version" "/api/build"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/aurore")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::api_aurore /api/aurore"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/api/aurore"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/aurores")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::api_aurores_alias /api/aurores"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/api/aurores"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/meteo-spatiale")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::api_meteo_spatiale /api/meteo-spatiale"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/api/meteo-spatiale"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/space-weather")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::api_space_weather /api/space-weather"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/api/space-weather"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/v1/solar-weather")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::api_v1_solar /api/v1/solar-weather"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/api/v1/solar-weather"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/weather")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::api_weather_alias /api/weather"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/api/weather"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/weather/bulletins")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::api_weather_bulletins /api/weather/bulletins"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/api/weather/bulletins"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/weather/bulletins/latest")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::api_weather_bulletins_latest /api/weather/bulletins/latest"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/api/weather/bulletins/latest"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/weather/history")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::api_weather_history /api/weather/history"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/api/weather/history"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/weather/local")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::api_weather_local /api/weather/local"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/api/weather/local"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/aurores")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::aurores_page /aurores"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/aurores"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/control")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::control /control"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/control"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/meteo")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::control /meteo"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/meteo"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/meteo-reel")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::meteo_page /meteo-reel"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/meteo-reel"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/meteo/reel")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::meteo_reel /api/meteo/reel"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/api/meteo/reel"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/meteo-spatiale")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::meteo_spatiale_page /meteo-spatiale"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/meteo-spatiale"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/space-weather")
if [[ "$code" =~ ^(200|301|302|304|401|403)$ ]]; then OK=$((OK+1)); else KO=$((KO+1)); FAIL_LINES+=("  [$code] weather::space_weather_page /space-weather"); fi
printf '  [%s] %-15s %s\n' "$code" "weather" "/space-weather"

echo
echo "=== RÉSUMÉ ==="
echo "OK   (2xx/3xx/401/403) : $OK"
echo "FAIL (4xx hors 401/403, 5xx) : $KO"
if [[ $KO -gt 0 ]]; then
  echo
  echo '--- FAIL DETAILS ---'
  for line in "${FAIL_LINES[@]}"; do echo "$line"; done
fi
exit $KO