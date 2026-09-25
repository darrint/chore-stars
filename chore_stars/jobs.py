from datetime import datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chore_stars.config import Settings
from chore_stars.models import (
    ChoreSlot,
    ChoreTemplate,
    Grab,
    Standing,
    StarEvent,
    User,
    Week,
)
from chore_stars.timeutil import infraction_cutoff, local_today, now_tz, quiet_cutoff, week_end, week_start


def ensure_week(db: Session, settings: Settings, when: datetime | None = None) -> Week:
    thu = week_start(when, settings.timezone)
    week = db.execute(select(Week).where(Week.thu_start == thu)).scalar_one_or_none()
    if week is None:
        week = Week(thu_start=thu, star_budget=settings.star_budget)
        db.add(week)
        db.flush()
    for user in db.execute(select(User).where(User.role == "resident")).scalars():
        standing = db.execute(
            select(Standing).where(Standing.user_id == user.id, Standing.week_id == week.id)
        ).scalar_one_or_none()
        if standing is None:
            db.add(Standing(user_id=user.id, week_id=week.id, status="quiet"))
    db.flush()
    return week


def recalc_week_pool(db: Session, week: Week) -> None:
    awarded = db.execute(
        select(func.coalesce(func.sum(StarEvent.amount), 0)).where(
            StarEvent.week_id == week.id, StarEvent.kind == "award"
        )
    ).scalar_one()
    week.awarded_total = int(awarded)
    week.owe_stars = max(0, week.awarded_total - week.star_budget - week.pool_adjust)


def open_slots(db: Session, settings: Settings) -> int:
    week = ensure_week(db, settings)
    today = local_today(settings.timezone)
    created = 0
    templates = db.execute(select(ChoreTemplate).where(ChoreTemplate.active.is_(True))).scalars()
    for template in templates:
        slot_date = week.thu_start if template.period == "week" else today
        if template.period == "week" and today < week.thu_start:
            continue
        existing = db.execute(
            select(func.count()).where(
                ChoreSlot.week_id == week.id,
                ChoreSlot.template_id == template.id,
                ChoreSlot.slot_date == slot_date,
            )
        ).scalar_one()
        for seq in range(int(existing) + 1, template.cap + 1):
            db.add(
                ChoreSlot(
                    week_id=week.id,
                    template_id=template.id,
                    slot_date=slot_date,
                    advertised_stars=template.default_stars,
                    status="open",
                    sequence=seq,
                )
            )
            created += 1
    db.flush()
    return created


def expire_stale_slots(db: Session, settings: Settings) -> int:
    today = local_today(settings.timezone)
    expired = 0
    rows = db.execute(
        select(ChoreSlot, ChoreTemplate.period)
        .join(ChoreTemplate)
        .where(ChoreSlot.status.in_(("open", "grabbed")))
    ).all()
    for slot, period in rows:
        stale = week_end(slot.slot_date) < today if period == "week" else slot.slot_date < today
        if not stale:
            continue
        if slot.status == "grabbed":
            for grab in db.execute(
                select(Grab).where(Grab.slot_id == slot.id, Grab.status == "active", Grab.submitted_at.is_(None))
            ).scalars():
                grab.status = "expired"
        slot.status = "expired"
        expired += 1
    db.flush()
    return expired


def expire_grabs(db: Session, settings: Settings) -> int:
    now = now_tz(settings.timezone)
    expired = 0
    grabs = db.execute(
        select(Grab).where(Grab.status == "active", Grab.submitted_at.is_(None), Grab.expires_at <= now)
    ).scalars()
    for grab in grabs:
        grab.status = "expired"
        slot = grab.slot
        if slot.status == "grabbed":
            slot.status = "open"
        expired += 1
    db.flush()
    return expired


def standing_check(db: Session, settings: Settings) -> None:
    week = ensure_week(db, settings)
    now = now_tz(settings.timezone)
    quiet_at = quiet_cutoff(week.thu_start, settings.timezone)
    infraction_at = infraction_cutoff(week.thu_start, settings.timezone)
    standings = db.execute(select(Standing).where(Standing.week_id == week.id)).scalars()
    for standing in standings:
        if standing.cleared_at is not None and not standing.parent_marked_miss:
            continue
        awarded = db.execute(
            select(func.coalesce(func.sum(StarEvent.amount), 0)).where(
                StarEvent.user_id == standing.user_id,
                StarEvent.week_id == week.id,
                StarEvent.kind == "award",
            )
        ).scalar_one()
        if awarded > 0:
            standing.status = "present"
            continue
        if standing.parent_marked_miss or now >= infraction_at:
            if standing.status != "infraction":
                standing.status = "infraction"
                standing.misses = max(standing.misses, 1)
        elif now >= quiet_at:
            standing.status = "quiet"
        else:
            standing.status = "quiet"
    db.flush()


def mark_present(db: Session, user_id: int, week: Week) -> None:
    standing = db.execute(
        select(Standing).where(Standing.user_id == user_id, Standing.week_id == week.id)
    ).scalar_one_or_none()
    if standing is None:
        standing = Standing(user_id=user_id, week_id=week.id, status="present")
        db.add(standing)
    else:
        standing.status = "present"
        standing.parent_marked_miss = False
    db.flush()


def nag_messages(db: Session, settings: Settings) -> list[str]:
    week = ensure_week(db, settings)
    today = local_today(settings.timezone)
    messages: list[str] = []
    open_count = db.execute(
        select(func.count()).where(
            ChoreSlot.week_id == week.id,
            ChoreSlot.status == "open",
            ChoreSlot.slot_date == today,
        )
    ).scalar_one()
    if open_count:
        messages.append(f"{open_count} open slot(s) today.")
    pending_by_name: dict[str, int] = {}
    for name, amount, kind in (
        db.execute(
            select(User.name, StarEvent.amount, StarEvent.kind).join(User).where(
                StarEvent.week_id == week.id, StarEvent.kind.in_(("award", "claim"))
            )
        ).all()
    ):
        pending_by_name[name] = pending_by_name.get(name, 0) + (amount if kind == "award" else -amount)
    for name, pending in pending_by_name.items():
        if pending > 0:
            messages.append(f"{name} has {pending} unclaimed star(s).")
    for standing in db.execute(select(Standing).where(Standing.week_id == week.id)).scalars():
        if standing.status in ("quiet", "infraction"):
            user = db.get(User, standing.user_id)
            if user:
                messages.append(f"{user.name} is {standing.status} this week.")
    if week.owe_stars:
        messages.append(f"Thursday owe is {week.owe_stars} stars.")
    return messages


def push_ntfy(settings: Settings, messages: list[str]) -> None:
    if not settings.ntfy_url or not messages:
        return
    body = "\n".join(messages)
    url = settings.ntfy_url.rstrip("/") + "/" + settings.ntfy_topic
    try:
        httpx.post(url, content=body, headers={"Title": "Chore Stars"}, timeout=5.0)
    except httpx.HTTPError:
        pass


def run_daily(db: Session, settings: Settings) -> dict[str, int | list[str]]:
    opened = open_slots(db, settings)
    expired = expire_grabs(db, settings) + expire_stale_slots(db, settings)
    standing_check(db, settings)
    week = ensure_week(db, settings)
    recalc_week_pool(db, week)
    messages = nag_messages(db, settings)
    push_ntfy(settings, messages)
    return {"opened": opened, "expired": expired, "nags": messages}
