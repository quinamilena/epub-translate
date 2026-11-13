import json
from typing import Any, Dict, List

from app.db.database import connection


class BlockRepository:
    def bulk_insert(
        self, job_id: str, chapter_id: int, blocks: List[Dict[str, Any]]
    ) -> None:
        if not blocks:
            return
        with connection() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO blocks
                   (job_id, chapter_id, block_index, source_text, kind,
                    meta_json, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
                [
                    (
                        job_id,
                        chapter_id,
                        block["index"],
                        block["text"],
                        block.get("tag") or block.get("kind") or "p",
                        (
                            json.dumps(block["meta"], ensure_ascii=False)
                            if block.get("meta")
                            else None
                        ),
                    )
                    for block in blocks
                ],
            )

    def list_by_chapter(
        self, chapter_id: int, only_pending: bool = False
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM blocks WHERE chapter_id = ?"
        params: List[Any] = [chapter_id]
        if only_pending:
            query += " AND status = 'pending'"
        query += " ORDER BY block_index"
        with connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def save_translations(self, updates: List[Dict[str, Any]]) -> None:
        if not updates:
            return
        with connection() as conn:
            conn.executemany(
                """UPDATE blocks
                   SET translated_text = ?, status = ?, error = ?, attempts = attempts + 1
                   WHERE id = ?""",
                [
                    (
                        update.get("translated_text"),
                        update["status"],
                        update.get("error"),
                        update["id"],
                    )
                    for update in updates
                ],
            )

    def reset_failed(self, job_id: str) -> None:
        with connection() as conn:
            conn.execute(
                """UPDATE blocks SET status = 'pending', error = NULL
                   WHERE job_id = ? AND status = 'failed'""",
                (job_id,),
            )

    def count(self, job_id: str) -> int:
        with connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM blocks WHERE job_id = ?", (job_id,)
            ).fetchone()[0]

    def count_status(self, job_id: str, status: str) -> int:
        with connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM blocks WHERE job_id = ? AND status = ?",
                (job_id, status),
            ).fetchone()[0]

    def count_status_for_chapter(self, chapter_id: int, status: str) -> int:
        with connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM blocks WHERE chapter_id = ? AND status = ?",
                (chapter_id, status),
            ).fetchone()[0]

    def errors(self, job_id: str, limit: int = 10) -> List[str]:
        with connection() as conn:
            rows = conn.execute(
                """SELECT error FROM blocks
                   WHERE job_id = ? AND status = 'failed' AND error IS NOT NULL
                   ORDER BY id LIMIT ?""",
                (job_id, limit),
            ).fetchall()
        return [row[0] for row in rows]
