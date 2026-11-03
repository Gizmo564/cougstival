"""Tests for the schedule: regular 20-minute marks plus an exact run at every close."""
from datetime import datetime
from zoneinfo import ZoneInfo

from leaderboard import load_config
from loop import close_name, next_tick

MT = ZoneInfo("America/Denver")
CFG = load_config("config.json")


def at(day, h, m, s=0):
    return datetime(2026, 11, day, h, m, s, tzinfo=MT)


def main():
    # Regular marks.
    assert next_tick(CFG, at(9, 10, 5)) == at(9, 10, 20)
    assert next_tick(CFG, at(9, 10, 40)) == at(9, 11, 0)
    assert next_tick(CFG, at(9, 23, 50)) == at(10, 0, 0)

    # 5:00 PM is always a run, and is recognised as Monday's close.
    assert next_tick(CFG, at(9, 16, 59, 59)) == at(9, 17, 0)
    assert close_name(CFG, at(9, 17, 0)) == "Monday"
    assert close_name(CFG, at(9, 16, 40)) is None
    assert next_tick(CFG, at(9, 17, 0)) == at(9, 17, 20)   # strictly after

    # Saturday closes at 2:00 PM.
    assert close_name(CFG, at(14, 14, 0)) == "Saturday"
    assert close_name(CFG, at(14, 17, 0)) is None

    # A close that isn't on a 20-minute mark still gets its own run.
    odd = dict(CFG, days=[dict(CFG["days"][0], close="2026-11-09T17:10")] + CFG["days"][1:])
    assert next_tick(odd, at(9, 17, 0)) == at(9, 17, 10)
    assert close_name(odd, at(9, 17, 10)) == "Monday"
    assert next_tick(odd, at(9, 17, 10)) == at(9, 17, 20)
    print("loop tests passed")


if __name__ == "__main__":
    main()
