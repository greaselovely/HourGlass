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
  -f            force: skip local file check, smart wait, and polling
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

# ============================================================================
# Load config from project JSON
# ============================================================================
CONFIG_JSON="${SCRIPT_DIR}/configs/${PROJECT}.json"
if [[ ! -f "$CONFIG_JSON" ]]; then
  echo "Error: Config not found: ${CONFIG_JSON}"
  exit 1
fi

# Status API config (primary method for cron path)
TAILSCALE_IP=$(jq -r '.status_api.tailscale_ip // empty' "$CONFIG_JSON")
STATUS_PORT=$(jq -r '.status_api.port // 8321' "$CONFIG_JSON")
STATUS_API_URL=""
if [[ -n "$TAILSCALE_IP" ]]; then
  STATUS_API_URL="http://${TAILSCALE_IP}:${STATUS_PORT}/status/${PROJECT}"
fi

# Notification services config
NTFY_BASE=$(jq -r '.ntfy // empty' "$CONFIG_JSON")
NTFY_TOPIC_NAME=$(jq -r '.alerts.services.ntfy.topic // empty' "$CONFIG_JSON")
NTFY_ENABLED=$(jq -r '.alerts.services.ntfy.enabled // false' "$CONFIG_JSON")
NTFY_TOPIC=""
NTFY_JSON_URL=""
if [[ "$NTFY_ENABLED" == "true" && -n "$NTFY_BASE" && -n "$NTFY_TOPIC_NAME" ]]; then
  NTFY_TOPIC="${NTFY_BASE%/}/${NTFY_TOPIC_NAME}"
  NTFY_JSON_URL="https://ntfy.sh/${NTFY_TOPIC_NAME}/json"
fi

PO_ENABLED=$(jq -r '.alerts.services.pushover.enabled // false' "$CONFIG_JSON")
PO_API_TOKEN=$(jq -r '.alerts.services.pushover.api_token // empty' "$CONFIG_JSON")
PO_USER_KEY=$(jq -r '.alerts.services.pushover.user_key // empty' "$CONFIG_JSON")

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

# Initial filename — may be updated after polling or SSH check
FILENAME="${PROJECT}.${DATE_STR}.mp4"
REMOTE_FILE="${REMOTE_BASE}/${FILENAME}"

log() {
  local msg="$1"
  echo "$(date '+%Y-%m-%d %H:%M:%S') | $msg"
}

# ============================================================================
# Notification: sends to all enabled services (ntfy + Pushover)
# ============================================================================
notify() {
  local msg="$1"
  local priority="${2:-default}"  # default, low, high, urgent
  log "$msg"

  # ntfy
  if [[ -n "$NTFY_TOPIC" ]]; then
    curl -s -H "Priority: ${priority}" -d "[v.sh] $msg" "${NTFY_TOPIC}" >/dev/null 2>&1 || true
  fi

  # Pushover
  if [[ "$PO_ENABLED" == "true" && -n "$PO_API_TOKEN" && -n "$PO_USER_KEY" ]]; then
    local po_priority=0
    case "$priority" in
      low)     po_priority=-1 ;;
      high)    po_priority=1 ;;
      urgent)  po_priority=1 ;;
      *)       po_priority=0 ;;
    esac
    curl -s --form-string "token=${PO_API_TOKEN}" \
            --form-string "user=${PO_USER_KEY}" \
            --form-string "message=[v.sh] $msg" \
            --form-string "priority=${po_priority}" \
            "https://api.pushover.net/1/messages.json" >/dev/null 2>&1 || true
  fi
}

# ============================================================================
# Status API functions (primary method — queries HourGlass over Tailscale)
# ============================================================================

# Fetch status JSON from the API. Returns empty string on failure.
get_api_status() {
  if [[ -z "$STATUS_API_URL" ]]; then
    return 1
  fi
  curl -s --connect-timeout 5 --max-time 10 "$STATUS_API_URL" 2>/dev/null || true
}

# Get target end time from status API
get_end_time_from_api() {
  local status
  status=$(get_api_status) || return
  if [[ -z "$status" ]]; then
    return
  fi
  echo "$status" | jq -r '.capture.target_time // empty' 2>/dev/null
}

