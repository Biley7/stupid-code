"""SQLite cache store for snapshots, provenance, topology, and explanations.

Each operation uses its own session: it commits on success and rolls back on failure.
Payloads are stored as ``model_dump_json()`` text and validated with the matching domain
model on read. Database and filesystem failures surface as ``CacheStoreError``; the
message carries the exception class name and database path, never row content.

``CacheStore.transact`` and ``CacheStore.read`` run several typed operations on one
session through a ``CacheTransaction``. ``transact`` commits on success and rolls back on
any exception; ``read`` always rolls back, so a read path cannot write. Inside either,
use only the ``CacheTransaction`` methods: a nested public ``CacheStore`` call would open
a second session. Transactional reads never delete a row: an invalid stored payload
raises ``CacheStoreError`` naming the table only.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, TypeVar

from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, Integer, UniqueConstraint, event, type_coerce
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel, create_engine, select

from backend.domain.models import (
    ExplanationEnvelope,
    ModuleMastery,
    PedagogyLens,
    ProvenanceReport,
    RepoGraphSnapshot,
    TopologyProfile,
)

__all__ = [
    "CacheSettings",
    "CacheStore",
    "CacheStoreError",
    "CacheTransaction",
    "ExplanationRow",
    "MasteryRow",
    "ProvenanceRow",
    "RepositoryRecord",
    "RepositoryRow",
    "SnapshotRow",
    "StudyModeRow",
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


class StudyModeRow(SQLModel, table=True):
    repo_id: str = SQLField(primary_key=True)
    enabled: bool


class MasteryRow(SQLModel, table=True):
    repo_id: str = SQLField(primary_key=True)
    target_id: str = SQLField(primary_key=True)
    payload: str  # ModuleMastery.model_dump_json()


class RepositoryRow(SQLModel, table=True):
    repo_id: str = SQLField(primary_key=True)
    source_kind: str  # "local" | "github"
    content_hash: str  # sha256 hex fingerprint computed by the Analysis_Pipeline
    file_count: int
    symbol_count: int
    truncated: bool


_TABLES = [
    SnapshotRow.__table__,  # type: ignore[attr-defined]
    ProvenanceRow.__table__,  # type: ignore[attr-defined]
    TopologyRow.__table__,  # type: ignore[attr-defined]
    ExplanationRow.__table__,  # type: ignore[attr-defined]
    StudyModeRow.__table__,  # type: ignore[attr-defined]
    MasteryRow.__table__,  # type: ignore[attr-defined]
    RepositoryRow.__table__,  # type: ignore[attr-defined]
]


@dataclass(frozen=True)
class RepositoryRecord:
    """Registry entry for one analyzed repository."""

    repo_id: str
    source_kind: str
    content_hash: str
    file_count: int
    symbol_count: int
    truncated: bool


def _table_name(row_type: Any) -> str:
    return str(row_type.__tablename__)


def _invalid_payload(row_type: Any) -> CacheStoreError:
    return CacheStoreError(f"invalid stored payload in table {_table_name(row_type)}")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _raw(column: Any) -> Any:
    """Select a Boolean column as its stored integer, so a corrupt value is not coerced."""
    return type_coerce(column, Integer)


def _stored_bool(value: Any, row_type: Any) -> bool:
    if not _is_int(value) or value not in (0, 1):
        raise _invalid_payload(row_type)
    return value == 1


_REPOSITORY_COLUMNS = (
    RepositoryRow.repo_id,
    RepositoryRow.source_kind,
    RepositoryRow.content_hash,
    RepositoryRow.file_count,
    RepositoryRow.symbol_count,
    _raw(RepositoryRow.truncated),
)


class CacheTransaction:
    """Typed reads and writes on one session.

    Invalid payloads raise ``CacheStoreError`` naming the table; nothing is deleted.
    Committing or rolling back is the job of ``CacheStore.transact`` and ``CacheStore.read``.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # -- snapshot, provenance, topology ------------------------------------------------

    def get_snapshot(self, repo_id: str) -> RepoGraphSnapshot | None:
        return self._get_by_repo(SnapshotRow, repo_id, RepoGraphSnapshot)

    def get_provenance(self, repo_id: str) -> ProvenanceReport | None:
        return self._get_by_repo(ProvenanceRow, repo_id, ProvenanceReport)

    def get_topology(self, repo_id: str) -> TopologyProfile | None:
        return self._get_by_repo(TopologyRow, repo_id, TopologyProfile)

    def put_snapshot(self, snapshot: RepoGraphSnapshot) -> None:
        self._put_by_repo(SnapshotRow, snapshot.repo_id, snapshot)

    def put_provenance(self, report: ProvenanceReport) -> None:
        self._put_by_repo(ProvenanceRow, report.repo_id, report)

    def put_topology(self, profile: TopologyProfile) -> None:
        self._put_by_repo(TopologyRow, profile.repo_id, profile)

    # -- repository registry -----------------------------------------------------------

    def get_repository(self, repo_id: str) -> RepositoryRecord | None:
        row = self._session.exec(
            select(*_REPOSITORY_COLUMNS).where(RepositoryRow.repo_id == repo_id)
        ).first()
        return None if row is None else self._to_record(tuple(row))

    def list_repositories(self) -> list[RepositoryRecord]:
        rows = self._session.exec(
            select(*_REPOSITORY_COLUMNS).order_by(RepositoryRow.repo_id)
        ).all()
        return [self._to_record(tuple(row)) for row in rows]

    def put_repository(self, record: RepositoryRecord) -> None:
        row = self._session.get(RepositoryRow, record.repo_id)
        if row is None:
            self._session.add(
                RepositoryRow(
                    repo_id=record.repo_id,
                    source_kind=record.source_kind,
                    content_hash=record.content_hash,
                    file_count=record.file_count,
                    symbol_count=record.symbol_count,
                    truncated=record.truncated,
                )
            )
            return
        row.source_kind = record.source_kind
        row.content_hash = record.content_hash
        row.file_count = record.file_count
        row.symbol_count = record.symbol_count
        row.truncated = record.truncated
        self._session.add(row)

    # -- study mode --------------------------------------------------------------------

    def get_study_mode(self, repo_id: str) -> bool | None:
        row = self._session.exec(
            select(StudyModeRow.repo_id, _raw(StudyModeRow.enabled)).where(
                StudyModeRow.repo_id == repo_id
            )
        ).first()
        if row is None:
            return None
        return _stored_bool(row[1], StudyModeRow)

    def set_study_mode(self, repo_id: str, enabled: bool) -> None:
        row = self._session.get(StudyModeRow, repo_id)
        if row is None:
            self._session.add(StudyModeRow(repo_id=repo_id, enabled=enabled))
        else:
            row.enabled = enabled
            self._session.add(row)

    # -- mastery records ---------------------------------------------------------------

    def list_mastery(self, repo_id: str) -> list[ModuleMastery]:
        rows = self._session.exec(
            select(MasteryRow).where(MasteryRow.repo_id == repo_id).order_by(MasteryRow.target_id)
        ).all()
        return [self._to_mastery(row) for row in rows]

    def get_mastery(self, repo_id: str, target_id: str) -> ModuleMastery | None:
        row = self._session.get(MasteryRow, (repo_id, target_id))
        return None if row is None else self._to_mastery(row)

    def put_mastery(self, record: ModuleMastery) -> None:
        payload = record.model_dump_json()
        row = self._session.get(MasteryRow, (record.repo_id, record.target_id))
        if row is None:
            self._session.add(
                MasteryRow(repo_id=record.repo_id, target_id=record.target_id, payload=payload)
            )
        else:
            row.payload = payload
            self._session.add(row)

    # -- internals ---------------------------------------------------------------------

    def _get_by_repo(self, row_type: Any, repo_id: str, model: type[_ModelT]) -> _ModelT | None:
        row = self._session.get(row_type, repo_id)
        if row is None:
            return None
        try:
            return model.model_validate_json(row.payload)
        except (ValidationError, TypeError, ValueError):
            raise _invalid_payload(row_type) from None

    def _put_by_repo(self, row_type: Any, repo_id: str, obj: BaseModel) -> None:
        payload = obj.model_dump_json()
        row = self._session.get(row_type, repo_id)
        if row is None:
            self._session.add(row_type(repo_id=repo_id, payload=payload))
        else:
            row.payload = payload
            self._session.add(row)

    @staticmethod
    def _to_mastery(row: MasteryRow) -> ModuleMastery:
        try:
            record = ModuleMastery.model_validate_json(row.payload)
        except (ValidationError, TypeError, ValueError):
            raise _invalid_payload(MasteryRow) from None
        if record.repo_id != row.repo_id or record.target_id != row.target_id:
            raise _invalid_payload(MasteryRow)
        return record

    @staticmethod
    def _to_record(row: tuple[Any, ...]) -> RepositoryRecord:
        repo_id, source_kind, content_hash, file_count, symbol_count, truncated = row
        valid = (
            isinstance(repo_id, str)
            and isinstance(source_kind, str)
            and isinstance(content_hash, str)
            and _is_int(file_count)
            and _is_int(symbol_count)
        )
        if not valid:
            raise _invalid_payload(RepositoryRow)
        return RepositoryRecord(
            repo_id=repo_id,
            source_kind=source_kind,
            content_hash=content_hash,
            file_count=file_count,
            symbol_count=symbol_count,
            truncated=_stored_bool(truncated, RepositoryRow),
        )


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

    # -- transactions ------------------------------------------------------------------

    def transact(self, operation: Callable[[CacheTransaction], _ResultT]) -> _ResultT:
        """Run ``operation`` on one session; commit on success, roll back on any exception.

        Database failures surface as ``CacheStoreError``; any other exception raised by
        ``operation`` propagates unchanged after the rollback.
        """
        return self._run(lambda session: operation(CacheTransaction(session)))

    def read(self, operation: Callable[[CacheTransaction], _ResultT]) -> _ResultT:
        """Run ``operation`` on one session and always roll back, so nothing is written.

        ``operation`` must return fully built values (domain models, ``RepositoryRecord``,
        plain data), never ORM rows: the rollback expires them.
        """

        def op(session: Session) -> _ResultT:
            try:
                return operation(CacheTransaction(session))
            finally:
                session.rollback()

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
