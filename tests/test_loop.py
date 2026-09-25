from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from chore_stars.models import ChoreSlot, ChoreTemplate, Grab, StarEvent, User, WallPost, Week
from chore_stars.seed import seed_templates
from tests.conftest import jpeg_bytes, login, user_named


def test_login_and_board(client, app):
    login(client, app, "Alex")
    page = client.get("/board")
    assert page.status_code == 200
    assert "Load dishwasher" in page.text
    assert "Grab" in page.text


def test_one_active_grab_and_award_claim_owe(client, app):
    login(client, app, "Alex")
    board = client.get("/board")
    assert board.status_code == 200
    with Session(app.state.engine) as db:
        slot = db.execute(select(ChoreSlot).where(ChoreSlot.status == "open")).scalars().first()
        assert slot is not None
        slot_id = slot.id
        other = db.execute(
            select(ChoreSlot).where(ChoreSlot.status == "open", ChoreSlot.id != slot_id)
        ).scalars().first()
        other_id = other.id

    grabbed = client.post(f"/slots/{slot_id}/grab", follow_redirects=False)
    assert grabbed.status_code == 303
    grab_url = grabbed.headers["location"]

    again = client.post(f"/slots/{other_id}/grab", follow_redirects=True)
    assert "already have an active grab" in again.text

    grab_id = int(grab_url.rsplit("/", 1)[-1])
    for kind in ("before", "after"):
        files = {"photo": ("p.jpg", jpeg_bytes(), "image/jpeg")}
        up = client.post(f"/grabs/{grab_id}/photo", data={"kind": kind}, files=files, follow_redirects=False)
        assert up.status_code == 303
    submitted = client.post(f"/grabs/{grab_id}/submit", follow_redirects=False)
    assert submitted.status_code == 303

    login(client, app, "Dad")
    review = client.post(
        f"/parent/review/{grab_id}",
        data={"action": "award", "stars": "112", "note": "hot week"},
        follow_redirects=False,
    )
    assert review.status_code == 303
    parent = client.get("/parent")
    assert "owe 12" in parent.text

    login(client, app, "Alex")
    stars = client.get("/stars")
    assert "Ready to claim" in stars.text
    claimed = client.post("/stars/claim", follow_redirects=True)
    assert claimed.status_code == 200
    assert "Claimed" in claimed.text
    wall = client.get("/wall")
    assert "Alex" in wall.text


def test_wall_shows_grab_and_parent_ungrab(client, app):
    login(client, app, "Alex")
    with Session(app.state.engine) as db:
        slot = db.execute(select(ChoreSlot).where(ChoreSlot.status == "open")).scalars().first()
        slot_id = slot.id
    client.post(f"/slots/{slot_id}/grab", follow_redirects=False)
    wall = client.get("/wall")
    assert "Alex" in wall.text
    assert "grabbed" in wall.text

    login(client, app, "Dad")
    parent = client.get("/parent")
    assert "Ungrab" in parent.text
    with Session(app.state.engine) as db:
        grab = db.execute(select(Grab).where(Grab.status == "active")).scalar_one()
        grab_id = grab.id
    gone = client.post(f"/parent/grabs/{grab_id}/ungrab", follow_redirects=False)
    assert gone.status_code == 303
    with Session(app.state.engine) as db:
        grab = db.get(Grab, grab_id)
        assert grab.status == "released"
        assert grab.slot.status == "open"


def test_wall_backfills_missing_posts(client, app):
    login(client, app, "Alex")
    with Session(app.state.engine) as db:
        slot = db.execute(select(ChoreSlot).where(ChoreSlot.status == "open")).scalars().first()
        slot_id = slot.id
    grab_url = client.post(f"/slots/{slot_id}/grab", follow_redirects=False).headers["location"]
    page = client.get(grab_url)
    assert "Take photo" not in page.text
    assert "Choose photo" not in page.text
    assert "Open camera" in page.text
    assert "Use this shot" in page.text
    grab_id = int(grab_url.rsplit("/", 1)[-1])
    for kind in ("before", "after"):
        client.post(
            f"/grabs/{grab_id}/photo",
            data={"kind": kind},
            files={"photo": ("p.jpg", jpeg_bytes(), "image/jpeg")},
            follow_redirects=False,
        )
    client.post(f"/grabs/{grab_id}/submit", follow_redirects=False)
    login(client, app, "Dad")
    client.post(f"/parent/review/{grab_id}", data={"action": "award", "stars": "3", "note": ""}, follow_redirects=False)
    with Session(app.state.engine) as db:
        db.query(WallPost).delete()
        db.commit()
    wall = client.get("/wall")
    assert "Alex" in wall.text


def test_board_lists_trash_and_split_outdoor(client, app):
    login(client, app, "Alex")
    page = client.get("/board")
    assert "Take out trash" in page.text
    assert "Burn boxes" in page.text
    assert "Outdoor weeding" in page.text
    assert "Edge, prune, blow" not in page.text


def test_retired_combo_drops_open_slots(app):
    with Session(app.state.engine) as db:
        old = ChoreTemplate(
            slug="edge-prune-blow",
            title="Edge, prune, blow",
            default_stars=6,
            cap=1,
            period="week",
            active=True,
        )
        db.add(old)
        db.flush()
        week = db.execute(select(Week)).scalar_one()
        db.add(
            ChoreSlot(
                week_id=week.id,
                template_id=old.id,
                slot_date=date(2026, 9, 24),
                advertised_stars=6,
                status="open",
                sequence=1,
            )
        )
        db.add(
            ChoreSlot(
                week_id=week.id,
                template_id=old.id,
                slot_date=date(2026, 9, 24),
                advertised_stars=6,
                status="awarded",
                sequence=2,
            )
        )
        db.commit()
        seed_templates(db)
        db.commit()
        old = db.execute(select(ChoreTemplate).where(ChoreTemplate.slug == "edge-prune-blow")).scalar_one()
        assert old.active is False
        left = db.execute(select(ChoreSlot).where(ChoreSlot.template_id == old.id)).scalars().all()
        assert [slot.status for slot in left] == ["awarded"]


def test_payout_split_uses_awarded_stars(client, app):
    login(client, app, "Dad")
    empty = client.get("/parent?payout=40")
    assert "No awarded stars this week." in empty.text
    with Session(app.state.engine) as db:
        week = db.execute(select(Week)).scalar_one()
        alex = db.execute(select(User).where(User.name == "Alex")).scalar_one()
        sam = db.execute(select(User).where(User.name == "Sam")).scalar_one()
        db.add(StarEvent(user_id=alex.id, week_id=week.id, kind="award", amount=3))
        db.add(StarEvent(user_id=sam.id, week_id=week.id, kind="award", amount=1))
        db.commit()
    page = client.get("/parent?payout=10")
    assert "$7.50" in page.text
    assert "$2.50" in page.text
    odd = client.get("/parent?payout=0.01")
    assert "$0.01" in odd.text
    assert odd.text.count("$0.00") == 1


def test_parents_only(client, app):
    login(client, app, "Alex")
    denied = client.get("/parent", follow_redirects=False)
    assert denied.status_code in (303, 403)