# Poll status API for video_saved state
# Returns 0 on success (sets FILENAME and REMOTE_FILE), 1 on timeout
wait_for_video_via_api() {
  local max_attempts=60
  local interval=60
  local attempt=0

  log "Polling status API for video completion (${max_attempts}x${interval}s)..."

  while [[ $attempt -lt $max_attempts ]]; do
    attempt=$((attempt + 1))
    local status
    status=$(get_api_status) || { sleep "$interval"; continue; }

    if [[ -z "$status" ]]; then
      log "API unreachable (attempt ${attempt}/${max_attempts}). Waiting ${interval}s..."
      sleep "$interval"
      continue
    fi

    local state
    state=$(echo "$status" | jq -r '.state // empty' 2>/dev/null) || true

    case "$state" in
      video_saved)
        local api_filename
        api_filename=$(echo "$status" | jq -r '.video.filename // empty' 2>/dev/null) || true
        if [[ -n "$api_filename" ]]; then
          FILENAME="$api_filename"
          REMOTE_FILE="${REMOTE_BASE}/${FILENAME}"
        fi
        log "Video saved: ${FILENAME} (attempt ${attempt}/${max_attempts})"
        return 0
        ;;
      error)
        local detail
        detail=$(echo "$status" | jq -r '.detail // "unknown"' 2>/dev/null) || true
        log "HourGlass reported error: ${detail}"
        notify "HourGlass error: ${detail}" "high"
        return 1
        ;;
      idle)
        # Check if it completed (detail says "Completed") or never started
        local detail
        detail=$(echo "$status" | jq -r '.detail // empty' 2>/dev/null) || true
        if [[ "$detail" == "Completed" ]]; then
          # Video was saved but status already moved to idle — check for file
          log "Status is idle/Completed, checking for video file on server..."
          return 1  # Fall through to SSH resolution
        fi
        log "State: idle (attempt ${attempt}/${max_attempts}). Waiting ${interval}s..."
        ;;
      *)
        log "State: ${state:-unknown} (attempt ${attempt}/${max_attempts}). Waiting ${interval}s..."
        ;;
    esac

    if [[ $attempt -lt $max_attempts ]]; then
      sleep "$interval"
    fi
  done

  notify "Timed out waiting for video via status API after $((max_attempts * interval / 60))min" "high"
  return 1
}

# ============================================================================
# ntfy fallback functions (used when status API is not configured)
# ============================================================================

# Fetch today's End time from ntfy.sh topic history
get_end_time_from_ntfy() {
  if [[ -z "$NTFY_JSON_URL" ]]; then
    return
  fi
  local end_time
  end_time=$(curl -s "${NTFY_JSON_URL}?poll=1&since=24h" 2>/dev/null | \
    grep -o '"message":"[^"]*"' | \
    grep 'End:\\t' | \
    tail -1 | \
    sed 's/.*End:\\t\([0-9]\{1,2\}:[0-9]\{2\}\).*/\1/')
  echo "$end_time"
}

# Poll ntfy for "saved successfully" message, extract actual filename
wait_for_save_via_ntfy() {
  if [[ -z "$NTFY_JSON_URL" ]]; then
    notify "No status API or ntfy configured. Cannot poll for completion." "high"
    return 1
  fi

  local max_attempts=30
  local interval=60
  local attempt=0

  log "Falling back to ntfy polling for save confirmation (${max_attempts}x${interval}s)..."

  while [[ $attempt -lt $max_attempts ]]; do
    attempt=$((attempt + 1))
    local match
    match=$(curl -s "${NTFY_JSON_URL}?poll=1&since=24h" 2>/dev/null | \
      grep -o '"message":"[^"]*"' | \
      grep "${PROJECT}\.${DATE_STR}.*saved successfully" | \
      tail -1) || true

    if [[ -n "$match" ]]; then
      local extracted
      extracted=$(echo "$match" | grep -o "${PROJECT}\.[0-9]\{8\}\(\.[A-Z_]*\)*\.mp4") || true
      if [[ -n "$extracted" ]]; then
        FILENAME="$extracted"
        REMOTE_FILE="${REMOTE_BASE}/${FILENAME}"
        log "Save confirmed via ntfy: ${FILENAME} (attempt ${attempt}/${max_attempts})"
        return 0
      fi
    fi

    if [[ $attempt -lt $max_attempts ]]; then
      log "No confirmation yet (attempt ${attempt}/${max_attempts}). Waiting ${interval}s..."
      sleep "$interval"
    fi
  done

  notify "Timed out waiting for save confirmation via ntfy after $((max_attempts * interval / 60))min" "high"
  return 1
}

# ============================================================================
# Shared utilities
# ============================================================================

