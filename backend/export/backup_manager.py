"""
Database Backup and Restoration Manager for ScholarScout.
Provides:
1. Online, transactional database backup using sqlite3 native backup API.
2. Backup listing with size, timestamp, and table stats.
3. Safe database restoration with pre-restore safety snapshots and integrity verification.
4. Protection against directory traversal attacks.
"""

import os
import sqlite3
import glob
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from backend.config import config
from backend.logging_utils import logger

BACKUPS_DIR = os.path.join(os.path.dirname(os.path.abspath(config.database_path)), "backups")

def ensure_backups_dir() -> str:
    """Ensures the backups directory exists and returns its path."""
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    return BACKUPS_DIR

def _sanitize_filename(filename: str) -> str:
    """Prevents directory traversal by returning only the basename."""
    return os.path.basename(filename).strip()

def get_db_stats_from_conn(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Extracts high-level table record counts from an open SQLite connection."""
    stats = {}
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for table in tables:
            if table.startswith("sqlite_"):
                continue
            try:
                cnt = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                stats[table] = cnt
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[Backup] Failed extracting table stats: {e}")
    return stats

def create_database_backup(label: Optional[str] = None) -> Dict[str, Any]:
    """
    Creates a full, transactional backup of the active ScholarScout database
    using SQLite's online backup API (VACUUM-safe and WAL-compatible).
    """
    ensure_backups_dir()
    db_path = os.path.abspath(config.database_path)
    
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Source database not found at {db_path}")

    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    clean_label = "".join(c for c in (label or "") if c.isalnum() or c in ("-", "_")).strip()
    if clean_label:
        backup_filename = f"scholarscout_backup_{now_str}_{clean_label}.db"
    else:
        backup_filename = f"scholarscout_backup_{now_str}.db"

    backup_filepath = os.path.join(BACKUPS_DIR, backup_filename)

    src_conn = sqlite3.connect(db_path, timeout=60.0)
    dst_conn = sqlite3.connect(backup_filepath, timeout=60.0)

    try:
        # Perform transactional online backup
        with dst_conn:
            src_conn.backup(dst_conn, pages=100, sleep=0.01)
        
        # Verify integrity of the created backup
        integrity = dst_conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity.lower() != "ok":
            raise ValueError(f"Backup failed integrity verification: {integrity}")

        table_stats = get_db_stats_from_conn(dst_conn)
        size_bytes = os.path.getsize(backup_filepath)

        logger.info(f"[Backup] Successfully created database backup: {backup_filename} ({size_bytes} bytes)")

        return {
            "success": True,
            "filename": backup_filename,
            "filepath": backup_filepath,
            "size_bytes": size_bytes,
            "size_formatted": f"{round(size_bytes / 1024, 2)} KB" if size_bytes < 1024*1024 else f"{round(size_bytes / (1024*1024), 2)} MB",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "table_stats": table_stats,
            "integrity": integrity
        }
    finally:
        dst_conn.close()
        src_conn.close()

def list_database_backups() -> List[Dict[str, Any]]:
    """Lists all available database backup files with size and creation timestamp."""
    ensure_backups_dir()
    backup_files = sorted(
        glob.glob(os.path.join(BACKUPS_DIR, "scholarscout_backup_*.db")) +
        glob.glob(os.path.join(BACKUPS_DIR, "pre_restore_safety_snapshot_*.db")),
        reverse=True
    )

    results = []
    for filepath in backup_files:
        filename = os.path.basename(filepath)
        size_bytes = os.path.getsize(filepath)
        mtime = os.path.getmtime(filepath)
        created_at_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)

        # Quick check for table summary
        stats = {}
        try:
            conn = sqlite3.connect(filepath, timeout=5.0)
            stats = get_db_stats_from_conn(conn)
            conn.close()
        except Exception:
            pass

        results.append({
            "filename": filename,
            "filepath": filepath,
            "size_bytes": size_bytes,
            "size_formatted": f"{round(size_bytes / 1024, 2)} KB" if size_bytes < 1024*1024 else f"{round(size_bytes / (1024*1024), 2)} MB",
            "created_at": created_at_dt.isoformat(),
            "table_stats": stats,
            "is_safety_snapshot": filename.startswith("pre_restore_safety_snapshot_")
        })

    return results

def restore_database_backup(backup_filename: str) -> Dict[str, Any]:
    """
    Safely restores the active database from a backup file.
    Creates an automatic safety rollback snapshot before replacing active database.
    """
    ensure_backups_dir()
    clean_filename = _sanitize_filename(backup_filename)
    backup_filepath = os.path.join(BACKUPS_DIR, clean_filename)

    if not os.path.exists(backup_filepath):
        raise FileNotFoundError(f"Backup file '{clean_filename}' does not exist.")

    # 1. Verify integrity of the backup file before restoring
    backup_conn = sqlite3.connect(backup_filepath, timeout=10.0)
    try:
        integrity = backup_conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity.lower() != "ok":
            raise ValueError(f"Selected backup file is corrupted: {integrity}")
        backup_stats = get_db_stats_from_conn(backup_conn)
    finally:
        backup_conn.close()

    # 2. Create automatic pre-restore safety snapshot of the CURRENT database
    db_path = os.path.abspath(config.database_path)
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safety_filename = f"pre_restore_safety_snapshot_{now_str}.db"
    safety_filepath = os.path.join(BACKUPS_DIR, safety_filename)

    if os.path.exists(db_path):
        current_conn = sqlite3.connect(db_path, timeout=60.0)
        safety_conn = sqlite3.connect(safety_filepath, timeout=60.0)
        try:
            with safety_conn:
                current_conn.backup(safety_conn, pages=100, sleep=0.01)
            logger.info(f"[Restore] Created safety pre-restore snapshot: {safety_filename}")
        finally:
            safety_conn.close()
            current_conn.close()

    # 3. Perform restoration via SQLite online backup API from backup into main db
    src_conn = sqlite3.connect(backup_filepath, timeout=60.0)
    dst_conn = sqlite3.connect(db_path, timeout=60.0)
    try:
        with dst_conn:
            src_conn.backup(dst_conn, pages=100, sleep=0.01)

        # Run WAL mode & foreign keys
        dst_conn.execute("PRAGMA journal_mode = WAL")
        dst_conn.execute("PRAGMA foreign_keys = ON")
        dst_conn.commit()

        # Check integrity of restored db
        post_integrity = dst_conn.execute("PRAGMA integrity_check").fetchone()[0]
        if post_integrity.lower() != "ok":
            raise ValueError(f"Restored database integrity check failed: {post_integrity}")

        restored_stats = get_db_stats_from_conn(dst_conn)
        logger.info(f"[Restore] Successfully restored database from {clean_filename}")

        return {
            "success": True,
            "restored_from": clean_filename,
            "safety_snapshot_created": safety_filename,
            "restored_at": datetime.now(timezone.utc).isoformat(),
            "table_stats": restored_stats,
            "integrity": post_integrity
        }
    finally:
        dst_conn.close()
        src_conn.close()

def delete_database_backup(backup_filename: str) -> bool:
    """Deletes a backup file safely within the backups folder."""
    ensure_backups_dir()
    clean_filename = _sanitize_filename(backup_filename)
    backup_filepath = os.path.join(BACKUPS_DIR, clean_filename)

    if os.path.exists(backup_filepath):
        os.remove(backup_filepath)
        logger.info(f"[Backup] Deleted backup file: {clean_filename}")
        return True
    return False
