from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from chore_stars.config import Settings
from chore_stars.models import User


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path}/chores.db",
        photo_dir=str(tmp_path / "photos"),
        session_secret="test-secret",
        base_url="http://test",
        dev_auth=True,
        grab_minutes=45,
        star_budget=100,
        timezone="America/Indiana/Indianapolis",
    )


@pytest.fixture
def app(settings: Settings):
    from chore_stars.app import create_app

    return create_app(settings)


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def user_named(app, name: str) -> User:
    with Session(app.state.engine) as db:
        return db.execute(select(User).where(User.name == name)).scalar_one()


def login(client: TestClient, app, name: str) -> None:
    person = user_named(app, name)
    response = client.post("/auth/dev", data={"user_id": person.id}, follow_redirects=False)
    assert response.status_code == 303


def jpeg_bytes() -> BytesIO:
    buf = BytesIO()
    Image.new("RGB", (48, 48), "orange").save(buf, "JPEG")
    buf.seek(0)
    return buf
