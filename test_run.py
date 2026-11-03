"""Tests for the update cycle and the alert rules (no network, no browser)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from goosechase import LoginError
from leaderboard import load_config
from run import cycle, event_over, sane

CFG = load_config("config.json")
MT = ZoneInfo("America/Denver")
T0 = datetime(2026, 11, 9, 10, 0, tzinfo=MT)


def good_fetch():
    return ([{"teamName": "a", "missionPoints": 10, "bonusPoints": 0,
              "submissionCreatedAt": "2026-11-09T17:00:00.000Z"}], {"a": 10})


def failing(exc):
    def f():
        raise exc
    return f


def titles(alerts):
    return [a[0] for a in alerts]


def main():
    # Good run: data produced, no alerts.
    state = {}
    data, alerts = cycle(CFG, T0, None, state, good_fetch)
    assert data and alerts == [] and state["last_success"]

    # Login fails: one urgent alert immediately, then silence for an hour, then a repeat.
    data, alerts = cycle(CFG, T0 + timedelta(minutes=20), None, state, failing(LoginError("expired")))
    assert data is None and titles(alerts) == ["Goosechase login needed"] and alerts[0][2] == "urgent"
    _, alerts = cycle(CFG, T0 + timedelta(minutes=40), None, state, failing(LoginError("expired")))
    assert alerts == []
    _, alerts = cycle(CFG, T0 + timedelta(minutes=85), None, state, failing(LoginError("expired")))
    assert titles(alerts) == ["Goosechase login needed"]

    # Recovery is announced once.
    _, alerts = cycle(CFG, T0 + timedelta(minutes=105), None, state, good_fetch)
    assert titles(alerts) == ["Goosechase login recovered"]
    _, alerts = cycle(CFG, T0 + timedelta(minutes=125), None, state, good_fetch)
    assert alerts == []

    # Other errors: silent until 60 minutes without a success, then one alert, then hourly.
    state = {}
    cycle(CFG, T0, None, state, good_fetch)
    for m, expect in [(20, []), (40, []), (60, ["Leaderboard not updating"]), (80, []), (125, ["Leaderboard not updating"])]:
        _, alerts = cycle(CFG, T0 + timedelta(minutes=m), None, state, failing(RuntimeError("boom")))
        assert titles(alerts) == expect, (m, alerts)

    # Never succeeded at all: still alerts after 60 minutes.
    state = {}
    cycle(CFG, T0, None, state, failing(RuntimeError("boom")))
    _, alerts = cycle(CFG, T0 + timedelta(minutes=61), None, state, failing(RuntimeError("boom")))
    assert titles(alerts) == ["Leaderboard not updating"]

    # A big drop in submission count is not published.
    state = {"sub_count": 1000}
    data, _ = cycle(CFG, T0, None, state, good_fetch)
    assert data is None and "not publishing" in state["last_error"]
    assert sane(900, 1000) and not sane(100, 1000) and sane(5, None)

    # Mismatch alert fires once per distinct set.
    state = {}
    def off_by_one():
        subs, official = good_fetch()
        return subs, {"a": 11}
    _, alerts = cycle(CFG, T0, None, state, off_by_one)
    assert titles(alerts) == ["Leaderboard totals do not reconcile"]
    _, alerts = cycle(CFG, T0 + timedelta(minutes=20), None, state, off_by_one)
    assert alerts == []

    # Event over: only after the last close, and only once every day is frozen.
    close = datetime(2026, 11, 14, 14, 0, tzinfo=MT)
    before, _ = cycle(CFG, close - timedelta(minutes=10), None, {}, good_fetch)    # Saturday still open
    assert not event_over(CFG, close + timedelta(hours=1), before)                # not frozen yet: keep going
    done, _ = cycle(CFG, close + timedelta(minutes=5), before, {}, good_fetch)    # closing run freezes it
    assert all(d["frozen"] for d in done["days"])
    assert not event_over(CFG, close + timedelta(minutes=20), done)               # within 30 min of close
    assert event_over(CFG, close + timedelta(minutes=31), done)
    print("run tests passed")


def test_output_failure():
    """If saving/publishing fails, the update counts as failed (so the stale alert can fire)."""
    def boom(data):
        raise RuntimeError("push rejected")
    state = {}
    data, _ = cycle(CFG, T0, None, state, good_fetch, output=boom)
    assert data is None and "push rejected" in state["last_error"] and "last_success" not in state
    print("output-failure test passed")


if __name__ == "__main__":
    main()
    test_output_failure()
