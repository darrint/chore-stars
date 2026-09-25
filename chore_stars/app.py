from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

from chore_stars.auth import (
    build_oauth,
    login_user,
    logout_user,
    make_pairing_code,
    redeem_pairing_code,
    redirect_uri,
    role_from_groups,
    upsert_oidc_user,
)
from chore_stars.config import Settings, load_settings
from chore_stars.db import init_db, make_engine, make_session_factory, session_dep
from chore_stars.jobs import (
    ensure_week,
    expire_stale_slots,
    open_slots,
    recalc_week_pool,
    run_daily,
    standing_check,
)
from chore_stars.models import (
    ChoreSlot,
    ChoreTemplate,
    Grab,
    PrivilegeFlag,
    Standing,
    StarEvent,
    User,
    WallPost,
    Week,
)
from chore_stars.seed import seed_dev_users, seed_templates
from chore_stars.services import (
    active_grab,
    adjust_pool,
    backfill_wall_posts,
    claim_stars,
    finished_counts,
    grab_slot,
    leaderboard,
    live_grabs,
    payout_split,
    proof_of,
    release_grab,
    review_grab,
    standing_for,
    stars_summary,
    store_proof,
    submit_grab,
    ungrab,
)
from chore_stars.timeutil import local_today, now_tz, week_end

PACKAGE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE / "templates"))


