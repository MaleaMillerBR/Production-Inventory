import os
import sqlite3
from pathlib import Path
from typing import List, Optional

_raw_db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
DATABASE_URL = (
    _raw_db_url.replace("postgres://", "postgresql://", 1)
    if _raw_db_url and _raw_db_url.startswith("postgres://")
    else _raw_db_url
)


def _get_comment_conn():
    if DATABASE_URL:
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    path = Path(__file__).resolve().parent.parent / "backend" / "comments.db"
    return sqlite3.connect(str(path))


def init_comments_table(conn) -> None:
    cur = conn.cursor()
    if DATABASE_URL:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS item_comments (
                internal_reference TEXT NOT NULL,
                work_area TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (internal_reference, work_area)
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS item_comments (
                internal_reference TEXT NOT NULL,
                work_area TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (internal_reference, work_area)
            )
        """)
    conn.commit()
    cur.close()


def get_comments_list(work_areas: Optional[List[str]] = None) -> List[dict]:
    conn = _get_comment_conn()
    try:
        cur = conn.cursor()
        if work_areas:
            if DATABASE_URL:
                cur.execute(
                    "SELECT internal_reference, work_area, comment FROM item_comments WHERE work_area = ANY(%s)",
                    (work_areas,),
                )
            else:
                placeholders = ",".join("?" * len(work_areas))
                cur.execute(
                    f"SELECT internal_reference, work_area, comment FROM item_comments WHERE work_area IN ({placeholders})",
                    work_areas,
                )
        else:
            cur.execute("SELECT internal_reference, work_area, comment FROM item_comments")
        rows = cur.fetchall()
        cur.close()
        return [
            {"internal_reference": r[0], "work_area": r[1], "comment": r[2] or ""}
            for r in rows
        ]
    finally:
        conn.close()


def save_comment(internal_reference: str, work_area: str, comment: str) -> None:
    conn = _get_comment_conn()
    try:
        cur = conn.cursor()
        text = (comment or "").strip()
        if DATABASE_URL:
            cur.execute(
                """
                INSERT INTO item_comments (internal_reference, work_area, comment, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (internal_reference, work_area) DO UPDATE SET comment = EXCLUDED.comment, updated_at = CURRENT_TIMESTAMP
                """,
                (internal_reference, work_area, text),
            )
        else:
            cur.execute(
                """
                INSERT INTO item_comments (internal_reference, work_area, comment, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (internal_reference, work_area) DO UPDATE SET comment = excluded.comment, updated_at = CURRENT_TIMESTAMP
                """,
                (internal_reference, work_area, text),
            )
        conn.commit()
        cur.close()
    finally:
        conn.close()
