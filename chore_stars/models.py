from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pocket_id_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    grabs: Mapped[list["Grab"]] = relationship(back_populates="user")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    push_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PairingCode(Base):
    __tablename__ = "pairing_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True)
    role: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChoreTemplate(Base):
    __tablename__ = "chore_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    default_stars: Mapped[int] = mapped_column(Integer)
    cap: Mapped[int] = mapped_column(Integer)
    period: Mapped[str] = mapped_column(String(10))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Week(Base):
    __tablename__ = "weeks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thu_start: Mapped[date] = mapped_column(Date, unique=True)
    star_budget: Mapped[int] = mapped_column(Integer, default=100)
    awarded_total: Mapped[int] = mapped_column(Integer, default=0)
    owe_stars: Mapped[int] = mapped_column(Integer, default=0)
    pool_adjust: Mapped[int] = mapped_column(Integer, default=0)


class ChoreSlot(Base):
    __tablename__ = "chore_slots"
    __table_args__ = (UniqueConstraint("week_id", "template_id", "slot_date", "sequence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("weeks.id"))
    template_id: Mapped[int] = mapped_column(ForeignKey("chore_templates.id"))
    slot_date: Mapped[date] = mapped_column(Date)
    advertised_stars: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="open")
    sequence: Mapped[int] = mapped_column(Integer, default=1)

    template: Mapped[ChoreTemplate] = relationship()
    week: Mapped[Week] = relationship()
    grabs: Mapped[list["Grab"]] = relationship(back_populates="slot")


class Grab(Base):
    __tablename__ = "grabs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("chore_slots.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    grabbed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_stars: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="active")

    slot: Mapped[ChoreSlot] = relationship(back_populates="grabs")
    user: Mapped[User] = relationship(back_populates="grabs")
    proofs: Mapped[list["Proof"]] = relationship(back_populates="grab")
    reviews: Mapped[list["Review"]] = relationship(back_populates="grab")


class Proof(Base):
    __tablename__ = "proofs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grab_id: Mapped[int] = mapped_column(ForeignKey("grabs.id"))
    kind: Mapped[str] = mapped_column(String(20))
    path: Mapped[str] = mapped_column(String(500))
    thumb_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    grab: Mapped[Grab] = relationship(back_populates="proofs")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grab_id: Mapped[int] = mapped_column(ForeignKey("grabs.id"))
    parent_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    awarded_stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    grab: Mapped[Grab] = relationship(back_populates="reviews")
    parent: Mapped[User] = relationship()


class StarEvent(Base):
    __tablename__ = "star_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    week_id: Mapped[int] = mapped_column(ForeignKey("weeks.id"))
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer)
    grab_id: Mapped[int | None] = mapped_column(ForeignKey("grabs.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped[User] = relationship()
    week: Mapped[Week] = relationship()


class Standing(Base):
    __tablename__ = "standings"
    __table_args__ = (UniqueConstraint("user_id", "week_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    week_id: Mapped[int] = mapped_column(ForeignKey("weeks.id"))
    status: Mapped[str] = mapped_column(String(20), default="quiet")
    misses: Mapped[int] = mapped_column(Integer, default=0)
    parent_marked_miss: Mapped[bool] = mapped_column(Boolean, default=False)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship()
    week: Mapped[Week] = relationship()


class PrivilegeFlag(Base):
    __tablename__ = "privilege_flags"
    __table_args__ = (UniqueConstraint("user_id", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    day: Mapped[date] = mapped_column(Date)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class WallPost(Base):
    __tablename__ = "wall_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grab_id: Mapped[int] = mapped_column(ForeignKey("grabs.id"), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    grab: Mapped[Grab] = relationship()
    user: Mapped[User] = relationship()
