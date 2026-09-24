from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

THURSDAY = 3
SATURDAY = 5


def tzinfo(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def now_tz(tz_name: str) -> datetime:
    return datetime.now(tzinfo(tz_name))


def week_start(when: datetime | date | None = None, tz_name: str = "America/Indiana/Indianapolis") -> date:
    if isinstance(when, date) and not isinstance(when, datetime):
        current = datetime.combine(when, time.min, tzinfo=tzinfo(tz_name))
    elif when is None:
        current = now_tz(tz_name)
    else:
        current = when.astimezone(tzinfo(tz_name))
    days_since_thu = (current.weekday() - THURSDAY) % 7
    start = current - timedelta(days=days_since_thu)
    return start.date()


def week_end(thu_start: date) -> date:
    return thu_start + timedelta(days=6)


def local_today(tz_name: str) -> date:
    return now_tz(tz_name).date()


def at_local(d: date, hour: int, minute: int, tz_name: str) -> datetime:
    return datetime.combine(d, time(hour, minute), tzinfo=tzinfo(tz_name))


def quiet_cutoff(thu_start: date, tz_name: str) -> datetime:
    return at_local(thu_start, 18, 0, tz_name)


def infraction_cutoff(thu_start: date, tz_name: str) -> datetime:
    saturday = thu_start + timedelta(days=2)
    return at_local(saturday, 18, 0, tz_name)
