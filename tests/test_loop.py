from sqlalchemy import select
from sqlalchemy.orm import Session

from chore_stars.models import ChoreSlot, Grab, User, Week
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


def test_parents_only(client, app):
    login(client, app, "Alex")
    denied = client.get("/parent", follow_redirects=False)
    assert denied.status_code in (303, 403)
