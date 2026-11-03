"""Unit tests, plus an optional replay against a past event's CSV exports.

    python3 test_leaderboard.py                                  # unit tests
    python3 test_leaderboard.py Submissions.csv Participants.csv  # + replay
"""
import csv
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from leaderboard import build, ranked, windows

MT = ZoneInfo("America/Denver")


NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def cfg(experience_id, dates, last_close="17:00"):
    """Each day runs midnight to 5:00 PM; the last day closes at `last_close`."""
    days = [{"name": n, "open": f"{d}T00:00", "close": f"{d}T{last_close if n == 'Saturday' else '17:00'}"}
            for n, d in zip(NAMES, dates)]
    return {"experience_id": experience_id, "timezone": "America/Denver", "days": days}


CFG_2026 = cfg("x", ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-14"], "14:00")
# Last year's event ran Mon Nov 10 - Sat Nov 15.
CFG_2025 = cfg("y", ["2025-11-10", "2025-11-11", "2025-11-12", "2025-11-13", "2025-11-14", "2025-11-15"], "14:00")


def sub(team, pts, utc, bonus=0):
    return {"teamName": team, "missionPoints": pts, "bonusPoints": bonus, "submissionCreatedAt": utc}


def day(data, name):
    return next(d for d in data["days"] if d["name"] == name)


def unit_tests():
    # Nov 2026 is MST (UTC-7). Monday: 00:00 MT = 07:00 UTC; 5:00 PM MT = 00:00 UTC next day.
    w = windows(CFG_2026)
    utc = ZoneInfo("UTC")
    assert w[0][1].astimezone(utc).isoformat() == "2026-11-09T07:00:00+00:00"
    assert w[0][2].astimezone(utc).isoformat() == "2026-11-10T00:00:00+00:00"
    assert w[5][2].astimezone(utc).isoformat() == "2026-11-14T21:00:00+00:00"   # Saturday 2:00 PM

    now = datetime(2026, 11, 14, 22, 0, tzinfo=MT)
    subs = [
        sub("a", 100, "2026-11-09T06:59:59.999Z"),   # Sun 11:59:59 PM -> before the event: total only
        sub("a", 10,  "2026-11-09T07:00:00.000Z"),   # Mon 12:00 AM    -> Monday (open edge included)
        sub("a", 20,  "2026-11-09T23:59:59.999Z"),   # Mon 4:59:59 PM  -> Monday
        sub("a", 30,  "2026-11-10T00:00:00.000Z"),   # Mon 5:00 PM     -> evening: total only
        sub("a", 40,  "2026-11-10T06:59:59.999Z"),   # Mon 11:59 PM    -> evening: total only, NOT Tuesday
        sub("b", 50,  "2026-11-10T07:00:00.000Z", bonus=-50),  # Tue 12:00 AM: net zero, still on Tuesday's board
        sub("b", 5,   "2026-11-14T21:00:00.000Z"),   # Sat 2:00 PM     -> after the last close: total only
    ]
    official = {"a": 200, "b": 5}
    data, bad = build(subs, official, CFG_2026, now)
    assert bad == [], bad
    assert {r["name"]: r["points"] for r in day(data, "Monday")["rows"]} == {"a": 30}
    assert {r["name"]: r["points"] for r in day(data, "Tuesday")["rows"]} == {"b": 0}
    assert data["total"]["outside_points"] == 100 + 30 + 40 + 5
    assert {r["name"]: r["points"] for r in data["total"]["rows"]} == {"a": 200, "b": 5}   # Total has everything
    assert all(d["status"] == "closed" for d in data["days"])

    # A number that doesn't reconcile is reported.
    _, bad = build(subs, {"a": 200, "b": 6}, CFG_2026, now)
    assert bad == [{"team": "b", "computed": 5, "official": 6}], bad

    # Status by time of day: open during the day, closed in the evening, upcoming overnight.
    def statuses(h, m=0, d=9):
        return [x["status"] for x in build([], {}, CFG_2026, datetime(2026, 11, d, h, m, tzinfo=MT))[0]["days"]]
    assert statuses(9) == ["open"] + ["upcoming"] * 5
    assert statuses(20) == ["closed"] + ["upcoming"] * 5          # Monday 8 PM
    assert statuses(0, 0, 10) == ["closed", "open"] + ["upcoming"] * 4   # Tuesday midnight
    assert statuses(16, 59, 9)[0] == "open" and statuses(17, 0, 9)[0] == "closed"

    # Closed days freeze: later changes don't alter a frozen day.
    prev, _ = build([sub("a", 10, "2026-11-09T18:00:00.000Z")], {"a": 10}, CFG_2026, now)
    later = [sub("a", 999, "2026-11-09T18:00:00.000Z")]
    data2, _ = build(later, {"a": 999}, CFG_2026, now, previous=prev)
    assert day(prev, "Monday")["rows"][0]["points"] == 10
    assert day(data2, "Monday")["rows"][0]["points"] == 10       # still 10, not 999

    # Frozen days from a different setup (e.g. a rehearsal) are never reused.
    other = dict(CFG_2026, days=[dict(d, close="2026-11-09T16:00") if d["name"] == "Monday" else d for d in CFG_2026["days"]])
    rehearsal, _ = build([sub("a", 10, "2026-11-09T18:00:00.000Z")], {"a": 10}, other, now)
    data3, _ = build(later, {"a": 999}, CFG_2026, now, previous=rehearsal)
    assert day(data3, "Monday")["rows"][0]["points"] == 999

    # Ties share a rank, next rank skips.
    r = ranked({"x": 5, "y": 5, "z": 1})
    assert [x["rank"] for x in r] == [1, 1, 3], r
    print("unit tests passed")


def replay(sub_csv, par_csv):
    """Every team's days + outside-window points must equal the official total."""
    with open(sub_csv, encoding="utf-8") as f:
        subs = [sub(r["Team Name"], int(r["Points"]), r["Submission Time"], int(r["Bonus Points"]))
                for r in csv.DictReader(f)]
    with open(par_csv, encoding="utf-8") as f:
        official = {r["Team Name"]: int(r["Points"]) for r in csv.DictReader(f)}
    now = datetime(2025, 11, 16, 12, 0, tzinfo=MT)
    data, bad = build(subs, official, CFG_2025, now)
    print(f"replay: {len(subs)} submissions, {len(official)} teams, {len(bad)} mismatches")
    for d in data["days"]:
        print(f"  {d['name']:<9} {len(d['rows']):>3} teams  top: {d['rows'][0]['name']} {d['rows'][0]['points']}")
    print(f"  outside windows: {data['total']['outside_points']} points")
    assert bad == [], bad[:5]
    print("replay reconciles for every team")


if __name__ == "__main__":
    unit_tests()
    if len(sys.argv) == 3:
        replay(sys.argv[1], sys.argv[2])
