"""Basketball crowd-snapshot persistence (Polymarket matchday intensity).

Mirrors football-model/db.py's engine/SessionLocal/Base/_now/init_db pattern
but keeps ONLY the crowd-snapshot table — basketball has no draws, so no
draw column and no drawDelta in trends. All functions swallow their own
errors and never raise out to callers (the server imports this module
lazily inside try/except, so a missing DATABASE_URL degrades gracefully).
"""

import os
from datetime import datetime, timezone
from sqlalchemy import (create_engine, String, Float, Boolean, DateTime,
                        Integer, Index)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, sessionmaker)
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def _now():
    return datetime.now(timezone.utc)


class CrowdSnapshot(Base):
    """Append-only Polymarket crowd history per fixture (matchday intensity trend)."""
    __tablename__ = "crowd_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league: Mapped[str] = mapped_column(String, nullable=False)
    home_team: Mapped[str] = mapped_column(String, nullable=False)
    away_team: Mapped[str] = mapped_column(String, nullable=False)
    match_date: Mapped[str] = mapped_column(String, nullable=False)
    home: Mapped[float | None] = mapped_column(Float)
    away: Mapped[float | None] = mapped_column(Float)
    low_volume: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (
        Index("ix_crowd_fixture_time", "league", "home_team", "away_team",
              "match_date", "snapshot_at"),
    )


def init_db():
    """Create tables if missing. Never raises."""
    try:
        Base.metadata.create_all(engine)
    except Exception:
        pass


SNAPSHOT_THROTTLE_S = 30 * 60  # max 1 snapshot per fixture per 30 min


def record_crowd_snapshot(league, home, away, match_date, crowd):
    """Append crowd snapshot; skip when latest is <30min old. Returns bool recorded."""
    if not crowd:
        return False
    try:
        with SessionLocal() as s:
            latest = (s.query(CrowdSnapshot)
                      .filter_by(league=league, home_team=home,
                                 away_team=away, match_date=match_date)
                      .order_by(CrowdSnapshot.snapshot_at.desc()).first())
            if latest and latest.snapshot_at:
                snap_at = latest.snapshot_at
                if snap_at.tzinfo is None:
                    snap_at = snap_at.replace(tzinfo=timezone.utc)
                if (_now() - snap_at).total_seconds() < SNAPSHOT_THROTTLE_S:
                    return False
            s.add(CrowdSnapshot(league=league, home_team=home, away_team=away,
                                match_date=match_date, home=crowd.get("home"),
                                away=crowd.get("away"),
                                low_volume=bool(crowd.get("low_volume"))))
            s.commit()
            return True
    except Exception:
        return False


def crowd_history(league, home, away, match_date, limit=20):
    """Oldest→newest snapshots for a fixture. [] on any failure."""
    try:
        with SessionLocal() as s:
            rows = (s.query(CrowdSnapshot)
                    .filter_by(league=league, home_team=home,
                               away_team=away, match_date=match_date)
                    .order_by(CrowdSnapshot.snapshot_at.asc())
                    .limit(limit).all())
            return [{"home": r.home, "away": r.away,
                     "low_volume": r.low_volume,
                     "at": r.snapshot_at.isoformat() if r.snapshot_at else ""}
                    for r in rows]
    except Exception:
        return []


def crowd_trend(league, home, away, match_date):
    """{homeDelta, awayDelta, since} last-minus-first; None when <2 rows."""
    hist = crowd_history(league, home, away, match_date)
    if len(hist) < 2:
        return None
    first, last = hist[0], hist[-1]
    try:
        return {"homeDelta": round(last["home"] - first["home"], 4),
                "awayDelta": round(last["away"] - first["away"], 4),
                "since": first["at"]}
    except TypeError:
        return None