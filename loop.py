"""Runs the update cycle on schedule. Leave this running all week.

    python3 loop.py

Runs every 20 minutes on the :00 / :20 / :40 marks, and ALWAYS exactly at each day's close time from the config
(5:00 PM, and 2:00 PM Saturday), even if the config's times don't line up with the 20-minute marks.
A close-time run that fails is retried every minute (up to 5 tries) and raises an urgent alert if it never works.
Environment: same as run.py.
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from leaderboard import load_config, windows
from run import HERE, notify

STEP = 20            # minutes between regular runs
CLOSE_TRIES = 5
RUN_TIMEOUT = 300    # seconds; a stuck run is killed


def next_tick(cfg, after):
    """Next run time strictly after `after`: the next 20-minute mark, or an earlier day close."""
    mark = after.replace(minute=after.minute // STEP * STEP, second=0, microsecond=0) + timedelta(minutes=STEP)
    return min([mark] + [close for _, _, close in windows(cfg) if close > after])


def close_name(cfg, tick):
    """The day that closes exactly at `tick`, or None."""
    return next((name for name, _, close in windows(cfg) if abs((close - tick).total_seconds()) < 1), None)


def run_once():
    """Run run.py in its own process, so a hang or crash can't take the loop down. Returns its exit code."""
    try:
        return subprocess.run([sys.executable, os.path.join(HERE, "run.py")], timeout=RUN_TIMEOUT).returncode
    except subprocess.TimeoutExpired:
        print("run timed out and was killed")
        return 1


def run_close(day):
    for attempt in range(1, CLOSE_TRIES + 1):
        if run_once() == 0:
            return
        if attempt < CLOSE_TRIES:
            time.sleep(60)
    notify(f"{day} closing run FAILED",
           f"{day} closed but the final update failed {CLOSE_TRIES} times. The board is not frozen yet. Check the machine.",
           "urgent")


def sleep_until(t, tz):
    while True:
        left = (t - datetime.now(tz)).total_seconds()
        if left <= 0:
            return
        time.sleep(min(left, 20))  # short sleeps, so a laptop waking from sleep notices at once


def main():
    cfg = load_config(os.environ.get("CONFIG") or os.path.join(HERE, "config.json"))
    tz = ZoneInfo(cfg["timezone"])
    print("scheduler started; Ctrl-C to stop")
    run_once()  # don't wait for the next mark after a (re)start
    while True:
        tick = next_tick(cfg, datetime.now(tz))
        print(f"next run at {tick:%a %H:%M:%S}")
        sleep_until(tick, tz)
        day = close_name(cfg, tick)
        run_close(day) if day else run_once()


if __name__ == "__main__":
    main()
