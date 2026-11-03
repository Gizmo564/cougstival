# Cougstival leaderboard

Per-day leaderboards (Mon-Sat) plus a Total, built from the Goosechase admin data and published as a static site (GitHub Pages).

## Rules the code follows
- Each day counts points from midnight to 5:00 PM Mountain (Saturday: midnight to 2:00 PM).
- Points from 5:00 PM to midnight, and before the event, count toward the Total only. Nothing rolls into the next day.
- The Total is Goosechase's official overall number.
- Closed days are frozen at their close. The scheduler runs at EXACTLY each close time, plus every 20 minutes (:00/:20/:40).

## Install on the Ubuntu box (one line)
    curl -fsSL https://raw.githubusercontent.com/gizmo564/cougstival/main/install.sh | bash
It installs everything, asks for the login and alert settings (hidden input, written straight to a private `.env`),
tests the login, alerts and ping, runs one real update, then starts a service that survives reboots.
Website: https://gizmo564.github.io/cougstival/  (Settings -> Pages -> Deploy from a branch -> main, /docs)

## Commands (from the project folder)
- `./spike.sh`              login test (add `--headed` for a visible browser)
- `./run.sh`                one update cycle: logs in, fetches, writes docs/data.json (publishes if PUBLISH=1)
- `./run.sh --test-alert`   test notification  |  `./run.sh --test-ping`   test healthchecks.io
- `./loop.sh`               the scheduler (the Linux service runs this)
- `python3 rehearsal.py`, then `./loop.sh rehearsal`   the week squeezed into ~20 minutes (never publishes).
  Afterwards delete docs/data.json and state.json.
- `cd docs && python3 -m http.server 8000`   preview the website at http://localhost:8000
- Tests (no login needed): `python3 test_leaderboard.py`, `test_run.py`, `test_loop.py`, `test_publish.py`

## On the Linux box
- Status `systemctl status cougstival`, live log `journalctl -u cougstival -f`
- Stop `sudo systemctl stop cougstival`, start `sudo systemctl start cougstival`
- Update code `cd ~/cougstival && git pull && sudo systemctl restart cougstival`
- Pause the healthchecks.io check after Saturday.

## Files
config.json (event + day windows), leaderboard.py (day/total logic), goosechase.py (login + queries), run.py (update cycle,
alerts, publishing), loop.py (scheduler), docs/index.html (the website), install.sh (Linux installer),
first_push.sh (one-time publish from the Mac; stays local).
