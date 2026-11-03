"""Writes rehearsal.json: the same event squeezed into ~20 minutes so you can watch the scheduler and freezing work.

    python3 rehearsal.py
    CONFIG=rehearsal.json python3 loop.py        (or ./loop.sh rehearsal)

Day 1 closes about 4 minutes from now and each later day 3 minutes after that. Uses the real 2026 experience.
Afterwards delete docs/data.json and state.json, then run without CONFIG for the real event.
"""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

cfg = json.load(open("config.json"))
tz = ZoneInfo(cfg["timezone"])
now = datetime.now(tz).replace(second=0, microsecond=0)
names = [d["name"] for d in cfg["days"]]
closes = [now + timedelta(minutes=4 + 3 * i) for i in range(len(names))]
opens = [now - timedelta(hours=1)] + closes[:-1]   # each day opens when the previous one closes
fmt = "%Y-%m-%dT%H:%M"
cfg.update(days=[{"name": n, "open": o.strftime(fmt), "close": c.strftime(fmt)}
                                for n, o, c in zip(names, opens, closes)])
json.dump(cfg, open("rehearsal.json", "w"), indent=2)
print("rehearsal.json written. Days close at:")
for n, c in zip(names, closes):
    print(f"  {n:<9} {c:%H:%M}")
