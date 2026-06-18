"""cmd_q CLI entry point.

Usage after installation:
    cmd_q check <agent>
    cmd_q history [days]
    cmd_q search <keyword>
    cmd_q stats
    cmd_q get <id>
    cmd_q archive [days]
"""

import sys

from cmd_q.command_queue import CommandQueue


def main():
    # type: () -> int
    if len(sys.argv) < 2:
        _print_usage()
        return 0

    cmd = sys.argv[1]

    if cmd == "check":
        if len(sys.argv) < 3:
            print("Usage: cmd_q check <agent>")
            return 1
        agent = sys.argv[2]
        CommandQueue(agent).print_check()

    elif cmd == "history":
        d = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        CommandQueue("").print_history(d)

    elif cmd == "search":
        kw = sys.argv[2] if len(sys.argv) > 2 else ""
        results = CommandQueue("").search(kw)
        for r in results:
            print("#%d [%s] %s -> %s: %s (%s)" % (
                r["id"], r["priority"], r["from_agent"],
                r["to_agent"], r["title"], r["status"]))

    elif cmd == "stats":
        CommandQueue("").print_stats()

    elif cmd == "get":
        if len(sys.argv) < 3:
            print("Usage: cmd_q get <id>")
            return 1
        cmd_id = int(sys.argv[2])
        q = CommandQueue("")
        item = q.get(cmd_id)
        if not item:
            print("Command #%d not found" % cmd_id)
            return 1
        print("=== Command #%d ===" % item["id"])
        print("  From: %s -> To: %s" % (item["from_agent"], item["to_agent"]))
        print("  Title: %s" % item["title"])
        print("  Priority: %s / Status: %s" % (item["priority"], item["status"]))
        print("  Created: %s" % item["created_at"])
        if item["completed_at"]:
            print("  Completed: %s" % item["completed_at"])
        print("\n--- Body ---")
        print(item["body"])
        if item["ref_files"]:
            print("\n--- Reference files ---")
            for f in item["ref_files"]:
                print("  - %s" % f)
        result = q.get_result(cmd_id)
        if result:
            print("\n--- Result ---")
            print("  Summary: %s" % result["summary"])
            if result["detail"]:
                print(result["detail"])
            if result["findings"]:
                print("\n  Findings:")
                for f in result["findings"]:
                    print("    [%s] %s — %s:%s" % (
                        f.get("severity", "?"), f.get("title", ""),
                        f.get("file", ""), f.get("line", "")))

    elif cmd == "archive":
        d = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        count = CommandQueue("").archive(d)
        print("%d archived" % count)

    else:
        print("Unknown command: %s" % cmd)
        _print_usage()
        return 1

    return 0


def _print_usage():
    # type: () -> None
    print("Usage:")
    print("  cmd_q check <agent>       — show pending commands")
    print("  cmd_q history [days]      — full history (default 7 days)")
    print("  cmd_q search <keyword>    — search by keyword")
    print("  cmd_q stats               — per-agent statistics")
    print("  cmd_q get <id>            — command detail + result")
    print("  cmd_q archive [days]      — clean up old completed entries (default 30 days)")
    print("")
    print("DB path:")
    print("  Set via the CMD_Q_DB environment variable. Defaults to ~/.cmd_q/queue.db.")


if __name__ == "__main__":
    sys.exit(main())
