#!/usr/bin/env bash
# stop.sh — stop a HourGlass project and discard today's capture.
#
# Kills the project's capture tmux session (and any stray main.py), then deletes
# today's run folder(s) under IMAGES_FOLDER plus their matching AUDIO_FOLDER
# scratch dirs. Use it when a day's capture is garbage (source site down, DDoS'd,
# nothing but duplicate frames) and you'd rather have no video than a bad one.
#
# The status API service is deliberately left alone — it isn't what alerts.
#
# Usage: ./stop.sh [PROJECT] [-y] [-n] [--keep-images]   (PROJECT default: VLA)
#   -y, --yes        don't prompt before deleting (required when non-interactive)
#   -n, --dry-run    show what would be killed/removed, change nothing
#       --keep-images  stop capture only; leave today's folders on disk
set -euo pipefail

PROJECT="VLA"
ASSUME_YES=0
DRY_RUN=0
KEEP_IMAGES=0
for arg in "$@"; do
    case "$arg" in
        -y|--yes)     ASSUME_YES=1 ;;
        -n|--dry-run) DRY_RUN=1 ;;
        --keep-images) KEEP_IMAGES=1 ;;
        -*) echo "Unknown option: $arg" >&2; exit 1 ;;
        *)  PROJECT="$arg" ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONFIG_FILE="configs/${PROJECT}.json"
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Config not found: ${SCRIPT_DIR}/${CONFIG_FILE}" >&2
    exit 1
fi

# Same sources main.py uses: session name, both run-folder roots, and the sun
# TIME_OFFSET_HOURS that decides which calendar day "today" is for this project.
CONFIG_DATA="$(venv/bin/python3 -c "
import json, os
c = json.load(open('$CONFIG_FILE'))
ff = c.get('files_and_folders', {})
exp = lambda p: os.path.expanduser(p) if p else ''
print('|'.join([
    c.get('tmux', {}).get('session_name', 'hourglass-timelapse'),
    exp(ff.get('IMAGES_FOLDER', '')),
    exp(ff.get('AUDIO_FOLDER', '')),
    str(c.get('sun', {}).get('TIME_OFFSET_HOURS', 0)),
]))
")"
IFS='|' read -r SESSION_NAME IMAGES_FOLDER AUDIO_FOLDER TIME_OFFSET <<< "$CONFIG_DATA"

# Run folders are named YYYYMMDD_xxxxxxxx (see utils.get_or_create_run_id), so
# today's date is a plain prefix match — offset applied the way capture does it.
TODAY="$(venv/bin/python3 -c "
from datetime import datetime, timedelta
print((datetime.now() + timedelta(hours=float('$TIME_OFFSET'))).strftime('%Y%m%d'))
")"

echo "== Stopping HourGlass '${PROJECT}'  (tmux session: ${SESSION_NAME}) =="
[[ "$DRY_RUN" -eq 1 ]] && echo "[*] DRY RUN — nothing will be killed or deleted"

# 1) Kill the capture tmux session (SIGHUPs its main.py child with it).
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "[*] Killing tmux session ${SESSION_NAME}"
    [[ "$DRY_RUN" -eq 1 ]] || tmux kill-session -t "$SESSION_NAME"
else
    echo "[*] No tmux session ${SESSION_NAME} to kill"
fi

# 2) Reap any stray main.py for THIS project only (surgical — matches the arg,
#    so it never touches other projects or the status service).
if pgrep -f "main.py ${PROJECT}" >/dev/null 2>&1; then
    echo "[*] Reaping stray 'main.py ${PROJECT}' process(es)"
    if [[ "$DRY_RUN" -eq 0 ]]; then
        pkill -f "main.py ${PROJECT}" || true
        sleep 1
    fi
fi

if [[ "$KEEP_IMAGES" -eq 1 ]]; then
    echo "[*] Keeping today's capture folders (--keep-images)"
    echo "Done. Capture stopped."
    exit 0
fi

# 3) Collect today's run folders. Anything not matching YYYYMMDD_ is skipped —
#    this script does an rm -rf, so the name shape is the safety check.
TARGETS=()
if [[ -d "$IMAGES_FOLDER" ]]; then
    while IFS= read -r d; do
        [[ -n "$d" ]] && TARGETS+=("$d")
    done < <(find "$IMAGES_FOLDER" -mindepth 1 -maxdepth 1 -type d -name "${TODAY}_*" | sort)
fi
# Matching audio scratch dirs share the run_id, so drop them with their run.
for t in "${TARGETS[@]:-}"; do
    [[ -z "$t" ]] && continue
    audio_dir="${AUDIO_FOLDER}/$(basename "$t")"
    [[ -d "$audio_dir" ]] && TARGETS+=("$audio_dir")
done

if [[ "${#TARGETS[@]}" -eq 0 ]]; then
    echo "[*] No ${TODAY} run folders under ${IMAGES_FOLDER} — nothing to remove"
    echo "Done. Capture stopped."
    exit 0
fi

echo "[*] Capture folders for ${TODAY}:"
for t in "${TARGETS[@]}"; do
    printf '      %s  (%s, %s files)\n' \
        "$t" \
        "$(du -sh "$t" 2>/dev/null | cut -f1)" \
        "$(find "$t" -type f 2>/dev/null | wc -l | tr -d ' ')"
done

# 4) Confirm, then remove. Non-interactive callers must pass -y explicitly.
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[*] DRY RUN — would remove the folders above"
    exit 0
fi
if [[ "$ASSUME_YES" -eq 0 ]]; then
    if [[ ! -t 0 ]]; then
        echo "[!] Refusing to delete without a TTY — re-run with -y" >&2
        exit 1
    fi
    read -r -p "Delete these folders? [y/N] " reply
    if [[ ! "$reply" =~ ^[Yy]$ ]]; then
        echo "[*] Aborted — capture is stopped, folders left in place"
        exit 0
    fi
fi

for t in "${TARGETS[@]}"; do
    echo "[*] Removing ${t}"
    rm -rf "$t"
done

echo "== Post-stop state =="
tmux ls 2>/dev/null || echo "  (no tmux sessions)"
echo "Done. Capture stopped and ${TODAY} folders removed."
