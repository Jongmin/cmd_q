"""cmd_q — inter-agent command queue system.

SQLite-based, uses WAL mode for safe concurrent access from multiple processes.
Used for different agent sessions to exchange commands with each other.

Usage:
    from cmd_q import CommandQueue

    q = CommandQueue("alice")          # uses ~/.cmd_q/queue.db automatically
    q = CommandQueue("alice", db_path="/path/to/db")  # specify directly
    # or set the path via the CMD_Q_DB environment variable
"""

from cmd_q.command_queue import CommandQueue

__version__ = "0.1.0"
__all__ = ["CommandQueue"]
