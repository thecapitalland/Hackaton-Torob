"""Opening hours handling (Asia/Tehran).

The dataset stores ``weekly_hours`` as a JSON object with one key per Iranian
week day (``sat`` .. ``fri``).  Each day is either ``closed``, ``unsupported``
or ``declared`` with a list of ``{"start_time": "HH:MM:SS", "end_time": "..."}``
shifts.

Python's ``weekday()`` is Monday based, while the Iranian week starts on
Saturday, therefore the mapping below is what turns a Python weekday into the
dataset key (``weekday() == 4`` is Thursday in Python but *Friday* in Iran).
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..normalize import fa_digits

TEHRAN = ZoneInfo("Asia/Tehran")

WEEKDAY_KEY = {
    5: "sat",  # Saturday
    6: "sun",  # Sunday
    0: "mon",  # Monday
    1: "tue",  # Tuesday
    2: "wed",  # Wednesday
    3: "thu",  # Thursday
    4: "fri",  # Friday (Python Thursday)
}

DAY_NAMES_FA = {
    "sat": "شنبه",
    "sun": "یکشنبه",
    "mon": "دوشنبه",
    "tue": "سه‌شنبه",
    "wed": "چهارشنبه",
    "thu": "پنجشنبه",
    "fri": "جمعه",
}


def now_tehran() -> datetime:
    """Current time in Tehran (overridable through ``DEMO_NOW``)."""
    from ..data_static import demo_now

    override = demo_now()
    if override:
        try:
            parsed = datetime.fromisoformat(override)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=TEHRAN)
            return parsed.astimezone(TEHRAN)
        except ValueError:
            pass
    return datetime.now(TEHRAN)


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    parts = str(value).split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        return None
    if hour == 24:
        hour = 0
    try:
        return time(hour=hour, minute=minute, second=second)
    except ValueError:
        return None


def _parse_hours(weekly_hours: str | None) -> dict:
    if not weekly_hours:
        return {}
    if isinstance(weekly_hours, dict):
        return weekly_hours
    try:
        data = json.loads(weekly_hours)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _shift_bounds(shift: dict) -> tuple[time, time] | None:
    if not isinstance(shift, dict):
        return None
    start = _parse_time(shift.get("start_time"))
    end = _parse_time(shift.get("end_time"))
    if start is None or end is None:
        return None
    if start == end:
        # 00:00-00:00 (or 08:00-08:00) means "no hours declared" -> ignore
        return None
    return start, end


def open_status(weekly_hours: str | None, now: datetime | None = None) -> tuple[str, str]:
    """Return ``(status, label)`` where status is open / closed / unknown."""
    now = now or now_tehran()
    if now.tzinfo is None:
        now = now.replace(tzinfo=TEHRAN)
    data = _parse_hours(weekly_hours)
    if not data:
        return "unknown", "ساعت کاری اعلام نشده"

    day = data.get(WEEKDAY_KEY.get(now.weekday(), "sun"))
    if not isinstance(day, dict):
        return "unknown", "ساعت کاری اعلام نشده"

    status = day.get("status")
    if status == "closed":
        return "closed", "الان بسته"
    if status != "declared":
        return "unknown", "ساعت کاری اعلام نشده"

    shifts = day.get("shifts") or []
    bounds = [b for b in (_shift_bounds(s) for s in shifts) if b]
    if not bounds:
        return "unknown", "ساعت کاری اعلام نشده"

    current = now.time()
    for start, end in bounds:
        if start <= end:
            if start <= current < end:
                return "open", f"باز است تا {fa_digits(end.strftime('%H:%M'))}"
        else:  # overnight shift
            if current >= start or current < end:
                closing = datetime.combine(now.date(), end, tzinfo=now.tzinfo)
                if current < end:
                    closing += timedelta(days=1)
                return "open", f"باز است تا {fa_digits(closing.strftime('%H:%M'))}"
    return "closed", "الان بسته"


def today_hours_text(weekly_hours: str | None, now: datetime | None = None) -> str:
    """Human readable summary of today's shifts."""
    now = now or now_tehran()
    data = _parse_hours(weekly_hours)
    if not data:
        return "ساعت کاری اعلام نشده"
    day = data.get(WEEKDAY_KEY.get(now.weekday(), "sun"))
    if not isinstance(day, dict):
        return "ساعت کاری اعلام نشده"
    if day.get("status") == "closed":
        return "امروز تعطیل"
    shifts = day.get("shifts") or []
    bounds = [b for b in (_shift_bounds(s) for s in shifts) if b]
    if not bounds:
        return "ساعت کاری اعلام نشده"
    parts = [
        f"{fa_digits(start.strftime('%H:%M'))} تا {fa_digits(end.strftime('%H:%M'))}"
        for start, end in bounds
    ]
    return "، ".join(parts)


def is_open_now(weekly_hours: str | None, now: datetime | None = None) -> bool:
    status, _ = open_status(weekly_hours, now)
    return status == "open"


def price_age_days(last_price_changed_at: str | None, now: datetime | None = None) -> int | None:
    """Days since the seller last changed the price."""
    if not last_price_changed_at:
        return None
    now = now or now_tehran()
    try:
        stamp = datetime.fromisoformat(str(last_price_changed_at))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=TEHRAN)
    return max(0, (now.astimezone(TEHRAN) - stamp.astimezone(TEHRAN)).days)
