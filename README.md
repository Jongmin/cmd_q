# cmd_q

SQLite 기반 에이전트 간 명령 큐. 여러 에이전트 세션이 SQLite 파일을 통해 명령을 주고받는다. WAL 모드로 동시 읽기/쓰기 안전.

## 설치

```bash
pip install git+https://github.com/Jongmin/cmd_q.git
```

또는 버전 고정:

```bash
pip install "git+https://github.com/Jongmin/cmd_q.git@v0.1.0"
```

## DB 경로

우선순위:

1. `CommandQueue(agent, db_path=...)` 인자
2. 환경변수 `CMD_Q_DB`
3. `~/.cmd_q/queue.db` (디렉토리 자동 생성)

프로젝트마다 다른 DB를 쓰려면 환경변수를 분리한다.

```bash
export CMD_Q_DB=/path/to/project/.cmd_q.db
```

## Python API

```python
from cmd_q import CommandQueue

q = CommandQueue("alice")

# 내 미완료 명령 확인
pending = q.check()
# → [{"id": 27, "from_agent": "bob", "title": "...", "priority": "high", "status": "pending"}, ...]

# 명령 상세
cmd = q.get(27)
# → {"id": 27, "body": "...", "ref_files": ["src/test.py"], ...}

# 작업 시작 → 완료
q.start(27)
q.complete(27,
    summary="모든 검증 통과",
    detail="| # | 항목 | 결과 |\n...",
    findings=[
        {"severity": "P0", "title": "버그 발견", "file": "x.py", "line": 42},
    ],
)

# 다른 에이전트에게 명령 보내기
q.send(
    to="charlie",
    title="DB 스키마 검토",
    body="### 수정 내역\n...",
    priority="high",       # critical, high, medium, low
    ref_files=["src/db/schema.py"],
)

# 취소
q.cancel(27, reason="요구사항 변경으로 제거")

# 조회
q.history(days=7)
q.history(agent="alice")
q.search("스키마")
q.get_result(27)
q.stats()
```

## CLI

```bash
cmd_q check alice           # 미완료 명령 확인
cmd_q history 7             # 최근 7일 이력
cmd_q search "스키마"        # 키워드 검색
cmd_q stats                 # 에이전트별 통계
cmd_q get 27                # 명령 상세 + 결과
cmd_q archive 30            # 30일 지난 완료 건 정리
```

## 스키마

### commands
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | INTEGER PK | autoincrement |
| from_agent | TEXT | 보낸 에이전트 |
| to_agent | TEXT | 받을 에이전트 |
| title | TEXT | 제목 |
| body | TEXT | 본문 (마크다운 권장) |
| priority | TEXT | critical / high / medium / low |
| status | TEXT | pending / in_progress / completed / cancelled |
| ref_files | TEXT(JSON) | 관련 파일 경로 리스트 |
| cancel_reason | TEXT | 취소 사유 |
| created_at / started_at / completed_at | DATETIME | |

### results
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | INTEGER PK | |
| command_id | INTEGER FK | commands.id |
| agent | TEXT | 결과 작성 에이전트 |
| summary | TEXT | 1-2줄 요약 |
| detail | TEXT | 상세 (마크다운) |
| findings | TEXT(JSON) | `[{severity, title, file, line}, ...]` |

## 사용 규칙 가이드 (각 프로젝트에서 채택)

프로젝트 규칙 파일(예: AGENTS.md)에 다음을 명시할 것:

- 세션 시작 시 `q.check()` 실행하여 내 미완료 명령 확인
- 다른 에이전트에게 작업 요청 시 `q.send()` 사용
- 검토/검증 완료 후 반드시 `q.complete()` 호출
- "X에게 Y 요청" 지시를 받으면 → 방금 한 작업을 정리해 `q.send()` 의 body 에 포함

## 라이선스

MIT
