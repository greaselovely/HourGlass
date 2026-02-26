#!/usr/bin/env bash

# ============================================================================
# HourGlass Video Download Script
# ============================================================================

set -o errexit
set -o pipefail
set -o nounset

# Ensure PATH includes common locations for cron compatibility
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

source "${HOME}/.linode_config"

# Only clear if running in a terminal
[[ -t 1 ]] && clear

# Defaults and constants
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="${HOME}/v.log"
LOG_MAX_SIZE=1048576  # 1MB in bytes

# Rotate log if over max size
rotate_log() {
  if [[ -f "$LOG_FILE" ]]; then
    local size
    size=$(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
    if [[ $size -gt $LOG_MAX_SIZE ]]; then
      mv "$LOG_FILE" "${LOG_FILE}.1"
    fi
  fi
}
rotate_log
KEY_PATH="${HOME}/.ssh/github_actions_deploy-vla"
SSH_OPTS="-i ${KEY_PATH} -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new"
SAVE_BUFFER_MIN=18  # 13 min avg save time + 5 min buffer
PY_ENV="${HOME}/projects/python/.venv"
PY_HOME="${HOME}/projects/python/python"
FW_SCRIPT="${PY_HOME}/linode_firewall.py"

# Args
PROJECT=""           # required: project name (e.g. VLA)
DATE_STR=""          # if set via -d, overrides offsets
OFFSET_DAYS=0        # 0 = today, 1 = yesterday
USE_YESTERDAY=0
FORCE=0              # if set via -f, skip local file check + smart wait + polling

usage() {
  cat <<EOF
Usage: $(basename "$0") -p PROJECT [-f] [-d MMDDYYYY] [-o N] [-y] [-h]

  -p PROJECT    project name (required, e.g. VLA) — loads configs/PROJECT.json
  -f            force: skip local file check, smart wait, and ntfy polling
  -d MMDDYYYY   specific date (overrides -o and -y)
  -o N          N days ago (1 = yesterday)
  -y            yesterday (same as -o 1)
  -h            help

Examples:
  $(basename "$0") -p VLA              # cron: smart wait + poll + download
  $(basename "$0") -p VLA -f           # manual re-run: skip checks, just download
  $(basename "$0") -p VLA -f -y        # force download yesterday's video
  $(basename "$0") -p VLA -d 09222025  # specific date
EOF
}

# Parse args
while getopts ":p:fd:o:yh" opt; do
  case $opt in
    p)
      PROJECT="$OPTARG"
      ;;
    f)
      FORCE=1
      ;;
    d)
      if [[ $OPTARG =~ ^[0-1][0-9][0-3][0-9][0-9]{4}$ ]]; then
        DATE_STR="$OPTARG"
      else
        echo "Error: Invalid -d format. Use MMDDYYYY."
        exit 1
      fi
      ;;
    o)
      if [[ $OPTARG =~ ^[0-9]+$ ]]; then
        OFFSET_DAYS="$OPTARG"
      else
        echo "Error: -o requires a non-negative integer."
        exit 1
      fi
      ;;
    y)
      USE_YESTERDAY=1
      ;;
    h)
      usage
      exit 0
      ;;
    \?)
      echo "Invalid option: -$OPTARG" >&2
      usage
      exit 1
      ;;
    :)
      echo "Option -$OPTARG requires an argument." >&2
      usage
      exit 1
      ;;
  esac
done

# Validate required project arg
if [[ -z "$PROJECT" ]]; then
  echo "Error: -p PROJECT is required."
  usage
  exit 1
fi

# Load ntfy config from project JSON
CONFIG_JSON="${SCRIPT_DIR}/configs/${PROJECT}.json"
if [[ ! -f "$CONFIG_JSON" ]]; then
  echo "Error: Config not found: ${CONFIG_JSON}"
  exit 1
fi
NTFY_BASE=$(jq -r '.ntfy // empty' "$CONFIG_JSON")
NTFY_TOPIC_NAME=$(jq -r '.alerts.ntfy // empty' "$CONFIG_JSON")
if [[ -z "$NTFY_BASE" || -z "$NTFY_TOPIC_NAME" ]]; then
  echo "Error: ntfy not configured in ${CONFIG_JSON}. Need 'ntfy' (base URL) and 'alerts.ntfy' (topic name)."
  exit 1
