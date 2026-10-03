"""
Scheduled Rechecks Runner for Shortlisted Opportunities & Faculty.
Handles:
1. Periodic rechecking of deadlines, funding terms, recruitment status, and faculty contacts.
2. Missed runs handling: catches up with a single controlled execution without launching duplicate jobs.
3. Safe change detection & evidence history recording.
4. User transparency: explicitly notes that local schedules only trigger while the application is running.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from backend.config import config
from backend.logging_utils import logger
from backend.database import (
    get_db_connection,
    enqueue_research_job,
    get_scholarships,
    get_professors,
    get_active_profile
)

def get_scheduled_rechecks() -> List[Dict[str, Any]]:
    """Retrieves all registered recheck tasks."""
    conn = get_db_connection()
    rows = conn.execute("""
    SELECT sr.*, 
           CASE 
               WHEN sr.next_run_at IS NOT NULL AND datetime(sr.next_run_at) < datetime('now') THEN 1 
               ELSE 0 
           END as is_overdue
    FROM scheduled_rechecks sr
    ORDER BY sr.id DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_scheduled_recheck(
    target_type: str, # 'scholarship', 'professor', 'all_shortlisted'
    target_id: Optional[int] = None,
    target_title: str = "",
    target_url: str = "",
    frequency: str = "weekly" # 'daily', 'weekly', 'monthly'
) -> int:
    """Registers a new scheduled recheck for an opportunity or faculty lead."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Calculate initial next_run_at
    now = datetime.now(timezone.utc)
    if frequency == "daily":
        next_run = now + timedelta(days=1)
    elif frequency == "monthly":
        next_run = now + timedelta(days=30)
    else: # weekly default
        next_run = now + timedelta(days=7)

    cursor.execute("""
    INSERT INTO scheduled_rechecks (
        target_type, target_id, target_title, target_url, frequency,
        is_enabled, next_run_at, last_status
    ) VALUES (?, ?, ?, ?, ?, 1, ?, 'pending')
    """, (
        target_type,
        target_id,
        target_title.strip() or f"{target_type.title()} Recheck",
        target_url.strip(),
        frequency,
        next_run.strftime("%Y-%m-%d %H:%M:%S")
    ))
    recheck_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"[Scheduled Rechecks] Created recheck #{recheck_id} ({frequency}) for '{target_title}'")
    return recheck_id

def update_scheduled_recheck(
    recheck_id: int,
    is_enabled: Optional[bool] = None,
    frequency: Optional[str] = None
) -> bool:
    """Updates status or frequency of a scheduled recheck."""
    conn = get_db_connection()
    cursor = conn.cursor()
    fields = ["updated_at = CURRENT_TIMESTAMP"]
    values = []

    if is_enabled is not None:
        fields.append("is_enabled = ?")
        values.append(1 if is_enabled else 0)
    if frequency is not None:
        fields.append("frequency = ?")
        values.append(frequency)
        # Recalculate next run from now if frequency changed
        now = datetime.now(timezone.utc)
        delta = timedelta(days=1) if frequency == "daily" else (timedelta(days=30) if frequency == "monthly" else timedelta(days=7))
        next_run = now + delta
        fields.append("next_run_at = ?")
        values.append(next_run.strftime("%Y-%m-%d %H:%M:%S"))

    values.append(recheck_id)
    sql = f"UPDATE scheduled_rechecks SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(sql, tuple(values))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def delete_scheduled_recheck(recheck_id: int) -> bool:
    """Deletes a scheduled recheck."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scheduled_rechecks WHERE id = ?", (recheck_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

async def check_and_run_due_rechecks() -> List[Dict[str, Any]]:
    """
    Checks for any recheck tasks that are due or overdue (e.g. from missed runs while computer was off).
    Executes a single controlled research job for each due recheck and updates the next run time
    to prevent runaway duplicates.
    """
    conn = get_db_connection()
    due_items = conn.execute("""
    SELECT * FROM scheduled_rechecks
    WHERE is_enabled = 1 AND (next_run_at IS NULL OR datetime(next_run_at) <= datetime('now'))
    """).fetchall()
    conn.close()

    if not due_items:
        return []

    executed = []
    profile = get_active_profile() or {}
    profile_id = profile.get("id")

    for item in due_items:
        recheck_id = item["id"]
        target_type = item["target_type"]
        target_url = item["target_url"]
        target_title = item["target_title"]
        frequency = item["frequency"]

        logger.info(f"[Scheduled Rechecks] Triggering due recheck #{recheck_id} for '{target_title}'")

        # Determine target URL if not provided directly
        effective_url = target_url
        if not effective_url and target_type == "scholarship" and item["target_id"]:
            s_list = get_scholarships(job_id=None)
            for s in s_list:
                if s["id"] == item["target_id"]:
                    effective_url = s.get("official_url") or s.get("source_url")
                    break

        if not effective_url:
            effective_url = "https://scholarships.university.edu"

        # 1. Enqueue recheck job with bounded limits
        job_id = enqueue_research_job(
            university_url=effective_url,
            profile_id=profile_id,
            university_name=f"[Recheck] {target_title}",
            profile_version=profile.get("version", 1),
            scope="funding" if target_type == "scholarship" else ("faculty" if target_type == "professor" else "all"),
            max_pages=8,
            time_limit_seconds=90,
            job_type="scheduled_recheck"
        )

        # 2. Advance next_run_at based on frequency from current time
        now = datetime.now(timezone.utc)
        delta = timedelta(days=1) if frequency == "daily" else (timedelta(days=30) if frequency == "monthly" else timedelta(days=7))
        next_run = now + delta

        conn2 = get_db_connection()
        conn2.execute("""
        UPDATE scheduled_rechecks SET
            last_run_at = CURRENT_TIMESTAMP,
            next_run_at = ?,
            last_status = 'running',
            last_job_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (next_run.strftime("%Y-%m-%d %H:%M:%S"), job_id, recheck_id))
        conn2.commit()
        conn2.close()

        executed.append({
            "recheck_id": recheck_id,
            "target_title": target_title,
            "job_id": job_id,
            "next_run_at": next_run.isoformat()
        })

    return executed
