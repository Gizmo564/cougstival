"""One update cycle: log in, fetch, build, write docs/data.json (and publish it), alert if something is wrong.

    python3 run.py                # one update cycle
    python3 run.py --test-alert   # send a test notification and exit
    python3 run.py --test-ping    # ping the healthchecks.io URL and exit

Normally loop.py runs this on schedule. Exit code: 0 ok, 1 update failed, 2 another run was in progress.
Environment: GC_EMAIL, GC_PASSWORD, NTFY_TOPIC (alerts), PING_URL (healthchecks.io), CONFIG (alternate config file),
PUBLISH=1 and GIT_EMAIL (to publish docs/data.json to GitHub)
"""
import fcntl
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from goosechase import LoginError, fetch_all, session
from leaderboard import build, load_config, windows

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "docs", "data.json")
STATE = os.path.join(HERE, "state.json")
STALE = timedelta(minutes=60)    # no successful update for this long -> alert
REPEAT = timedelta(hours=1)      # repeat an unresolved alert this often


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def sane(new_count, old_count):
    """Refuse to publish if the submission count suddenly drops a lot (a bad fetch, not real removals)."""
    return old_count is None or new_count >= old_count * 0.8


def event_over(cfg, now, previous):
    last_close = windows(cfg)[-1][2]
    return bool(previous) and now > last_close + timedelta(minutes=30) and all(d.get("frozen") for d in previous["days"])


def update_state(state, now, ok, auth_failed, err, mismatches):
    """Update state in place; return the alerts to send as (title, message, priority)."""
    alerts, t = [], now.isoformat()
    state.setdefault("first_seen", t)

    def due(key):
        last = state.get(key)
        return not last or now - datetime.fromisoformat(last) >= REPEAT

    if ok:
        if state.get("auth_failing"):
            alerts.append(("Goosechase login recovered", "Leaderboard updates are working again.", "default"))
        state.update(last_success=t, auth_failing=False, last_error=None)
        key = ",".join(sorted(m["team"] for m in mismatches))
        if key and key != state.get("mismatch_key"):
            m = mismatches[0]
            alerts.append(("Leaderboard totals do not reconcile",
                           f"{len(mismatches)} team(s) differ from Goosechase totals, e.g. {m['team']}: "
                           f"computed {m['computed']} vs official {m['official']}.", "low"))
        state["mismatch_key"] = key
        return alerts

    state["last_error"] = err
    if auth_failed:
        if not state.get("auth_failing") or due("last_auth_alert"):
            alerts.append(("Goosechase login needed",
                           f"The leaderboard cannot log in ({err}). Log in again on the machine running it.", "urgent"))
            state["last_auth_alert"] = t
        state["auth_failing"] = True
    else:
        since = datetime.fromisoformat(state.get("last_success") or state["first_seen"])
        if now - since >= STALE and due("last_stale_alert"):
            alerts.append(("Leaderboard not updating",
                           f"No successful update since {since.isoformat()}. Last error: {err}", "high"))
            state["last_stale_alert"] = t
    return alerts


def cycle(cfg, now, previous, state, fetch, output=None):
    """Returns (new data or None, alerts). fetch() -> (submissions, official totals).
    output(data) saves/publishes the result; if it raises, the update counts as failed."""
    data, mismatches, err, auth_failed, ok = None, [], None, False, False
    try:
        subs, official = fetch()
        if not sane(len(subs), state.get("sub_count")):
            raise RuntimeError(f"fetched {len(subs)} submissions but had {state.get('sub_count')}; not publishing")
        data, mismatches = build(subs, official, cfg, now, previous)
        if output:
            output(data)
        state["sub_count"] = len(subs)
        ok = True
    except LoginError as e:
        auth_failed, err = True, str(e)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    return (data if ok else None), update_state(state, now, ok, auth_failed, err, mismatches)


def publish(now):
    """Commit docs/data.json and push it (GitHub Pages serves /docs). Commits are authored by Team Rocket."""
    def git(*args):
        return subprocess.run(["git", "-C", HERE, *args], check=True, capture_output=True, text=True, timeout=90)
    git("add", "docs/data.json")
    if subprocess.run(["git", "-C", HERE, "diff", "--cached", "--quiet"]).returncode == 0:
        return  # nothing changed
    git("-c", "user.name=Team Rocket", "-c", f"user.email={os.environ['GIT_EMAIL']}",
        "commit", "-m", f"Update leaderboard {now:%a %H:%M}")
    try:
        git("push")
    except subprocess.CalledProcessError:
        git("pull", "--rebase")  # someone pushed code to the repo meanwhile
        git("push")


def notify(title, message, priority):
    topic = os.environ.get("NTFY_TOPIC")
    print(f"ALERT [{priority}] {title}: {message}")
    if not topic:
        print("  not sent: NTFY_TOPIC is not set (add it to .env)")
        return
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=message.encode(),
                                     headers={"Title": title, "Priority": priority})
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"  sent to ntfy.sh/{topic} (HTTP {r.status})")
    except Exception as e:
        print("  could not send alert:", e)


def ping(ok=True):
    """Tell healthchecks.io we're alive (or failed). It alerts you if the pings stop."""
    url = os.environ.get("PING_URL")
    if not url:
        return
    try:
        with urllib.request.urlopen(url if ok else url.rstrip("/") + "/fail", timeout=10) as r:
            print(f"  pinged healthchecks ({'ok' if ok else 'fail'}, HTTP {r.status})")
    except Exception as e:
        print("  ping failed:", e)


def main():
    if "--test-alert" in sys.argv:
        notify("Cougstival test alert", "If you can read this, alerts work.", "default")
        return 0
    if "--test-ping" in sys.argv:
        ping(True)
        return 0

    cfg = load_config(os.environ.get("CONFIG") or os.path.join(HERE, "config.json"))
    now = datetime.now(ZoneInfo(cfg["timezone"]))

    lock = open(os.path.join(HERE, ".run.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("previous run still going; skipping")
        return 2

    previous, state = load_json(OUT, None), load_json(STATE, {})
    if event_over(cfg, now, previous):
        print("event is over and every day is frozen; nothing to do")
        ping(True)
        return 0

    def fetch():
        with session(cfg["experience_id"], os.environ.get("GC_EMAIL"), os.environ.get("GC_PASSWORD")) as gql:
            return fetch_all(gql, cfg["experience_id"])

    def output(data):
        save_json(OUT, data)
        if os.environ.get("PUBLISH") == "1" and not os.environ.get("CONFIG"):   # never publish a rehearsal
            publish(now)

    data, alerts = cycle(cfg, now, previous, state, fetch, output)
    if data:
        print(f"{now:%a %H:%M:%S} updated: " + ", ".join(f"{d['name']} {d['status']}" for d in data["days"]))
    else:
        print(f"{now:%a %H:%M:%S} update FAILED: {state.get('last_error')}")
    save_json(STATE, state)
    for a in alerts:
        notify(*a)
    ping(bool(data))
    return 0 if data else 1


if __name__ == "__main__":
    sys.exit(main())
