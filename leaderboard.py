"""Turn Goosechase submissions into per-day leaderboards plus a total.

A submission counts toward a day only if its timestamp is inside that day's window [open, close), which is
midnight to 5:00 PM (Saturday to 2:00 PM). Everything else (evenings, before the event) counts toward the
Total only and never rolls into another day. Points = mission points + bonus.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo


def load_config(path="config.json"):
    with open(path) as f:
        return json.load(f)


def config_key(cfg):
    """Identifies an event setup, so data from a rehearsal or another event is never reused."""
    return json.dumps([cfg["experience_id"], cfg["timezone"], cfg["days"]], sort_keys=True)


def parse_utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def windows(cfg):
    """[(day name, open, close)] as timezone-aware datetimes."""
    tz = ZoneInfo(cfg["timezone"])

    def at(text):
        return datetime.fromisoformat(text).replace(tzinfo=tz)
    return [(d["name"], at(d["open"]), at(d["close"])) for d in cfg["days"]]


def tiebreak(name):
    """Order within a tie. Placeholder until the real tiebreaker rule exists."""
    return name.lower()


def ranked(points_by_team):
    """Rows sorted by points; tied teams share a rank (1, 2, 2, 4)."""
    items = sorted(points_by_team.items(), key=lambda kv: (-kv[1], tiebreak(kv[0])))
    rows, prev, rank = [], None, 0
    for i, (name, pts) in enumerate(items, 1):
        if pts != prev:
            rank, prev = i, pts
        rows.append({"rank": rank, "name": name, "points": pts})
    return rows


def build(subs, official, cfg, now, previous=None):
    """Return (data for the website, list of teams whose numbers don't reconcile).

    subs:     dicts with teamName, missionPoints, bonusPoints, submissionCreatedAt
    official: {teamName: Goosechase's overall points}
    now:      timezone-aware datetime
    previous: last published data, used to keep closed days frozen
    """
    if previous and previous.get("config_key") != config_key(cfg):
        previous = None  # data from a different setup (e.g. a rehearsal): start fresh
    wins = windows(cfg)
    daily = {name: {} for name, _, _ in wins}
    outside = {}  # points outside every window: evenings, before the event, after the last close

    for s in subs:
        t = parse_utc(s["submissionCreatedAt"])
        team = s["teamName"]
        pts = (s["missionPoints"] or 0) + (s["bonusPoints"] or 0)
        for name, opens, closes in wins:
            if opens <= t < closes:
                daily[name][team] = daily[name].get(team, 0) + pts
                break
        else:
            outside[team] = outside.get(team, 0) + pts

    prev_days = {d["name"]: d for d in (previous or {}).get("days", [])}
    days = []
    for name, opens, closes in wins:
        status = "upcoming" if now < opens else "closed" if now >= closes else "open"
        old = prev_days.get(name)
        if status == "closed" and old and old.get("frozen"):
            days.append(old)  # closed days don't change
            continue
        days.append({
            "name": name,
            "status": status,
            "opens": opens.isoformat(),
            "closes": closes.isoformat(),
            "frozen": status == "closed",
            "rows": ranked(daily[name]),
        })

    # Reconcile: every team's days + outside must equal Goosechase's overall number.
    mismatches = []
    for team in set(official) | set(outside) | {t for d in daily.values() for t in d}:
        mine = sum(d.get(team, 0) for d in daily.values()) + outside.get(team, 0)
        if mine != official.get(team, 0):
            mismatches.append({"team": team, "computed": mine, "official": official.get(team, 0)})

    data = {
        "updated": now.isoformat(),
        "config_key": config_key(cfg),
        "days": days,
        "total": {
            "rows": ranked({t: p for t, p in official.items() if p != 0}),
            "outside_points": sum(outside.values()),
        },
    }
    return data, mismatches
