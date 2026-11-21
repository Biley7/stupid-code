"""SQLite cache store for snapshots, provenance, topology, and explanations.

Each operation uses its own session: it commits on success and rolls back on failure.
Payloads are stored as ``model_dump_json()`` text and validated with the matching domain
model on read. Database and filesystem failures surface as ``CacheStoreError``; the
message carries the exception class name and database path, never row content.
"""

from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Any, TypeVar

from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, UniqueConstraint, event
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel, create_engine, select

from backend.domain.models import (
    ExplanationEnvelope,
    PedagogyLens,
    ProvenanceReport,
    RepoGraphSnapshot,
    TopologyProfile,
)

__all__ = [
    "CacheSettings",
    "CacheStore",
    "CacheStoreError",
    "ExplanationRow",
    "ProvenanceRow",
    "SnapshotRow",
    "TopologyRow",
]

DEFAULT_DB_PATH = "./data/stupid_code.db"
MEMORY_DB_PATH = ":memory:"

_ModelT = TypeVar("_ModelT", bound=BaseModel)
_ResultT = TypeVar("_ResultT")


class CacheStoreError(Exception):
    """Raised for database or filesystem failures in the cache store."""


class CacheSettings(BaseSettings):
    """Cache configuration. Reads ``STUPID_CODE_DB_PATH`` from the environment only."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", populate_by_name=True)

    stupid_code_db_path: str = Field(DEFAULT_DB_PATH, validation_alias="STUPID_CODE_DB_PATH")

    @field_validator("stupid_code_db_path", mode="before")
    @classmethod
    def _empty_means_default(cls, value: Any) -> Any:
        if value is None or (isinstance(value, str) and value == ""):
            return DEFAULT_DB_PATH
        return value


class SnapshotRow(SQLModel, table=True):
    repo_id: str = SQLField(primary_key=True)
    payload: str


class ProvenanceRow(SQLModel, table=True):
    repo_id: str = SQLField(primary_key=True)
    payload: str


class TopologyRow(SQLModel, table=True):
    repo_id: str = SQLField(primary_key=True)
    payload: str


class ExplanationRow(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("repo_id", "ast_hash", "target_id", "lens"),)

    id: int | None = SQLField(default=None, primary_key=True)
    repo_id: str
    ast_hash: str
    target_id: str
    lens: str
    payload: str


_TABLES = [
    SnapshotRow.__table__,  # type: ignore[attr-defined]
    ProvenanceRow.__table__,  # type: ignore[attr-defined]
    TopologyRow.__table__,  # type: ignore[attr-defined]
    ExplanationRow.__table__,  # type: ignore[attr-defined]
]


def _enable_wal(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


class CacheStore:
    """Persist and retrieve the four cached object types, keyed as the design specifies."""

    def __init__(self, db_path: str | None = None, settings: CacheSettings | None = None) -> None:
        if db_path is None or db_path == "":
            db_path = (settings or CacheSettings()).stupid_code_db_path
        self._db_path = db_path
        self._engine: Engine | None = None
        try:
            self._engine = self._create_engine(db_path)
            SQLModel.metadata.create_all(self._engine, tables=_TABLES)
        except (SQLAlchemyError, OSError, ValueError) as exc:  # ValueError: NUL in path
            self.close()
            raise self._wrap(exc) from exc

    # -- lifecycle ---------------------------------------------------------------------

    def close(self) -> None:
        """Dispose the engine. An in-memory database is discarded."""
        engine, self._engine = self._engine, None
        if engine is not None:
            engine.dispose()

    def __enter__(self) -> "CacheStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- snapshots ---------------------------------------------------------------------

    def put_snapshot(self, snapshot: RepoGraphSnapshot) -> None:
        self._put_by_repo(SnapshotRow, snapshot.repo_id, snapshot)

    def get_snapshot(self, repo_id: str) -> RepoGraphSnapshot | None:
        return self._get_by_repo(SnapshotRow, repo_id, RepoGraphSnapshot)

    # -- provenance --------------------------------------------------------------------

    def put_provenance(self, report: ProvenanceReport) -> None:
        self._put_by_repo(ProvenanceRow, report.repo_id, report)

    def get_provenance(self, repo_id: str) -> ProvenanceReport | None:
        return self._get_by_repo(ProvenanceRow, repo_id, ProvenanceReport)

    # -- topology ----------------------------------------------------------------------

    def put_topology(self, profile: TopologyProfile) -> None:
        self._put_by_repo(TopologyRow, profile.repo_id, profile)

    def get_topology(self, repo_id: str) -> TopologyProfile | None:
        return self._get_by_repo(TopologyRow, repo_id, TopologyProfile)

    # -- explanations ------------------------------------------------------------------

    def put_explanation(self, envelope: ExplanationEnvelope) -> None:
        lens = PedagogyLens(envelope.lens).value
        payload = envelope.model_dump_json()

        def op(session: Session) -> None:
            row = session.exec(
                select(ExplanationRow).where(
                    ExplanationRow.repo_id == envelope.repo_id,
                    ExplanationRow.ast_hash == envelope.ast_hash,
                    ExplanationRow.target_id == envelope.target_id,
                    ExplanationRow.lens == lens,
                )
            ).first()
            if row is None:
                session.add(
                    ExplanationRow(
                        repo_id=envelope.repo_id,
                        ast_hash=envelope.ast_hash,
                        target_id=envelope.target_id,
                        lens=lens,
                        payload=payload,
                    )
                )
            else:
                row.payload = payload
                session.add(row)

        self._run(op)

    def get_explanation(
        self, repo_id: str, ast_hash: str, target_id: str, lens: PedagogyLens
    ) -> ExplanationEnvelope | None:
        lens_value = PedagogyLens(lens).value

        def op(session: Session) -> ExplanationEnvelope | None:
            row = session.exec(
                select(ExplanationRow).where(
                    ExplanationRow.repo_id == repo_id,
                    ExplanationRow.ast_hash == ast_hash,
                    ExplanationRow.target_id == target_id,
                    ExplanationRow.lens == lens_value,
                )
            ).first()
            if row is None:
                return None
            try:
                return ExplanationEnvelope.model_validate_json(row.payload)
            except ValidationError:
                session.delete(row)
                return None

        return self._run(op)

    # -- internals ---------------------------------------------------------------------

    def _put_by_repo(self, row_type: Any, repo_id: str, obj: BaseModel) -> None:
        payload = obj.model_dump_json()

        def op(session: Session) -> None:
            row = session.get(row_type, repo_id)
            if row is None:
                session.add(row_type(repo_id=repo_id, payload=payload))
            else:
                row.payload = payload
                session.add(row)

        self._run(op)

    def _get_by_repo(self, row_type: Any, repo_id: str, model: type[_ModelT]) -> _ModelT | None:
        def op(session: Session) -> _ModelT | None:
            row = session.get(row_type, repo_id)
            if row is None:
                return None
            try:
                return model.model_validate_json(row.payload)
            except ValidationError:
                session.delete(row)
                return None

        return self._run(op)

    def _run(self, operation: Callable[[Session], _ResultT]) -> _ResultT:
        """Run ``operation`` in one session: commit on success, roll back on failure."""
        if self._engine is None:
            raise CacheStoreError(f"CacheStore is closed (database {self._db_path})")
        try:
            with Session(self._engine) as session:
                try:
                    result = operation(session)
                    session.commit()
                except BaseException:
                    session.rollback()
                    raise
                return result
        except (SQLAlchemyError, OSError) as exc:
            raise self._wrap(exc) from exc

    def _wrap(self, exc: BaseException) -> CacheStoreError:
        return CacheStoreError(f"{type(exc).__name__} on cache database {self._db_path}")

    @staticmethod
    def _create_engine(db_path: str) -> Engine:
        if db_path == MEMORY_DB_PATH:
            return create_engine(
                "sqlite://",
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # URL.create keeps characters such as "?" in the path out of URL query parsing.
        engine = create_engine(URL.create("sqlite", database=db_path))
        event.listen(engine, "connect", _enable_wal)
        return engine
