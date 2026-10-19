from __future__ import annotations

import datetime as dt


def report_date_for(rule: str, today: dt.date | None = None) -> dt.date:
    """Resolve the report_date rule from config.yaml."""
    today = today or dt.date.today()
    rule = (rule or "today").lower()
    if rule == "today":
        return today
    if rule == "tomorrow":
        return today + dt.timedelta(days=1)
    if rule == "next_weekday":
        d = today + dt.timedelta(days=1)
        while d.weekday() >= 5:  # 5 = Sat, 6 = Sun
            d += dt.timedelta(days=1)
        return d
    raise SystemExit(f"Unknown report_date rule {rule!r}; use today, tomorrow or next_weekday")