fi
NTFY_TOPIC="${NTFY_BASE%/}/${NTFY_TOPIC_NAME}"
NTFY_JSON_URL="https://ntfy.sh/${NTFY_TOPIC_NAME}/json"

# Derive paths from project name (convention: HourGlass/{PROJECT}/video/)
REMOTE_BASE="HourGlass/${PROJECT}/video"

# Resolve date with macOS and Linux support
resolve_date() {
  # If user gave -d, use it as is
  if [[ -n "${DATE_STR}" ]]; then
    echo "${DATE_STR}"
    return 0
  fi

  # Yesterday flag
  if [[ "${USE_YESTERDAY}" -eq 1 ]]; then
    OFFSET_DAYS=1
  fi

  # Compute from offset
  local os="$(uname -s)"
  if [[ "${os}" == "Darwin" ]]; then
    # macOS BSD date
    if [[ "${OFFSET_DAYS}" -gt 0 ]]; then
      date -v-"${OFFSET_DAYS}"d +%m%d%Y
    else
      date +%m%d%Y
    fi
  else
    # Linux GNU date
    if [[ "${OFFSET_DAYS}" -gt 0 ]]; then
      date -d "${OFFSET_DAYS} days ago" +%m%d%Y
    else
      date +%m%d%Y
    fi
  fi
}

DATE_STR="$(resolve_date)"

# Initial filename — may be updated after ntfy polling or SSH check
FILENAME="${PROJECT}.${DATE_STR}.mp4"
REMOTE_FILE="${REMOTE_BASE}/${FILENAME}"

log() {
  local msg="$1"
  echo "$(date '+%Y-%m-%d %H:%M:%S') | $msg"
}

notify() {
  local msg="$1"
  local priority="${2:-default}"  # default, low, high, urgent
  log "$msg"
  curl -s -H "Priority: ${priority}" -d "[v.sh] $msg" "${NTFY_TOPIC}" >/dev/null || true
}

# Fetch today's End time from ntfy.sh topic history
# Returns End time in HH:MM format, or empty string if not found
get_end_time_from_ntfy() {
  # Fetch last 24h of messages, look for schedule notification with End time
  # Message format: "Sleep:\t02:11\nStart:\t07:12\nEnd:\t18:05"
  local end_time
  end_time=$(curl -s "${NTFY_JSON_URL}?poll=1&since=24h" 2>/dev/null | \
    grep -o '"message":"[^"]*"' | \
    grep 'End:\\t' | \
    tail -1 | \
    sed 's/.*End:\\t\([0-9]\{1,2\}:[0-9]\{2\}\).*/\1/')

  echo "$end_time"
}

# Calculate seconds to sleep until video should be ready
# Returns 0 if we should proceed immediately
calculate_sleep_seconds() {
  local end_time="$1"

  if [[ -z "$end_time" ]]; then
    echo "0"
    return
  fi

  local end_hour end_min
  end_hour=$(echo "$end_time" | cut -d: -f1)
  end_min=$(echo "$end_time" | cut -d: -f2)

  # Target time = End time + buffer
  local target_min=$((end_hour * 60 + end_min + SAVE_BUFFER_MIN))
  local target_hour=$((target_min / 60))
  target_min=$((target_min % 60))

  # Current time in minutes since midnight
  local now_hour now_min now_total
  now_hour=$(date +%-H)
  now_min=$(date +%-M)
  now_total=$((now_hour * 60 + now_min))

  local target_total=$((target_hour * 60 + target_min))
  local diff=$((target_total - now_total))

  if [[ $diff -le 0 ]]; then
    echo "0"
  else
    echo $((diff * 60))
  fi
}