# Calculate seconds to sleep until video should be ready
calculate_sleep_seconds() {
  local end_time="$1"

  if [[ -z "$end_time" ]]; then
    echo "0"
    return
  fi

  local end_hour end_min
  end_hour=$(echo "$end_time" | cut -d: -f1)
  end_min=$(echo "$end_time" | cut -d: -f2)

  # Target time = End time + buffer (10# forces base-10)
  local target_min=$((10#$end_hour * 60 + 10#$end_min + SAVE_BUFFER_MIN))
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

# Check remote server for actual filename (handles NO_AUDIO variant)
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

  local dur_int=${duration%.*}
  local dur_min=$((dur_int / 60))
  local dur_sec=$((dur_int % 60))
  log "ffprobe OK: duration ${dur_min}m${dur_sec}s" >&2
  echo "${dur_min}m${dur_sec}s"
  return 0
}

# ============================================================================
# Pre-flight checks
# ============================================================================

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
[[ -n "$STATUS_API_URL" ]] && log "Status API: ${STATUS_API_URL}"

# ============================================================================
# Main flow: cron vs manual (-f)
# ============================================================================

if [[ "$FORCE" -eq 0 ]]; then
  # --- Cron path: smart wait → poll for completion → download → validate ---

  # Step 1: Get end time (try status API first, fall back to ntfy)
  END_TIME=""
  if [[ -n "$STATUS_API_URL" ]]; then
    END_TIME=$(get_end_time_from_api)
    [[ -n "$END_TIME" ]] && log "Capture end time from status API: ${END_TIME}"
  fi
  if [[ -z "$END_TIME" && -n "$NTFY_JSON_URL" ]]; then
    END_TIME=$(get_end_time_from_ntfy)
    [[ -n "$END_TIME" ]] && log "Capture end time from ntfy: ${END_TIME}"
  fi

  # Step 2: Smart wait
  if [[ -n "$END_TIME" ]]; then
    SLEEP_SECS=$(calculate_sleep_seconds "$END_TIME")
    if [[ $SLEEP_SECS -gt 0 ]]; then
      WAKE_TIME=$(date -v+"${SLEEP_SECS}"S +%H:%M 2>/dev/null || date -d "+${SLEEP_SECS} seconds" +%H:%M)
      log "Video not ready yet. Sleeping ${SLEEP_SECS}s (until ~${WAKE_TIME})..."
      notify "Waiting until ~${WAKE_TIME} for video to be ready" "low"
      sleep "$SLEEP_SECS"
      log "Waking up, polling for completion."
    else
      log "Target time already passed, polling for completion."
    fi
  else
    log "Could not determine end time, polling for completion."
  fi

  # Step 3: Poll for video completion (status API first, ntfy fallback)
  POLL_OK=0
  if [[ -n "$STATUS_API_URL" ]]; then
    if wait_for_video_via_api; then
      POLL_OK=1
    else
      log "Status API polling failed, trying ntfy fallback..."
    fi
  fi
  if [[ $POLL_OK -eq 0 ]]; then
    if ! wait_for_save_via_ntfy; then
      exit 1
    fi
  fi

else
  # --- Manual path (-f): skip wait + polling, resolve filename via SSH ---
  log "Force mode: skipping smart wait and polling."
fi

# ============================================================================
# Download flow (shared by cron and manual paths)
# ============================================================================

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

# 2) Resolve filename via SSH if not already resolved by polling (force mode, or poll gave us idle/Completed)
if [[ "$FORCE" -eq 1 ]] || [[ "$FILENAME" == "${PROJECT}.${DATE_STR}.mp4" ]]; then
  # Filename may not have been resolved by polling — check server for actual file
  if ! resolve_remote_filename; then
    if [[ "$FORCE" -eq 1 ]]; then
      notify "Remote file not found for ${PROJECT}.${DATE_STR} (checked both variants)."
    else
      notify "Remote file not found after polling: ${PROJECT}.${DATE_STR}."
    fi
    exit 1
  fi
else
  # Polling resolved the filename, verify it exists on the server
  if ssh $SSH_OPTS "${LINODE_IP}" "test -s '$REMOTE_FILE'" 2>/dev/null; then
    log "Remote file confirmed: ${REMOTE_FILE}"
  else
    if ssh $SSH_OPTS "${LINODE_IP}" "test -e '$REMOTE_FILE'" 2>/dev/null; then
      notify "Remote file exists but is empty: ${REMOTE_FILE}." "high"
    else
      notify "Remote file not found: ${REMOTE_FILE}."
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
    notify "Retry failed. Check disk space, perms, or paths." "high"
    exit 1
  fi
fi

# 4) Validate with ffprobe
DURATION=$(validate_video "$FILENAME") || exit 1

notify "Video Downloaded: ${FILENAME} (${FILE_SIZE}, ${DURATION})" "low"
exit 0
