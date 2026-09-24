from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chore_stars.config import Settings
from chore_stars.jobs import ensure_week, mark_present, recalc_week_pool
from chore_stars.models import (
    ChoreSlot,
    Grab,
    Proof,
    Review,
    Standing,
    StarEvent,
    User,
    WallPost,
    Week,
)
from chore_stars.photos import save_jpeg, week_dir
from chore_stars.timeutil import now_tz


ACTIVE_GRAB = ("active",)
BUSY_SLOT = ("grabbed", "submitted")


def current_week(db: Session, settings: Settings) -> Week:
    return ensure_week(db, settings)


def standing_for(db: Session, user_id: int, week: Week) -> Standing | None:
    return db.execute(
        select(Standing).where(Standing.user_id == user_id, Standing.week_id == week.id)
    ).scalar_one_or_none()


def stars_summary(db: Session, user_id: int, week: Week) -> dict[str, int]:
    rows = db.execute(
        select(StarEvent.kind, func.coalesce(func.sum(StarEvent.amount), 0)).where(
            StarEvent.user_id == user_id, StarEvent.week_id == week.id
        ).group_by(StarEvent.kind)
    ).all()
    by_kind = {kind: int(total) for kind, total in rows}
    awarded = by_kind.get("award", 0)
    claimed = by_kind.get("claim", 0)
    return {
        "awarded": awarded,
        "claimed": claimed,
        "unclaimed": max(0, awarded - claimed),
    }


def active_grab(db: Session, user_id: int) -> Grab | None:
    return db.execute(
        select(Grab).where(Grab.user_id == user_id, Grab.status == "active")
    ).scalar_one_or_none()


def grab_slot(db: Session, settings: Settings, user: User, slot: ChoreSlot) -> Grab:
    if user.role != "resident":
        raise ValueError("Only residents can grab slots.")
    if slot.status != "open":
        raise ValueError("That slot is not open.")
    existing = active_grab(db, user.id)
    if existing is not None:
        raise ValueError("You already have an active grab.")
    now = now_tz(settings.timezone)
    grab = Grab(
        slot_id=slot.id,
        user_id=user.id,
        grabbed_at=now,
        expires_at=now + timedelta(minutes=settings.grab_minutes),
        locked_stars=slot.advertised_stars,
        status="active",
    )
    slot.status = "grabbed"
    db.add(grab)
    db.flush()
    return grab


def proof_of(grab: Grab, kind: str) -> Proof | None:
    for proof in grab.proofs:
        if proof.kind == kind:
            return proof
    return None


def store_proof(db: Session, settings: Settings, grab: Grab, week: Week, kind: str, upload) -> Proof:
    if kind not in ("before", "after"):
        raise ValueError("Photo must be before or after.")
    if grab.status != "active":
        raise ValueError("Grab is not active.")
    root = Path(settings.photo_dir)
    folder = week_dir(root, week.thu_start.isoformat(), grab.id)
    dest = folder / f"{kind}.jpg"
    thumb = folder / f"{kind}-thumb.jpg"
    save_jpeg(upload, dest, thumb)
    proof = proof_of(grab, kind)
    rel = str(dest)
    thumb_rel = str(thumb)
    if proof is None:
        proof = Proof(grab_id=grab.id, kind=kind, path=rel, thumb_path=thumb_rel)
        db.add(proof)
    else:
        proof.path = rel
        proof.thumb_path = thumb_rel
    db.flush()
    return proof


def submit_grab(db: Session, grab: Grab) -> None:
    if grab.status != "active":
        raise ValueError("Grab is not active.")
    if proof_of(grab, "before") is None or proof_of(grab, "after") is None:
        raise ValueError("Need before and after photos.")
    grab.submitted_at = now_tz("UTC")
    grab.slot.status = "submitted"
    db.flush()


def release_grab(db: Session, grab: Grab) -> None:
    if grab.submitted_at is not None:
        raise ValueError("Already submitted.")
    grab.status = "released"
    if grab.slot.status == "grabbed":
        grab.slot.status = "open"
    db.flush()


def review_grab(
    db: Session,
    settings: Settings,
    parent: User,
    grab: Grab,
    action: str,
    stars: int | None,
    note: str | None,
) -> Review:
    if action not in ("award", "reject", "send_back"):
        raise ValueError("Unknown review action.")
    if grab.slot.status != "submitted" and action != "send_back":
        if grab.slot.status not in ("submitted", "grabbed"):
            raise ValueError("Nothing to review.")
    review = Review(
        grab_id=grab.id,
        parent_id=parent.id,
        awarded_stars=stars if action == "award" else None,
        action=action,
        note=note or None,
    )
    db.add(review)
    slot = grab.slot
    week = slot.week
    if action == "award":
        if stars is None or stars < 0:
            raise ValueError("Award needs a star count.")
        grab.status = "awarded"
        slot.status = "awarded"
        db.add(
            StarEvent(
                user_id=grab.user_id,
                week_id=week.id,
                kind="award",
                amount=stars,
                grab_id=grab.id,
            )
        )
        db.add(WallPost(grab_id=grab.id, user_id=grab.user_id, published_at=now_tz(settings.timezone)))
        mark_present(db, grab.user_id, week)
        recalc_week_pool(db, week)
    elif action == "reject":
        grab.status = "rejected"
        slot.status = "open"
    elif action == "send_back":
        grab.status = "active"
        grab.submitted_at = None
        slot.status = "grabbed"
        grab.expires_at = now_tz(settings.timezone) + timedelta(minutes=settings.grab_minutes)
    db.flush()
    return review


def claim_stars(db: Session, user: User, week: Week) -> int:
    summary = stars_summary(db, user.id, week)
    pending = summary["unclaimed"]
    if pending <= 0:
        raise ValueError("Nothing to claim.")
    db.add(
        StarEvent(
            user_id=user.id,
            week_id=week.id,
            kind="claim",
            amount=pending,
        )
    )
    db.flush()
    return pending


def adjust_pool(db: Session, week: Week, amount: int) -> None:
    week.pool_adjust += amount
    recalc_week_pool(db, week)


def leaderboard(db: Session, week: Week | None, kind: str) -> list[dict]:
    query = (
        select(User.id, User.name, func.coalesce(func.sum(StarEvent.amount), 0).label("total"))
        .join(StarEvent, StarEvent.user_id == User.id)
        .where(User.role == "resident")
    )
    if week is not None:
        query = query.where(StarEvent.week_id == week.id)
    if kind == "claimed":
        query = query.where(StarEvent.kind == "claim")
    elif kind == "awarded":
        query = query.where(StarEvent.kind == "award")
    else:
        query = query.where(StarEvent.kind == "award")
    query = query.group_by(User.id, User.name).order_by(func.coalesce(func.sum(StarEvent.amount), 0).desc())
    rows = db.execute(query).all()
    return [{"user_id": r.id, "name": r.name, "total": int(r.total)} for r in rows]


def finished_counts(db: Session, week: Week | None) -> list[dict]:
    query = (
        select(User.id, User.name, func.count(Grab.id).label("total"))
        .join(Grab, Grab.user_id == User.id)
        .where(User.role == "resident", Grab.status == "awarded")
    )
    if week is not None:
        query = query.join(ChoreSlot, ChoreSlot.id == Grab.slot_id).where(ChoreSlot.week_id == week.id)
    query = query.group_by(User.id, User.name).order_by(func.count(Grab.id).desc())
    return [{"user_id": r.id, "name": r.name, "total": int(r.total)} for r in db.execute(query).all()]