# Poll ntfy for "saved successfully" message, extract actual filename
# Returns 0 on success (sets FILENAME and REMOTE_FILE), 1 on timeout
wait_for_save_confirmation() {
  local max_attempts=30
  local interval=60
  local attempt=0

  log "Polling ntfy for save confirmation (${max_attempts}x${interval}s)..."

  while [[ $attempt -lt $max_attempts ]]; do
    attempt=$((attempt + 1))
    local match
    match=$(curl -s "${NTFY_JSON_URL}?poll=1&since=24h" 2>/dev/null | \
      grep -o '"message":"[^"]*"' | \
      grep "${PROJECT}\.${DATE_STR}.*saved successfully" | \
      tail -1) || true

    if [[ -n "$match" ]]; then
      # Extract filename (e.g. "VLA.02252026.mp4" or "VLA.02252026.NO_AUDIO.mp4")
      local extracted
      extracted=$(echo "$match" | grep -o "${PROJECT}\.[0-9]\{8\}\(\.[A-Z_]*\)*\.mp4") || true
      if [[ -n "$extracted" ]]; then
        FILENAME="$extracted"
        REMOTE_FILE="${REMOTE_BASE}/${FILENAME}"
        log "Save confirmed: ${FILENAME} (attempt ${attempt}/${max_attempts})"
        return 0
      fi
    fi

    if [[ $attempt -lt $max_attempts ]]; then
      log "No confirmation yet (attempt ${attempt}/${max_attempts}). Waiting ${interval}s..."
      sleep "$interval"
    fi
  done

  notify "Timed out waiting for save confirmation after $((max_attempts * interval / 60))min" "high"
  return 1
}

# Check remote server for actual filename (handles NO_AUDIO variant)
# Sets FILENAME and REMOTE_FILE on success, returns 1 if neither found
resolve_remote_filename() {
  local base="${PROJECT}.${DATE_STR}"
  local candidates=("${base}.mp4" "${base}.NO_AUDIO.mp4")

  for candidate in "${candidates[@]}"; do
    if ssh $SSH_OPTS "${LINODE_IP}" "test -s '${REMOTE_BASE}/${candidate}'" 2>/dev/null; then
      FILENAME="$candidate"
      REMOTE_FILE="${REMOTE_BASE}/${FILENAME}"
      log "Found remote file: ${REMOTE_FILE}"
      return 0
    fi
  done

  return 1
}

# Validate downloaded file with ffprobe
# Returns 0 if valid, 1 if corrupt (deletes bad file and notifies)
validate_video() {
  local file="$1"

  if ! command -v ffprobe &>/dev/null; then
    log "WARNING: ffprobe not found, skipping validation"
    return 0
  fi

  local duration
  duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$file" 2>/dev/null) || true

  if [[ -z "$duration" || "$duration" == "0" || "$duration" == "0.000000" || "$duration" == "N/A" ]]; then
    log "FAILED: ffprobe validation — file appears corrupt (duration: ${duration:-empty})"
    rm -f "$file"
    notify "Downloaded file is corrupt (ffprobe failed). Deleted ${file}." "high"
    return 1
  fi

  # Format duration as minutes:seconds for readability
  local dur_int=${duration%.*}
  local dur_min=$((dur_int / 60))
  local dur_sec=$((dur_int % 60))
  log "ffprobe OK: duration ${dur_min}m${dur_sec}s"
  echo "${dur_min}m${dur_sec}s"
  return 0
}

# If local file exists, stop (unless -f force flag is set)
if [[ "$FORCE" -eq 0 ]]; then
  for _f in "${PROJECT}.${DATE_STR}.mp4" "${PROJECT}.${DATE_STR}.NO_AUDIO.mp4"; do
    if [[ -e "$_f" ]]; then
      notify "File ${_f} already exists. Exiting. Use -f to override." "low"
      exit 0
    fi
  done
fi

echo ""
log "=== Invoked as: $0 -p ${PROJECT} | PID: $$ ==="
log "Server: ${LINODE_IP}"
log "Project: ${PROJECT}"
log "Target date: ${DATE_STR}"

# ============================================================================
# Main flow: cron vs manual (-f)
# ============================================================================

