"""Shared agent command queue (SQLite + WAL).

A structure where multiple agent sessions exchange commands through SQLite.
WAL mode makes concurrent reads/writes safe.

DB path resolution priority:
    1) CommandQueue(agent, db_path=...) argument
    2) CMD_Q_DB environment variable
    3) ~/.cmd_q/queue.db (directory created automatically)
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

VALID_PRIORITIES = ("critical", "high", "medium", "low")
VALID_STATUSES = ("pending", "in_progress", "completed", "cancelled")

# Current schema version — for migration safety
SCHEMA_VERSION = 1


def _default_db_path():
    # type: () -> str
    """Resolve the DB path (environment variable -> home directory fallback)."""
    env = os.environ.get("CMD_Q_DB")
    if env:
        return env
    home = os.path.expanduser("~")
    return os.path.join(home, ".cmd_q", "queue.db")


def _get_conn(db_path):
    # type: (str) -> sqlite3.Connection
    parent = os.path.dirname(db_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def _setup_db(db_path):
    # type: (str) -> None
    conn = _get_conn(db_path)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS commands (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent   TEXT NOT NULL,
            to_agent     TEXT NOT NULL,
            title        TEXT NOT NULL,
            body         TEXT NOT NULL DEFAULT '',
            priority     TEXT DEFAULT 'medium',
            status       TEXT DEFAULT 'pending',
            ref_files    TEXT DEFAULT '[]',
            cancel_reason TEXT,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            started_at   DATETIME,
            completed_at DATETIME
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            command_id  INTEGER NOT NULL REFERENCES commands(id),
            agent       TEXT NOT NULL,
            summary     TEXT NOT NULL,
            detail      TEXT,
            findings    TEXT DEFAULT '[]',
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS schema_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute(
        "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('version', ?)",
        (str(SCHEMA_VERSION),),
    )

    c.execute("CREATE INDEX IF NOT EXISTS idx_cmd_to ON commands(to_agent, status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cmd_status ON commands(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cmd_from ON commands(from_agent)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cmd_created ON commands(created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_res_cmd ON results(command_id)")

    conn.commit()
    conn.close()


class CommandQueue:
    """Per-agent command queue.

    Parameters
    ----------
    agent_name : str
        The agent name this instance uses. Free-form string — not validated.
    db_path : Optional[str]
        DB file path. If unspecified, the CMD_Q_DB environment variable or
        ~/.cmd_q/queue.db.
    """

    def __init__(self, agent_name, db_path=None):
        # type: (str, Optional[str]) -> None
        self.agent = agent_name
        self.db_path = db_path or _default_db_path()
        _setup_db(self.db_path)

    def _conn(self):
        # type: () -> sqlite3.Connection
        return _get_conn(self.db_path)

    # ──────────────────────────────────────────
    # Check commands
    # ──────────────────────────────────────────

    def check(self):
        # type: () -> List[Dict]
        """Query my unfinished commands (pending + in_progress)."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT id, from_agent, title, priority, status, created_at "
            "FROM commands "
            "WHERE to_agent = ? AND status IN ('pending', 'in_progress') "
            "ORDER BY "
            "  CASE priority "
            "    WHEN 'critical' THEN 0 "
            "    WHEN 'high' THEN 1 "
            "    WHEN 'medium' THEN 2 "
            "    WHEN 'low' THEN 3 "
            "  END, created_at ASC",
            (self.agent,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get(self, command_id):
        # type: (int) -> Optional[Dict]
        """Query command details."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM commands WHERE id = ?", (command_id,)
        ).fetchone()
        conn.close()
        if row:
            result = dict(row)
            result["ref_files"] = json.loads(result.get("ref_files", "[]"))
            return result
        return None

    # ──────────────────────────────────────────
    # Send commands
    # ──────────────────────────────────────────

    def send(self, to, title, body="", priority="medium", ref_files=None):
        # type: (str, str, str, str, Optional[List[str]]) -> int
        """Send a command to another agent."""
        if priority not in VALID_PRIORITIES:
            raise ValueError("priority must be one of: %s" % ", ".join(VALID_PRIORITIES))
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO commands (from_agent, to_agent, title, body, priority, ref_files) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (self.agent, to, title, body, priority,
             json.dumps(ref_files or [], ensure_ascii=False)),
        )
        conn.commit()
        cmd_id = c.lastrowid
        conn.close()
        return cmd_id

    # ──────────────────────────────────────────
    # Status changes
    # ──────────────────────────────────────────

    def start(self, command_id):
        # type: (int) -> None
        """Start working on a command."""
        conn = self._conn()
        conn.execute(
            "UPDATE commands SET status = 'in_progress', started_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (command_id,),
        )
        conn.commit()
        conn.close()

    def complete(self, command_id, summary, detail="", findings=None):
        # type: (int, str, str, Optional[List[Dict]]) -> int
        """Complete a command and record the result."""
        conn = self._conn()
        c = conn.cursor()

        c.execute(
            "INSERT INTO results (command_id, agent, summary, detail, findings) "
            "VALUES (?, ?, ?, ?, ?)",
            (command_id, self.agent, summary, detail,
             json.dumps(findings or [], ensure_ascii=False)),
        )
        result_id = c.lastrowid

        c.execute(
            "UPDATE commands SET status = 'completed', completed_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (command_id,),
        )
        conn.commit()
        conn.close()
        return result_id

    def cancel(self, command_id, reason=""):
        # type: (int, str) -> None
        """Cancel a command."""
        conn = self._conn()
        conn.execute(
            "UPDATE commands SET status = 'cancelled', cancel_reason = ?, "
            "completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (reason, command_id),
        )
        conn.commit()
        conn.close()

    # ──────────────────────────────────────────
    # Queries
    # ──────────────────────────────────────────

    def history(self, days=7, agent=None):
        # type: (int, Optional[str]) -> List[Dict]
        """Query history. If agent is given, what that agent sent/received."""
        conn = self._conn()
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        if agent:
            rows = conn.execute(
                "SELECT id, from_agent, to_agent, title, priority, status, "
                "created_at, completed_at "
                "FROM commands "
                "WHERE (from_agent = ? OR to_agent = ?) AND created_at >= ? "
                "ORDER BY created_at DESC",
                (agent, agent, cutoff),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, from_agent, to_agent, title, priority, status, "
                "created_at, completed_at "
                "FROM commands WHERE created_at >= ? "
                "ORDER BY created_at DESC",
                (cutoff,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def search(self, keyword):
        # type: (str) -> List[Dict]
        """Keyword search over commands and results."""
        conn = self._conn()
        pattern = "%{}%".format(keyword)

        cmd_rows = conn.execute(
            "SELECT id, from_agent, to_agent, title, priority, status, created_at "
            "FROM commands WHERE title LIKE ? OR body LIKE ?",
            (pattern, pattern),
        ).fetchall()

        res_rows = conn.execute(
            "SELECT r.command_id as id, c.from_agent, c.to_agent, "
            "c.title, c.priority, c.status, c.created_at "
            "FROM results r JOIN commands c ON r.command_id = c.id "
            "WHERE r.summary LIKE ? OR r.detail LIKE ?",
            (pattern, pattern),
        ).fetchall()

        conn.close()

        seen = set()
        results = []
        for r in list(cmd_rows) + list(res_rows):
            d = dict(r)
            if d["id"] not in seen:
                seen.add(d["id"])
                results.append(d)

        return sorted(results, key=lambda x: x["created_at"], reverse=True)

    def get_result(self, command_id):
        # type: (int) -> Optional[Dict]
        """Query the result of a command."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM results WHERE command_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (command_id,),
        ).fetchone()
        conn.close()
        if row:
            result = dict(row)
            result["findings"] = json.loads(result.get("findings", "[]"))
            return result
        return None

    # ──────────────────────────────────────────
    # Statistics
    # ──────────────────────────────────────────

    def stats(self):
        # type: () -> List[Dict]
        """Per-agent statistics."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT to_agent as agent, status, COUNT(*) as cnt "
            "FROM commands GROUP BY to_agent, status "
            "ORDER BY to_agent, status",
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ──────────────────────────────────────────
    # Cleanup
    # ──────────────────────────────────────────

    def archive(self, days=30):
        # type: (int) -> int
        """Move old completed/cancelled commands to the archive tables."""
        conn = self._conn()
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS commands_archive (
                id INTEGER, from_agent TEXT, to_agent TEXT, title TEXT,
                body TEXT, priority TEXT, status TEXT, ref_files TEXT,
                cancel_reason TEXT, created_at DATETIME,
                started_at DATETIME, completed_at DATETIME,
                archived_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS results_archive (
                id INTEGER, command_id INTEGER, agent TEXT,
                summary TEXT, detail TEXT, findings TEXT,
                created_at DATETIME,
                archived_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        old_ids = [r[0] for r in conn.execute(
            "SELECT id FROM commands "
            "WHERE status IN ('completed', 'cancelled') AND completed_at < ?",
            (cutoff,),
        ).fetchall()]

        if not old_ids:
            conn.close()
            return 0

        placeholders = ",".join("?" * len(old_ids))

        conn.execute(
            "INSERT INTO commands_archive "
            "SELECT *, CURRENT_TIMESTAMP FROM commands WHERE id IN (%s)" % placeholders,
            old_ids,
        )
        conn.execute(
            "INSERT INTO results_archive "
            "SELECT *, CURRENT_TIMESTAMP FROM results WHERE command_id IN (%s)" % placeholders,
            old_ids,
        )

        conn.execute("DELETE FROM results WHERE command_id IN (%s)" % placeholders, old_ids)
        conn.execute("DELETE FROM commands WHERE id IN (%s)" % placeholders, old_ids)

        conn.commit()
        conn.close()
        return len(old_ids)

    # ──────────────────────────────────────────
    # Output helpers
    # ──────────────────────────────────────────

    def print_check(self):
        # type: () -> None
        """Print unfinished commands."""
        pending = self.check()
        if not pending:
            print("[%s] No unfinished commands" % self.agent)
            return
        print("[%s] %d unfinished command(s):" % (self.agent, len(pending)))
        for cmd in pending:
            print("  #%d [%s] %s ← %s (%s)" % (
                cmd["id"], cmd["priority"].upper(), cmd["title"],
                cmd["from_agent"], cmd["status"]))

    def print_history(self, days=7):
        # type: (int) -> None
        """Print the full history."""
        items = self.history(days)
        if not items:
            print("No commands in the last %d day(s)" % days)
            return
        status_icon = {
            "pending": "[P]", "in_progress": "[R]",
            "completed": "[OK]", "cancelled": "[X]",
        }
        current_date = ""
        for item in items:
            date = (item["created_at"] or "")[:10]
            if date != current_date:
                current_date = date
                print("\n=== %s ===" % date)
            icon = status_icon.get(item["status"], "?")
            print("  %s #%d [%s] %s -> %s: %s" % (
                icon, item["id"], item["priority"],
                item["from_agent"], item["to_agent"], item["title"]))

    def print_stats(self):
        # type: () -> None
        """Print per-agent statistics."""
        stats = self.stats()
        if not stats:
            print("No data")
            return
        current_agent = ""
        for s in stats:
            if s["agent"] != current_agent:
                current_agent = s["agent"]
                print("\n[%s]" % current_agent)
            print("  %s: %d" % (s["status"], s["cnt"]))
