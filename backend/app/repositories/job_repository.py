from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.database import connection


ACTIVE_STATUSES = ("queued", "extracting", "translating", "rebuilding", "validating")

_UPDATABLE = {
    "source_path", "status", "progress", "message", "provider", "model",
    "base_url", "glossary", "has_api_key", "parser_version", "source_title",
    "total_chapters", "done_chapters", "total_blocks", "done_blocks",
    "output_path", "validation_json", "errors_json", "error",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRepository:
    def create(
        self,
        job_id: str,
        filename: str,
        *,
        source_path: str = "",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        glossary: Optional[str] = None,
        parser_version: int = 1,
    ) -> None:
        now = _now()
        with connection() as conn:
            conn.execute(
                """INSERT INTO jobs
                   (id, filename, source_path, status, progress, message,
                    provider, model, base_url, glossary, parser_version,
                    created_at, updated_at)
                   VALUES (?, ?, ?, 'queued', 0, 'Job criado', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id, filename, source_path, provider, model, base_url,
                    glossary, parser_version, now, now,
                ),
            )

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with connection() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row else None

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        with connection() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def update(self, job_id: str, **fields: Any) -> None:
        data = {key: value for key, value in fields.items() if key in _UPDATABLE}
        if not data:
            return
        data["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in data)
        with connection() as conn:
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?",
                (*data.values(), job_id),
            )

    def recover_interrupted(self) -> int:
        """Marca jobs que estavam ativos quando o processo caiu como 'paused'."""
        placeholders = ", ".join("?" for _ in ACTIVE_STATUSES)
        with connection() as conn:
            cursor = conn.execute(
                f"""UPDATE jobs
                    SET status = 'paused',
                        message = 'Interrompido. Use retomar para continuar.',
                        updated_at = ?
                    WHERE status IN ({placeholders})""",
                (_now(), *ACTIVE_STATUSES),
            )
            return cursor.rowcount

    def purge_payload(self, job_id: str) -> None:
        """Remove blocos e capítulos, mantendo apenas os metadados do job."""
        with connection() as conn:
            conn.execute("DELETE FROM blocks WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM chapters WHERE job_id = ?", (job_id,))