if [[ "$FORCE" -eq 0 ]]; then
  # --- Cron path: smart wait → poll ntfy → resolve filename → download → validate ---

  END_TIME=$(get_end_time_from_ntfy)
  if [[ -n "$END_TIME" ]]; then
    log "Capture end time from ntfy: ${END_TIME}"
    SLEEP_SECS=$(calculate_sleep_seconds "$END_TIME")
    if [[ $SLEEP_SECS -gt 0 ]]; then
      WAKE_TIME=$(date -v+"${SLEEP_SECS}"S +%H:%M 2>/dev/null || date -d "+${SLEEP_SECS} seconds" +%H:%M)
      log "Video not ready yet. Sleeping ${SLEEP_SECS}s (until ~${WAKE_TIME})..."
      notify "Waiting until ~${WAKE_TIME} for video to be ready" "low"
      sleep "$SLEEP_SECS"
      log "Waking up, polling for save confirmation."
    else
      log "Target time already passed, polling for save confirmation."
    fi
  else
    log "Could not fetch End time from ntfy, polling for save confirmation."
  fi

  # Poll ntfy for "saved successfully" — also resolves the actual filename
  if ! wait_for_save_confirmation; then
    exit 1
  fi

else
  # --- Manual path (-f): skip wait + polling, resolve filename via SSH ---
  log "Force mode: skipping smart wait and ntfy polling."
fi

# 1) Check SSH connectivity before touching firewall
if ! ssh $SSH_OPTS "${LINODE_IP}" "true" 2>"${SCRIPT_DIR}/ssh_err.txt"; then
  rm -f "${SCRIPT_DIR}/ssh_err.txt"
  notify "Cannot reach server. Will try firewall update then retry."
  if pushd "${PY_HOME%/python}" >/dev/null; then
    source "${PY_ENV}/bin/activate"
    "${PY_ENV}/bin/python" "${FW_SCRIPT}" || {
      notify "Firewall update script failed. Exiting." "high"
      exit 1
    }
    deactivate
    popd >/dev/null
  else
    notify "Internal path error launching firewall update." "high"
    exit 1
  fi

  log "Sleeping 5s before retry..."
  sleep 5
  if ! ssh $SSH_OPTS "${LINODE_IP}" "true" 2>/dev/null; then
    notify "Still cannot reach server after firewall update. Exiting." "high"
    exit 1
  fi
fi

# 2) Resolve filename via SSH if not already resolved by ntfy polling (manual -f path)
if [[ "$FORCE" -eq 1 ]]; then
  if ! resolve_remote_filename; then
    notify "Remote file not found for ${PROJECT}.${DATE_STR} (checked both variants). No firewall change."
    exit 1
  fi
else
  # Cron path: ntfy already resolved the filename, verify it exists on the server
  if ssh $SSH_OPTS "${LINODE_IP}" "test -s '$REMOTE_FILE'" 2>/dev/null; then
    log "Remote file confirmed: ${REMOTE_FILE}"
  else
    if ssh $SSH_OPTS "${LINODE_IP}" "test -e '$REMOTE_FILE'" 2>/dev/null; then
      notify "Remote file exists but is empty: ${REMOTE_FILE}. No firewall change." "high"
    else
      notify "Remote file not found: ${REMOTE_FILE}. No firewall change."
    fi
    exit 1
  fi
fi

# 3) Download
if scp $SSH_OPTS "${LINODE_IP}:${REMOTE_FILE}" . 2>"${SCRIPT_DIR}/scp_err.txt"; then
  rm -f "${SCRIPT_DIR}/scp_err.txt"
  if [[ -s "$FILENAME" ]]; then
    FILE_SIZE=$(du -h "$FILENAME" | cut -f1)
    log "File ${FILENAME} transferred. Size: ${FILE_SIZE}"
  else
    notify "Downloaded file is empty. No further action." "high"
    exit 1
  fi
else
  rm -f "${SCRIPT_DIR}/scp_err.txt"
  notify "SCP failed after existence check. Retrying in 60s."
  log "Sleeping 60s before retry..."
  sleep 60
  if scp $SSH_OPTS "${LINODE_IP}:${REMOTE_FILE}" .; then
    if [[ -s "$FILENAME" ]]; then
      FILE_SIZE=$(du -h "$FILENAME" | cut -f1)
      log "File ${FILENAME} transferred on retry. Size: ${FILE_SIZE}"
    else
      notify "Downloaded file is empty on retry. No further action." "high"
      exit 1
    fi
  else
    notify "Retry failed. No firewall change. Check disk space, perms, or paths." "high"
    exit 1
  fi
fi

# 4) Validate with ffprobe
DURATION=$(validate_video "$FILENAME") || exit 1

notify "Video Downloaded: ${FILENAME} (${FILE_SIZE}, ${DURATION})" "low"
exit 0