def _user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        seed_templates(db)
        if settings.dev_auth:
            seed_dev_users(db)
        open_slots(db, settings)
        expire_stale_slots(db, settings)
        backfill_wall_posts(db, settings)
        db.commit()

    oauth = build_oauth(settings)
    get_db = session_dep(factory)
    app = FastAPI(title="Chore Stars", docs_url=None, redoc_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="chores_session",
        same_site="lax",
        https_only=settings.base_url.startswith("https://"),
        max_age=60 * 60 * 24 * 400,
    )
    app.mount("/static", StaticFiles(directory=str(PACKAGE / "static")), name="static")
    app.state.settings = settings
    app.state.engine = engine
    app.state.oauth = oauth

    def ctx(request: Request, db: Session, **extra):
        user = _user(request, db)
        week = ensure_week(db, settings)
        standing = standing_for(db, user.id, week) if user and user.role == "resident" else None
        summary = stars_summary(db, user.id, week) if user and user.role == "resident" else None
        return {
            "request": request,
            "user": user,
            "week": week,
            "week_end": week_end(week.thu_start),
            "standing": standing,
            "summary": summary,
            "today": local_today(settings.timezone),
            "dev_auth": settings.dev_auth,
            **extra,
        }

    def need_user(request: Request, db: Session) -> User:
        user = _user(request, db)
        if user is None:
            raise HTTPException(status_code=401)
        return user

    @app.exception_handler(HTTPException)
    async def http_exc(request: Request, exc: HTTPException):
        if exc.status_code == 401:
            return RedirectResponse("/login", status_code=303)
        if exc.status_code == 403:
            with factory() as db:
                return templates.TemplateResponse(
                    request,
                    "error.html",
                    ctx(request, db, message="Not allowed."),
                    status_code=403,
                )
        return HTMLResponse(exc.detail, status_code=exc.status_code)

    @app.get("/login", response_class=HTMLResponse)
    def login(request: Request, db: Session = Depends(get_db)):
        users = []
        if settings.dev_auth:
            users = db.execute(select(User).order_by(User.role, User.name)).scalars().all()
        return templates.TemplateResponse(
            request,
            "login.html",
            ctx(request, db, users=users, oidc_ready=oauth is not None),
        )

    @app.get("/auth/oidc")
    async def auth_oidc(request: Request):
        if oauth is None:
            raise HTTPException(status_code=500, detail="OIDC is not configured.")
        return await oauth.pocketid.authorize_redirect(request, redirect_uri(settings))

    @app.get("/auth/callback")
    async def auth_callback(request: Request, db: Session = Depends(get_db)):
        if oauth is None:
            raise HTTPException(status_code=500, detail="OIDC is not configured.")
        token = await oauth.pocketid.authorize_access_token(request)
        info = token.get("userinfo") or {}
        sub = info.get("sub") or token.get("sub")
        name = info.get("name") or info.get("preferred_username") or "Resident"
        groups = info.get("groups") or []
        if isinstance(groups, str):
            groups = [groups]
        role = role_from_groups(list(groups), settings)
        if not sub or role is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                ctx(request, db, message="PocketID groups must include parents or residents."),
                status_code=403,
            )
        user = upsert_oidc_user(db, sub, name, role)
        login_user(request, user)
        ensure_week(db, settings)
        return RedirectResponse("/board", status_code=303)

    @app.post("/auth/dev")
    def auth_dev(request: Request, user_id: int = Form(...), db: Session = Depends(get_db)):
        if not settings.dev_auth:
            raise HTTPException(status_code=404)
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404)
        login_user(request, user)
        return RedirectResponse("/board" if user.role != "kiosk" else "/kiosk", status_code=303)

    @app.post("/logout")
    def logout(request: Request):
        logout_user(request)
        return RedirectResponse("/login", status_code=303)

    @app.post("/pair")
    def pair(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
        try:
            user = redeem_pairing_code(db, settings, code)
        except ValueError as exc:
            return templates.TemplateResponse(
                request, "login.html", ctx(request, db, error=str(exc), users=[], oidc_ready=oauth is not None)
            )
        login_user(request, user)
        return RedirectResponse("/kiosk" if user.role == "kiosk" else "/board", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, db: Session = Depends(get_db)):
        user = _user(request, db)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if user.role == "kiosk":
            return RedirectResponse("/kiosk", status_code=303)
        return RedirectResponse("/board", status_code=303)

    def board_slots(db: Session, week: Week, slug: str | None):
        today = local_today(settings.timezone)
        q = (
            select(ChoreSlot)
            .options(selectinload(ChoreSlot.template), selectinload(ChoreSlot.grabs).selectinload(Grab.user))
            .where(ChoreSlot.week_id == week.id, ChoreSlot.status != "expired")
            .order_by(ChoreSlot.slot_date, ChoreSlot.template_id, ChoreSlot.sequence)
        )
        slots = list(db.execute(q).scalars())
        if slug:
            slots = [s for s in slots if s.template.slug == slug]
        return slots, today

    @app.get("/board", response_class=HTMLResponse)
    def board(request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        week = ensure_week(db, settings)
        slots, today = board_slots(db, week, None)
        mine = active_grab(db, user.id) if user.role == "resident" else None
        return templates.TemplateResponse(
            request, "board.html", ctx(request, db, slots=slots, mine=mine, highlight=None)
        )

    @app.get("/c/{slug}", response_class=HTMLResponse)
    def board_slug(slug: str, request: Request, db: Session = Depends(get_db)):
        need_user(request, db)
        week = ensure_week(db, settings)
        slots, today = board_slots(db, week, slug)
        return templates.TemplateResponse(
            request, "board.html", ctx(request, db, slots=slots, mine=None, highlight=slug)
        )

    @app.post("/slots/{slot_id}/grab")
    def do_grab(slot_id: int, request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        slot = db.get(ChoreSlot, slot_id)
        if slot is None:
            raise HTTPException(status_code=404)
        try:
            grab = grab_slot(db, settings, user, slot)
        except ValueError as exc:
            week = ensure_week(db, settings)
            slots, _ = board_slots(db, week, None)
            return templates.TemplateResponse(
                request, "board.html", ctx(request, db, slots=slots, mine=active_grab(db, user.id), error=str(exc))
            )
        return RedirectResponse(f"/grabs/{grab.id}", status_code=303)

    @app.get("/grabs/{grab_id}", response_class=HTMLResponse)
    def show_grab(grab_id: int, request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        grab = db.get(Grab, grab_id)
        if grab is None:
            raise HTTPException(status_code=404)
        if user.role == "resident" and grab.user_id != user.id:
            raise HTTPException(status_code=403)
        return templates.TemplateResponse(
            request,
            "grab.html",
            ctx(
                request,
                db,
                grab=grab,
                before=proof_of(grab, "before"),
                after=proof_of(grab, "after"),
                now=now_tz(settings.timezone),
            ),
        )

    @app.post("/grabs/{grab_id}/photo")
    def upload_photo(
        grab_id: int,
        request: Request,
        kind: str = Form(...),
        photo: UploadFile = File(...),
        db: Session = Depends(get_db),
    ):
        user = need_user(request, db)
        grab = db.get(Grab, grab_id)
        if grab is None or (user.role == "resident" and grab.user_id != user.id):
            raise HTTPException(status_code=404)
        week = grab.slot.week
        try:
            store_proof(db, settings, grab, week, kind, photo)
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "grab.html",
                ctx(request, db, grab=grab, before=proof_of(grab, "before"), after=proof_of(grab, "after"), error=str(exc)),
                status_code=400,
            )
        return RedirectResponse(f"/grabs/{grab.id}", status_code=303)

    @app.post("/grabs/{grab_id}/submit")
    def do_submit(grab_id: int, request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        grab = db.get(Grab, grab_id)
        if grab is None or grab.user_id != user.id:
            raise HTTPException(status_code=404)
        try:
            submit_grab(db, grab)
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "grab.html",
                ctx(request, db, grab=grab, before=proof_of(grab, "before"), after=proof_of(grab, "after"), error=str(exc)),
            )
        return RedirectResponse("/board", status_code=303)

    @app.post("/grabs/{grab_id}/release")
    def do_release(grab_id: int, request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        grab = db.get(Grab, grab_id)
        if grab is None or grab.user_id != user.id:
            raise HTTPException(status_code=404)
        try:
            release_grab(db, grab)
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "grab.html",
                ctx(request, db, grab=grab, before=proof_of(grab, "before"), after=proof_of(grab, "after"), error=str(exc)),
            )
        return RedirectResponse("/board", status_code=303)

    @app.get("/photos/{grab_id}/{kind}")
    def photo(grab_id: int, kind: str, request: Request, thumb: int = 0, db: Session = Depends(get_db)):
        user = need_user(request, db)
        grab = db.get(Grab, grab_id)
        if grab is None:
            raise HTTPException(status_code=404)
        proof = proof_of(grab, kind)
        if proof is None:
            raise HTTPException(status_code=404)
        path = proof.thumb_path if thumb and proof.thumb_path else proof.path
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/stars", response_class=HTMLResponse)
    def stars(request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        week = ensure_week(db, settings)
        events = []
        if user.role == "resident":
            events = (
                db.execute(
                    select(StarEvent)
                    .where(StarEvent.user_id == user.id, StarEvent.week_id == week.id)
                    .order_by(StarEvent.created_at.desc())
                )
                .scalars()
                .all()
            )
        return templates.TemplateResponse(request, "stars.html", ctx(request, db, events=events))

    @app.post("/stars/claim")
    def do_claim(request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        week = ensure_week(db, settings)
        try:
            claim_stars(db, user, week)
        except ValueError as exc:
            events = []
            return templates.TemplateResponse(request, "stars.html", ctx(request, db, events=events, error=str(exc)))
        return RedirectResponse("/stars", status_code=303)

    @app.get("/wall", response_class=HTMLResponse)
    def wall(request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        backfill_wall_posts(db, settings)
        posts_q = (
            select(WallPost)
            .options(
                selectinload(WallPost.user),
                selectinload(WallPost.grab).selectinload(Grab.slot).selectinload(ChoreSlot.template),
                selectinload(WallPost.grab).selectinload(Grab.proofs),
            )
            .order_by(WallPost.published_at.desc())
            .limit(60)
        )
        if user.role != "parent":
            posts_q = posts_q.where(WallPost.hidden_at.is_(None))
        posts = db.execute(posts_q).scalars().all()
        week = ensure_week(db, settings)
        standings = {
            s.user_id: s.status
            for s in db.execute(select(Standing).where(Standing.week_id == week.id)).scalars()
        }
        return templates.TemplateResponse(
            request, "wall.html", ctx(request, db, posts=posts, live=live_grabs(db), standings=standings)
        )

    @app.get("/boards", response_class=HTMLResponse)
    def boards(request: Request, db: Session = Depends(get_db)):
        need_user(request, db)
        week = ensure_week(db, settings)
        week_standings = list(
            db.execute(
                select(Standing).options(selectinload(Standing.user)).where(Standing.week_id == week.id)
            ).scalars()
        )
        status_rank = {"present": 0, "quiet": 1, "infraction": 2}
        week_standings.sort(key=lambda s: (status_rank.get(s.status, 9), s.user.name.lower()))
        return templates.TemplateResponse(
            request,
            "boards.html",
            ctx(
                request,
                db,
                claimed_week=leaderboard(db, week, "claimed"),
                awarded_week=leaderboard(db, week, "awarded"),
                claimed_all=leaderboard(db, None, "claimed"),
                awarded_all=leaderboard(db, None, "awarded"),
                finished_week=finished_counts(db, week),
                finished_all=finished_counts(db, None),
                week_standings=week_standings,
            ),
        )

    @app.get("/kiosk", response_class=HTMLResponse)
    def kiosk(request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        week = ensure_week(db, settings)
        backfill_wall_posts(db, settings)
        slots, _ = board_slots(db, week, None)
        posts = (
            db.execute(
                select(WallPost)
                .options(
                    selectinload(WallPost.user),
                    selectinload(WallPost.grab).selectinload(Grab.slot).selectinload(ChoreSlot.template),
                    selectinload(WallPost.grab).selectinload(Grab.proofs),
                )
                .where(WallPost.hidden_at.is_(None))
                .order_by(WallPost.published_at.desc())
                .limit(12)
            )
            .scalars()
            .all()
        )
        standings = list(
            db.execute(select(Standing).options(selectinload(Standing.user)).where(Standing.week_id == week.id)).scalars()
        )
        return templates.TemplateResponse(
            request,
            "kiosk.html",
            ctx(request, db, slots=slots, posts=posts, live=live_grabs(db), standings=standings, kiosk=user),
        )

    @app.get("/parent", response_class=HTMLResponse)
    def parent_home(request: Request, payout: str = "", db: Session = Depends(get_db)):
        user = need_user(request, db)
        if user.role != "parent":
            raise HTTPException(status_code=403)
        week = ensure_week(db, settings)
        payout_shares = None
        payout_error = None
        if payout.strip():
            try:
                amount = Decimal(payout.strip())
                if amount < 0 or amount.as_tuple().exponent < -2:
                    raise ValueError("Use dollars and cents.")
                payout_shares = payout_split(db, week, int(amount * 100))
            except (InvalidOperation, ValueError) as exc:
                payout_error = "Use dollars and cents." if isinstance(exc, InvalidOperation) else str(exc)
        pending = (
            db.execute(
                select(Grab)
                .options(selectinload(Grab.user), selectinload(Grab.slot).selectinload(ChoreSlot.template), selectinload(Grab.proofs))
                .join(ChoreSlot)
                .where(ChoreSlot.status == "submitted", Grab.status == "active")
                .order_by(Grab.submitted_at.desc())
            )
            .scalars()
            .all()
        )
        standings = list(
            db.execute(select(Standing).options(selectinload(Standing.user)).where(Standing.week_id == week.id)).scalars()
        )
        open_slots_list = (
            db.execute(
                select(ChoreSlot)
                .options(selectinload(ChoreSlot.template))
                .where(ChoreSlot.week_id == week.id, ChoreSlot.status == "open")
                .order_by(ChoreSlot.slot_date, ChoreSlot.template_id)
            )
            .scalars()
            .all()
        )
        residents = db.execute(select(User).where(User.role == "resident").order_by(User.name)).scalars().all()
        return templates.TemplateResponse(
            request,
            "parent.html",
            ctx(
                request,
                db,
                pending=pending,
                live=live_grabs(db),
                standings=standings,
                open_slots_list=open_slots_list,
                residents=residents,
                payout=payout,
                payout_shares=payout_shares,
                payout_error=payout_error,
            ),
        )

    @app.post("/parent/grabs/{grab_id}/ungrab")
    def parent_ungrab(grab_id: int, request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        if user.role != "parent":
            raise HTTPException(status_code=403)
        grab = db.get(Grab, grab_id)
        if grab is None:
            raise HTTPException(status_code=404)
        try:
            ungrab(db, grab)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse("/wall", status_code=303)

    @app.get("/parent/review/{grab_id}", response_class=HTMLResponse)
    def parent_review(grab_id: int, request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        if user.role != "parent":
            raise HTTPException(status_code=403)
        grab = db.get(Grab, grab_id)
        if grab is None:
            raise HTTPException(status_code=404)
        return templates.TemplateResponse(
            request,
            "review.html",
            ctx(request, db, grab=grab, before=proof_of(grab, "before"), after=proof_of(grab, "after")),
        )

    @app.post("/parent/review/{grab_id}")
    def parent_review_post(
        grab_id: int,
        request: Request,
        action: str = Form(...),
        stars: str = Form(""),
        note: str = Form(""),
        db: Session = Depends(get_db),
    ):
        user = need_user(request, db)
        if user.role != "parent":
            raise HTTPException(status_code=403)
        grab = db.get(Grab, grab_id)
        if grab is None:
            raise HTTPException(status_code=404)
        amount = int(stars) if stars.strip() else None
        try:
            review_grab(db, settings, user, grab, action, amount, note)
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "review.html",
                ctx(
                    request,
                    db,
                    grab=grab,
                    before=proof_of(grab, "before"),
                    after=proof_of(grab, "after"),
                    error=str(exc),
                ),
            )
        return RedirectResponse("/parent", status_code=303)

    @app.post("/parent/slots/{slot_id}/stars")
    def edit_stars(slot_id: int, request: Request, advertised_stars: int = Form(...), db: Session = Depends(get_db)):
        user = need_user(request, db)
        if user.role != "parent":
            raise HTTPException(status_code=403)
        slot = db.get(ChoreSlot, slot_id)
        if slot is None or slot.status != "open":
            raise HTTPException(status_code=400, detail="Only open slots.")
        slot.advertised_stars = advertised_stars
        return RedirectResponse("/parent", status_code=303)

    @app.post("/parent/pool/adjust")
    def pool_adjust(request: Request, amount: int = Form(...), db: Session = Depends(get_db)):
        user = need_user(request, db)
        if user.role != "parent":
            raise HTTPException(status_code=403)
        week = ensure_week(db, settings)
        adjust_pool(db, week, amount)
        db.add(StarEvent(user_id=user.id, week_id=week.id, kind="adjust", amount=amount))
        return RedirectResponse("/parent", status_code=303)

    @app.post("/parent/roster/{user_id}")
    def roster_action(
        user_id: int,
        request: Request,
        action: str = Form(...),
        db: Session = Depends(get_db),
    ):
        parent = need_user(request, db)
        if parent.role != "parent":
            raise HTTPException(status_code=403)
        week = ensure_week(db, settings)
        standing = standing_for(db, user_id, week)
        if standing is None:
            standing = Standing(user_id=user_id, week_id=week.id, status="quiet")
            db.add(standing)
            db.flush()
        if action == "miss":
            standing.status = "infraction"
            standing.parent_marked_miss = True
            standing.misses = max(standing.misses, 1)
        elif action == "clear":
            standing.parent_marked_miss = False
            standing.cleared_at = now_tz(settings.timezone)
            summary = stars_summary(db, user_id, week)
            standing.status = "present" if summary["awarded"] else "quiet"
        elif action == "revoke":
            flag = PrivilegeFlag(user_id=user_id, day=local_today(settings.timezone), revoked=True)
            db.add(flag)
        elif action == "restore":
            flag = PrivilegeFlag(user_id=user_id, day=local_today(settings.timezone), revoked=False)
            db.add(flag)
        return RedirectResponse("/parent", status_code=303)

    @app.post("/parent/wall/{post_id}/hide")
    def hide_wall(post_id: int, request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        if user.role != "parent":
            raise HTTPException(status_code=403)
        post = db.get(WallPost, post_id)
        if post:
            post.hidden_at = now_tz(settings.timezone)
        return RedirectResponse("/wall", status_code=303)

    @app.post("/parent/wall/{post_id}/unhide")
    def unhide_wall(post_id: int, request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        if user.role != "parent":
            raise HTTPException(status_code=403)
        post = db.get(WallPost, post_id)
        if post:
            post.hidden_at = None
        return RedirectResponse("/wall", status_code=303)

    @app.post("/parent/pair")
    def parent_pair(
        request: Request,
        role: str = Form("kiosk"),
        user_id: str = Form(""),
        db: Session = Depends(get_db),
    ):
        user = need_user(request, db)
        if user.role != "parent":
            raise HTTPException(status_code=403)
        target = int(user_id) if user_id.strip() else None
        code = make_pairing_code(db, settings, user, role, target)
        week = ensure_week(db, settings)
        return templates.TemplateResponse(request, "pair.html", ctx(request, db, code=code))

    @app.get("/parent/qr", response_class=HTMLResponse)
    def qr_sheet(request: Request, db: Session = Depends(get_db)):
        user = need_user(request, db)
        if user.role != "parent":
            raise HTTPException(status_code=403)
        import io

        import qrcode
        import qrcode.image.svg

        board_url = settings.base_url.rstrip("/") + "/board"
        img = qrcode.make(board_url, image_factory=qrcode.image.svg.SvgPathImage)
        buf = io.BytesIO()
        img.save(buf)
        return templates.TemplateResponse(
            request, "qr.html", ctx(request, db, url=board_url, svg=buf.getvalue().decode("utf-8"))
        )

    @app.get("/manifest.json")
    def manifest():
        return FileResponse(PACKAGE / "static" / "manifest.json", media_type="application/manifest+json")

    @app.get("/sw.js")
    def sw():
        return FileResponse(PACKAGE / "static" / "sw.js", media_type="text/javascript")

    @app.post("/internal/job")
    def internal_job(request: Request, db: Session = Depends(get_db)):
        if request.client and request.client.host not in ("127.0.0.1", "::1"):
            raise HTTPException(status_code=403)
        return run_daily(db, settings)

    return app


def run_job(name: str, settings: Settings | None = None) -> dict:
    settings = settings or load_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        seed_templates(db)
        if name == "open-slots":
            result = {"opened": open_slots(db, settings)}
        elif name == "standing":
            standing_check(db, settings)
            result = {"ok": True}
        else:
            result = run_daily(db, settings)
        db.commit()
        return result
