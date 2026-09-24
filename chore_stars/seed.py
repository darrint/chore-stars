from sqlalchemy.orm import Session

from chore_stars.models import ChoreTemplate, User

TEMPLATES = [
    ("load-dishwasher", "Load dishwasher", 3, 2, "day"),
    ("sweep-north", "Sweep north", 4, 1, "day"),
    ("sweep-south", "Sweep south", 4, 1, "day"),
    ("vacuum-rugs", "Vacuum rugs", 5, 1, "day"),
    ("load-laundry", "Load laundry", 3, 4, "day"),
    ("sort-laundry", "Sort and distribute clean laundry", 8, 1, "day"),
    ("mow-lawn", "Mow lawn", 12, 1, "week"),
    ("edge-prune-blow", "Edge, prune, blow", 15, 1, "week"),
]

DEV_USERS = [
    ("dad", "Dad", "parent"),
    ("mom", "Mom", "parent"),
    ("alex", "Alex", "resident"),
    ("sam", "Sam", "resident"),
    ("riley", "Riley", "resident"),
    ("kitchen", "Kitchen", "kiosk"),
]


def seed_templates(db: Session) -> None:
    existing = {t.slug for t in db.query(ChoreTemplate).all()}
    for slug, title, stars, cap, period in TEMPLATES:
        if slug not in existing:
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
    db.flush()


def seed_dev_users(db: Session) -> None:
    existing = {u.pocket_id_sub for u in db.query(User).all()}
    for sub, name, role in DEV_USERS:
        key = f"dev:{sub}"
        if key not in existing:
            db.add(User(pocket_id_sub=key, name=name, role=role))
    db.flush()
