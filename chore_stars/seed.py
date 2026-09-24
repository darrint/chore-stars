from sqlalchemy.orm import Session

from chore_stars.models import ChoreSlot, ChoreTemplate, User

TEMPLATES = [
    ("load-dishwasher", "Load dishwasher", 1, 2, "day"),
    ("sweep-north", "Sweep north", 1, 1, "day"),
    ("sweep-south", "Sweep south", 1, 1, "day"),
    ("vacuum-rugs", "Vacuum rugs", 2, 1, "day"),
    ("load-laundry", "Load laundry", 1, 4, "day"),
    ("sort-laundry", "Sort and distribute clean laundry", 2, 1, "day"),
    ("mow-lawn", "Mow lawn", 8, 1, "week"),
    ("edge-prune-blow", "Edge, prune, blow", 8, 1, "week"),
]


def week_advertised_capacity() -> int:
    total = 0
    for _slug, _title, stars, cap, period in TEMPLATES:
        total += stars * cap * (7 if period == "day" else 1)
    return total

DEV_USERS = [
    ("dad", "Dad", "parent"),
    ("mom", "Mom", "parent"),
    ("alex", "Alex", "resident"),
    ("sam", "Sam", "resident"),
    ("riley", "Riley", "resident"),
    ("kitchen", "Kitchen", "kiosk"),
]


def seed_templates(db: Session) -> None:
    by_slug = {t.slug: t for t in db.query(ChoreTemplate).all()}
    for slug, title, stars, cap, period in TEMPLATES:
        template = by_slug.get(slug)
        if template is None:
            db.add(
                ChoreTemplate(
                    slug=slug,
                    title=title,
                    default_stars=stars,
                    cap=cap,
                    period=period,
                    active=True,
                )
            )
            continue
        changed = template.default_stars != stars
        template.title = title
        template.default_stars = stars
        template.cap = cap
        template.period = period
        if changed:
            for slot in db.query(ChoreSlot).filter(
                ChoreSlot.template_id == template.id,
                ChoreSlot.status == "open",
            ):
                slot.advertised_stars = stars
    db.flush()


def seed_dev_users(db: Session) -> None:
    existing = {u.pocket_id_sub for u in db.query(User).all()}
    for sub, name, role in DEV_USERS:
        key = f"dev:{sub}"
        if key not in existing:
            db.add(User(pocket_id_sub=key, name=name, role=role))
    db.flush()
