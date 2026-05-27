"""에이전트 공유 명령 큐 (SQLite + WAL).

여러 에이전트 세션이 SQLite를 통해 명령을 주고받는 구조.
WAL 모드로 동시 읽기/쓰기 안전.

DB 경로 결정 우선순위:
    1) CommandQueue(agent, db_path=...) 인자
    2) 환경변수 CMD_Q_DB
    3) ~/.cmd_q/queue.db (디렉토리 자동 생성)
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

VALID_PRIORITIES = ("critical", "high", "medium", "low")
VALID_STATUSES = ("pending", "in_progress", "completed", "cancelled")

# 현재 스키마 버전 — 마이그레이션 안전성 확보용
SCHEMA_VERSION = 1


def _default_db_path():
    # type: () -> str
    """DB 경로 결정 (환경변수 → 홈 디렉터리 폴백)."""
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
    """에이전트별 명령 큐.

    Parameters
    ----------
    agent_name : str
        이 인스턴스가 사용할 에이전트 이름. 자유 문자열 — 검증하지 않는다.
    db_path : Optional[str]
        DB 파일 경로. 미지정 시 환경변수 CMD_Q_DB 또는 ~/.cmd_q/queue.db.
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
    # 명령 확인
    # ──────────────────────────────────────────

    def check(self):
        # type: () -> List[Dict]
        """내 미완료 명령 조회 (pending + in_progress)."""
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
        """명령 상세 조회."""
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
    # 명령 보내기
    # ──────────────────────────────────────────

    def send(self, to, title, body="", priority="medium", ref_files=None):
        # type: (str, str, str, str, Optional[List[str]]) -> int
        """다른 에이전트에게 명령 보내기."""
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
    # 상태 변경
    # ──────────────────────────────────────────

    def start(self, command_id):
        # type: (int) -> None
        """명령 작업 시작."""
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
        """명령 완료 + 결과 기록."""
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
        """명령 취소."""
        conn = self._conn()
        conn.execute(
            "UPDATE commands SET status = 'cancelled', cancel_reason = ?, "
            "completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (reason, command_id),
        )
        conn.commit()
        conn.close()

    # ──────────────────────────────────────────
    # 조회
    # ──────────────────────────────────────────

    def history(self, days=7, agent=None):
        # type: (int, Optional[str]) -> List[Dict]
        """이력 조회. agent 지정 시 해당 에이전트가 보낸/받은 것."""
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
        """명령 + 결과 키워드 검색."""
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
        """명령의 결과 조회."""
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
    # 통계
    # ──────────────────────────────────────────

    def stats(self):
        # type: () -> List[Dict]
        """에이전트별 통계."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT to_agent as agent, status, COUNT(*) as cnt "
            "FROM commands GROUP BY to_agent, status "
            "ORDER BY to_agent, status",
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ──────────────────────────────────────────
    # 정리
    # ──────────────────────────────────────────

    def archive(self, days=30):
        # type: (int) -> int
        """완료/취소된 오래된 명령을 archive 테이블로 이동."""
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
    # 출력 헬퍼
    # ──────────────────────────────────────────

    def print_check(self):
        # type: () -> None
        """미완료 명령 출력."""
        pending = self.check()
        if not pending:
            print("[%s] 미완료 명령 없음" % self.agent)
            return
        print("[%s] 미완료 명령 %d건:" % (self.agent, len(pending)))
        for cmd in pending:
            print("  #%d [%s] %s ← %s (%s)" % (
                cmd["id"], cmd["priority"].upper(), cmd["title"],
                cmd["from_agent"], cmd["status"]))

    def print_history(self, days=7):
        # type: (int) -> None
        """전체 이력 출력."""
        items = self.history(days)
        if not items:
            print("최근 %d일 명령 없음" % days)
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
        """에이전트별 통계 출력."""
        stats = self.stats()
        if not stats:
            print("데이터 없음")
            return
        current_agent = ""
        for s in stats:
            if s["agent"] != current_agent:
                current_agent = s["agent"]
                print("\n[%s]" % current_agent)
            print("  %s: %d건" % (s["status"], s["cnt"]))
