"""cmd_q — 에이전트 간 명령 큐 시스템.

SQLite 기반, WAL 모드로 다중 프로세스 동시 접근 안전.
서로 다른 에이전트 세션이 명령을 주고받는 데 사용한다.

사용법:
    from cmd_q import CommandQueue

    q = CommandQueue("alice")          # ~/.cmd_q/queue.db 자동 사용
    q = CommandQueue("alice", db_path="/path/to/db")  # 직접 지정
    # 또는 환경변수 CMD_Q_DB 로 경로 지정
"""

from cmd_q.command_queue import CommandQueue

__version__ = "0.1.0"
__all__ = ["CommandQueue"]
