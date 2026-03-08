#!/usr/bin/env bash
# deploy_dashboards.sh — Upload SASP Splunk dashboards via REST API
# Required env vars: SPLUNK_HOST, SPLUNK_USER, SPLUNK_PASS, SPLUNK_APP

set -euo pipefail

# ---------------------------------------------------------------------------
# Validate required environment variables
# ---------------------------------------------------------------------------
for var in SPLUNK_HOST SPLUNK_USER SPLUNK_PASS SPLUNK_APP; do
  if [ -z "${!var:-}" ]; then
    echo "ERROR: $var is not set" >&2
    exit 1
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="https://${SPLUNK_HOST}:8089"
AUTH="${SPLUNK_USER}:${SPLUNK_PASS}"
VIEWS_ENDPOINT="/servicesNS/nobody/${SPLUNK_APP}/data/ui/views"

DASHBOARDS=(
  "detections"
  "investigations"
  "ai_health"
  "gpu_health"
  "roce_network"
  "ise_activity"
)

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------
dashboard_exists() {
  local name="$1"
  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" -k -u "${AUTH}" \
    "${BASE_URL}${VIEWS_ENDPOINT}/${name}")
  [ "$http_code" = "200" ]
}

upload_dashboard() {
  local name="$1"
  local xml_file="${SCRIPT_DIR}/${name}.xml"

  if [ ! -f "$xml_file" ]; then
    echo "ERROR: ${xml_file} not found" >&2
    return 1
  fi

  local xml_data
  xml_data=$(<"$xml_file")

  if dashboard_exists "$name"; then
    echo "Updating existing dashboard: ${name}"
    curl -s -k -u "${AUTH}" \
      -X POST \
      "${BASE_URL}${VIEWS_ENDPOINT}/${name}" \
      -d "eai:data=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.stdin.read()))" <<< "$xml_data")" \
      -o /dev/null -w "  HTTP %{http_code}\n"
  else
    echo "Creating new dashboard: ${name}"
    curl -s -k -u "${AUTH}" \
      -X POST \
      "${BASE_URL}${VIEWS_ENDPOINT}" \
      -d "name=${name}" \
      -d "eai:data=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.stdin.read()))" <<< "$xml_data")" \
      -o /dev/null -w "  HTTP %{http_code}\n"
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo "Deploying SASP dashboards to ${SPLUNK_HOST} (app: ${SPLUNK_APP})"
echo "---"

failures=0
for dashboard in "${DASHBOARDS[@]}"; do
  if ! upload_dashboard "$dashboard"; then
    failures=$((failures + 1))
  fi
done

echo "---"
if [ "$failures" -gt 0 ]; then
  echo "Completed with ${failures} failure(s)." >&2
  exit 1
else
  echo "All dashboards deployed successfully."
fi
