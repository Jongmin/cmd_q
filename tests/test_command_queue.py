"""기본 단위 테스트 — 임시 DB 경로로 전 흐름 검증."""

import os
import tempfile
import unittest

from cmd_q import CommandQueue


class CommandQueueTest(unittest.TestCase):
    def setUp(self):
        # type: () -> None
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.db_path)  # _setup_db 이 새로 만들도록

    def tearDown(self):
        # type: () -> None
        for ext in ("", "-wal", "-shm", "-journal"):
            p = self.db_path + ext
            if os.path.exists(p):
                os.remove(p)

    def test_send_and_check(self):
        # type: () -> None
        bob = CommandQueue("bob", db_path=self.db_path)
        alice = CommandQueue("alice", db_path=self.db_path)

        cmd_id = bob.send(to="alice", title="review request", body="body", priority="high")
        self.assertGreater(cmd_id, 0)

        pending = alice.check()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], cmd_id)
        self.assertEqual(pending[0]["priority"], "high")

        detail = alice.get(cmd_id)
        self.assertEqual(detail["title"], "review request")
        self.assertEqual(detail["body"], "body")

    def test_start_complete(self):
        # type: () -> None
        bob = CommandQueue("bob", db_path=self.db_path)
        alice = CommandQueue("alice", db_path=self.db_path)

        cmd_id = bob.send(to="alice", title="t", body="b")
        alice.start(cmd_id)
        self.assertEqual(alice.get(cmd_id)["status"], "in_progress")

        alice.complete(cmd_id,
            summary="OK",
            detail="all green",
            findings=[{"severity": "P2", "title": "minor"}],
        )
        self.assertEqual(alice.get(cmd_id)["status"], "completed")

        result = alice.get_result(cmd_id)
        self.assertEqual(result["summary"], "OK")
        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(result["findings"][0]["severity"], "P2")

    def test_cancel(self):
        # type: () -> None
        bob = CommandQueue("bob", db_path=self.db_path)
        cmd_id = bob.send(to="alice", title="x")
        bob.cancel(cmd_id, reason="manual cancel")
        d = bob.get(cmd_id)
        self.assertEqual(d["status"], "cancelled")
        self.assertEqual(d["cancel_reason"], "manual cancel")

    def test_priority_order(self):
        # type: () -> None
        bob = CommandQueue("bob", db_path=self.db_path)
        alice = CommandQueue("alice", db_path=self.db_path)
        bob.send(to="alice", title="low",      priority="low")
        bob.send(to="alice", title="critical", priority="critical")
        bob.send(to="alice", title="medium",   priority="medium")
        bob.send(to="alice", title="high",     priority="high")
        pending = alice.check()
        self.assertEqual(
            [p["title"] for p in pending],
            ["critical", "high", "medium", "low"],
        )

    def test_invalid_priority(self):
        # type: () -> None
        bob = CommandQueue("bob", db_path=self.db_path)
        with self.assertRaises(ValueError):
            bob.send(to="alice", title="x", priority="urgent")

    def test_search(self):
        # type: () -> None
        bob = CommandQueue("bob", db_path=self.db_path)
        alice = CommandQueue("alice", db_path=self.db_path)
        bob.send(to="alice", title="schema review", body="check")
        bob.send(to="alice", title="other", body="something")
        hits = alice.search("schema")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["title"], "schema review")


if __name__ == "__main__":
    unittest.main()
