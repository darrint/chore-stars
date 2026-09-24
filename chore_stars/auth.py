import secrets
from datetime import timedelta
from typing import Annotated
from urllib.parse import urljoin

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.config import Config

from chore_stars.config import Settings
from chore_stars.models import PairingCode, User
from chore_stars.timeutil import now_tz


def build_oauth(settings: Settings) -> OAuth | None:
    if not (settings.oidc_issuer and settings.oidc_client_id and settings.oidc_client_secret):
        return None
    config = Config(
        environ={
            "CHORES_OIDC_CLIENT_ID": settings.oidc_client_id,
            "CHORES_OIDC_CLIENT_SECRET": settings.oidc_client_secret,
        }
    )
    oauth = OAuth(config)
    oauth.register(
        name="pocketid",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=urljoin(settings.oidc_issuer.rstrip("/") + "/", ".well-known/openid-configuration"),
        client_kwargs={"scope": "openid profile email groups"},
    )
    return oauth


def redirect_uri(settings: Settings) -> str:
    return settings.oidc_redirect_uri or (settings.base_url.rstrip("/") + "/auth/callback")


def role_from_groups(groups: list[str], settings: Settings) -> str | None:
    lowered = {g.lower() for g in groups}
    if settings.parents_group.lower() in lowered:
        return "parent"
    if settings.residents_group.lower() in lowered:
        return "resident"
    return None


def upsert_oidc_user(db: Session, sub: str, name: str, role: str) -> User:
    user = db.execute(select(User).where(User.pocket_id_sub == sub)).scalar_one_or_none()
    if user is None:
        user = User(pocket_id_sub=sub, name=name, role=role)
        db.add(user)
        db.flush()
    else:
        user.name = name or user.name
        user.role = role
    return user


def login_user(request: Request, user: User) -> None:
    request.session["user_id"] = user.id
    request.session["role"] = user.role
    request.session["name"] = user.name


def logout_user(request: Request) -> None:
    request.session.clear()


def current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_user(request: Request, db: Session) -> User:
    user = current_user(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in first.")
    return user


def require_parent(user: User) -> User:
    if user.role != "parent":
        raise HTTPException(status_code=403, detail="Parents only.")
    return user


def require_resident(user: User) -> User:
    if user.role != "resident":
        raise HTTPException(status_code=403, detail="Residents only.")
    return user


def make_pairing_code(db: Session, settings: Settings, creator: User, role: str, user_id: int | None) -> PairingCode:
    code = f"{secrets.randbelow(1000000):06d}"
    row = PairingCode(
        code=code,
        role=role,
        user_id=user_id,
        created_by=creator.id,
        expires_at=now_tz(settings.timezone) + timedelta(minutes=20),
    )
    db.add(row)
    db.flush()
    return row


def redeem_pairing_code(db: Session, settings: Settings, code: str) -> User:
    row = db.execute(select(PairingCode).where(PairingCode.code == code.strip())).scalar_one_or_none()
    now = now_tz(settings.timezone)
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise ValueError("That code is dead.")
    if row.user_id:
        user = db.get(User, row.user_id)
        if user is None:
            raise ValueError("User gone.")
    else:
        user = User(pocket_id_sub=f"pair:{row.code}", name="Kitchen", role=row.role)
        db.add(user)
        db.flush()
        row.user_id = user.id
    row.used_at = now
    db.flush()
    return user
