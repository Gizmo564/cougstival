#!/bin/bash
# Runs the Phase 0 login test. First run creates .venv and installs Playwright + Chromium.
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -q playwright && .venv/bin/playwright install chromium || exit 1
fi
.venv/bin/python spike_login.py "$@"
