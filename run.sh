#!/bin/bash
# Runs one update cycle (or: ./run.sh --test-alert). Uses .env and the .venv made by spike.sh.
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
.venv/bin/python run.py "$@"
