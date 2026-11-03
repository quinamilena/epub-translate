from typing import Any, Dict, List, Optional

from app.db.database import connection


class ChapterRepository:
    def bulk_create(self, job_id: str, documents: List[Dict[str, Any]]) -> None:
        if not documents:
            return
        with connection() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO chapters
                   (job_id, file_name, item_id, order_index, status)
                   VALUES (?, ?, ?, ?, 'pending')""",
                [
                    (job_id, doc["file_name"], doc.get("item_id"), index)
                    for index, doc in enumerate(documents)
                ],
            )

    def list_by_job(self, job_id: str) -> List[Dict[str, Any]]:
        with connection() as conn:
            rows = conn.execute(
                "SELECT * FROM chapters WHERE job_id = ? ORDER BY order_index",
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, chapter_id: int) -> Optional[Dict[str, Any]]:
        with connection() as conn:
            row = conn.execute(
                "SELECT * FROM chapters WHERE id = ?", (chapter_id,)
            ).fetchone()
        return dict(row) if row else None

    def count(self, job_id: str) -> int:
        with connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM chapters WHERE job_id = ?", (job_id,)
            ).fetchone()[0]

    def count_done(self, job_id: str) -> int:
        with connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM chapters WHERE job_id = ? AND status = 'done'",
                (job_id,),
            ).fetchone()[0]

    def set_status(
        self,
        chapter_id: int,
        status: str,
        error: Optional[str] = None,
        increment_attempts: bool = False,
    ) -> None:
        attempts_sql = "attempts + 1" if increment_attempts else "attempts"
        with connection() as conn:
            conn.execute(
                f"UPDATE chapters SET status = ?, error = ?, attempts = {attempts_sql} WHERE id = ?",
                (status, error, chapter_id),
            )
