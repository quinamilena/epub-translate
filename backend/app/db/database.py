import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.core.config import settings


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _db_path() -> Path:
    path = Path(settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_column(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    """Adiciona uma coluna em bancos criados por versões anteriores.

    O schema usa CREATE TABLE IF NOT EXISTS, que não altera tabelas
    existentes. Por isso cada coluna nova precisa ser verificada aqui.
    """
    columns = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table})")
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    """Cria o schema (idempotente) e aplica as migrações pendentes."""
    with connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _ensure_column(
            conn, "jobs", "source_format", "TEXT NOT NULL DEFAULT 'epub'"
        )
        _ensure_column(conn, "chapters", "title", "TEXT")
        _ensure_column(conn, "blocks", "kind", "TEXT NOT NULL DEFAULT 'p'")
        _ensure_column(conn, "blocks", "meta_json", "TEXT")
        _ensure_column(
            conn, "jobs", "context_blocks", "INTEGER NOT NULL DEFAULT 2"
        )
        conn.execute("PRAGMA user_version=3")
