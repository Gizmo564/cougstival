#!/bin/bash
# Runs the scheduler (loop.py) with your .env. Leave it running.
#   ./loop.sh              the real event
#   ./loop.sh rehearsal    the squeezed-down ~20 minute rehearsal (run python3 rehearsal.py first)
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
[ "$1" = "rehearsal" ] && export CONFIG="$PWD/rehearsal.json"
exec .venv/bin/python loop.py
