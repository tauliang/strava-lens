"""Immutable normalized records and durable import state."""

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Record(Base):
    __tablename__ = "records"
    event_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), index=True)
    activity_id: Mapped[str | None] = mapped_column(String(100), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class Snapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[float] = mapped_column(Float)
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)


class SnapshotRecord(Base):
    __tablename__ = "snapshot_records"
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("records.event_id"), primary_key=True
    )


class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    archive_path: Mapped[str] = mapped_column(Text)
    archive_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(36))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(100))
    config: Mapped[dict] = mapped_column(JSON)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
