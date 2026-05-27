"""cmd_q CLI 진입점.

설치 후 사용법:
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
            print("사용법: cmd_q check <agent>")
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
            print("사용법: cmd_q get <id>")
            return 1
        cmd_id = int(sys.argv[2])
        q = CommandQueue("")
        item = q.get(cmd_id)
        if not item:
            print("명령 #%d 없음" % cmd_id)
            return 1
        print("=== 명령 #%d ===" % item["id"])
        print("  From: %s -> To: %s" % (item["from_agent"], item["to_agent"]))
        print("  제목: %s" % item["title"])
        print("  우선순위: %s / 상태: %s" % (item["priority"], item["status"]))
        print("  생성: %s" % item["created_at"])
        if item["completed_at"]:
            print("  완료: %s" % item["completed_at"])
        print("\n--- 본문 ---")
        print(item["body"])
        if item["ref_files"]:
            print("\n--- 참조 파일 ---")
            for f in item["ref_files"]:
                print("  - %s" % f)
        result = q.get_result(cmd_id)
        if result:
            print("\n--- 결과 ---")
            print("  요약: %s" % result["summary"])
            if result["detail"]:
                print(result["detail"])
            if result["findings"]:
                print("\n  발견사항:")
                for f in result["findings"]:
                    print("    [%s] %s — %s:%s" % (
                        f.get("severity", "?"), f.get("title", ""),
                        f.get("file", ""), f.get("line", "")))

    elif cmd == "archive":
        d = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        count = CommandQueue("").archive(d)
        print("%d건 아카이브 완료" % count)

    else:
        print("알 수 없는 명령: %s" % cmd)
        _print_usage()
        return 1

    return 0


def _print_usage():
    # type: () -> None
    print("사용법:")
    print("  cmd_q check <agent>       — 미완료 명령 확인")
    print("  cmd_q history [days]      — 전체 이력 (기본 7일)")
    print("  cmd_q search <keyword>    — 키워드 검색")
    print("  cmd_q stats               — 에이전트별 통계")
    print("  cmd_q get <id>            — 명령 상세 + 결과")
    print("  cmd_q archive [days]      — 오래된 완료 건 정리 (기본 30일)")
    print("")
    print("DB 경로:")
    print("  환경변수 CMD_Q_DB 로 지정. 미지정 시 ~/.cmd_q/queue.db.")


if __name__ == "__main__":
    sys.exit(main())
