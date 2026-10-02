from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now() -> datetime:
    return datetime.now(timezone.utc)


def identity() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = 'product_variants'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    category: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(160))
    version: Mapped[str] = mapped_column(String(160))
    data: Mapped[dict] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String(12), index=True)
    reviewed: Mapped[str] = mapped_column(String(20), default='demo')
    price_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Visitor(Base):
    __tablename__ = 'anonymous_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identity)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Requirement(Base):
    __tablename__ = 'requirement_revisions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identity)
    session_id: Mapped[str] = mapped_column(ForeignKey('anonymous_sessions.id'), index=True)
    base_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Run(Base):
    __tablename__ = 'operation_runs'
    __table_args__ = (UniqueConstraint('session_id', 'idempotency_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identity)
    session_id: Mapped[str] = mapped_column(ForeignKey('anonymous_sessions.id'), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    stage: Mapped[str] = mapped_column(String(80), default='等待处理')
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Snapshot(Base):
    __tablename__ = 'recommendation_snapshots'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identity)
    session_id: Mapped[str] = mapped_column(ForeignKey('anonymous_sessions.id'), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('operation_runs.id'), unique=True)
    requirement_id: Mapped[str] = mapped_column(ForeignKey('requirement_revisions.id'))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def create_database(url: str):
    engine = create_engine(url, connect_args={'check_same_thread': False} if url.startswith('sqlite') else {}, pool_pre_ping=True)
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def enable_foreign_keys(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
    return engine, sessionmaker(engine, expire_on_commit=False)
