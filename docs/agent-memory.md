# 에이전트 메모리 구성 (Agent Memory)

세션 간에 유지되는 **파일 기반 메모리**. 에이전트의 정체성·역할·사용자 선호·프로젝트 맥락을
작은 파일들로 저장하고, 매 세션 시작 시 인덱스를 로드한다.

명령 큐가 *"지금 무엇을 할지"* 를 다룬다면, 메모리는 *"나는 누구이고 어떻게 일하는가"* 를 다룬다.
워킹모드 세션 시작 프로토콜의 1단계가 이 메모리 로드다. → [working-mode.md](working-mode.md)

---

## 디렉토리 구조

```
<project-memory>/
├── MEMORY.md                    # 인덱스 (매 세션 로드, 한 줄 = 한 메모리)
├── project_<role>_role.md       # 에이전트 정체성 / 역할
├── feedback_<topic>.md          # 사용자 피드백 / 작업 규칙
├── project_<topic>.md           # 프로젝트 목표 / 제약
└── reference_<topic>.md         # 외부 리소스 포인터
```

프로젝트마다 별도 메모리 디렉토리를 둔다(큐 DB 를 `CMD_Q_DB` 로 분리하는 것과 같은 원리).

---

## 메모리 파일 = 하나의 사실

각 파일은 **하나의 사실**을 담고 frontmatter 를 갖는다:

```markdown
---
name: <short-kebab-case-slug>
description: <한 줄 요약 — 회상 시 관련성 판단에 사용>
metadata:
  type: user | feedback | project | reference
---

<사실 본문. feedback / project 는 **Why:** 와 **How to apply:** 줄을 덧붙인다.
관련 메모리는 [[their-name]] 으로 링크.>
```

### 4가지 타입

| type | 용도 |
|---|---|
| `user` | 사용자가 누구인가 (역할, 전문성, 선호) |
| `feedback` | 일하는 방식에 대한 지침 (교정·확정된 접근) — **why 포함** |
| `project` | 코드 / git 에서 유추 불가한 진행 작업·목표·제약 (상대 날짜는 절대 날짜로 변환) |
| `reference` | 외부 리소스 포인터 (URL, 대시보드, 티켓) |

---

## MEMORY.md 인덱스

매 세션 컨텍스트에 로드되는 인덱스. **한 줄에 한 메모리, frontmatter 없음**:

```markdown
- [Developer agent identity](project_developer_role.md) — 메인 개발 에이전트 정체성·행동 규칙·세션 시작 프로토콜
- [Verifier agent role](project_verifier_role.md) — 독립 검증 담당
- [Command queue](reference_command_queue.md) — SQLite 명령 큐 사용법
- [Working-mode auto-stop](feedback_working_mode.md) — 워커 큐가 모두 비면 루프 자동 종료
```

규칙:

- 저장 전 기존 파일이 이미 그 사실을 담고 있는지 확인 — **중복 생성 대신 갱신**.
- 틀린 것으로 판명된 메모리는 삭제.
- 코드 / git / 설정이 이미 기록하는 것은 저장하지 않는다 (메모리는 *유추 불가한* 것만).
- 메모리는 작성 시점의 관찰이다 — 파일·함수·플래그를 언급하면 현재 코드로 재확인 후 단언한다.

---

## 역할 기반 에이전트 정체성

멀티 에이전트 협업에서 각 에이전트는 `project` 타입 메모리로 자기 정체성을 갖는다.
정체성 파일에 담는 것:

- **나는 누구인가** — 역할(개발 / 검증 / 조율), 책임 범위
- **작업 원칙** — 명령 정확 이행, 코드로 증명, 모르면 모른다, 묻지 않고 실행 …
- **세션 시작 행동** — 메모리 확인 → 큐 확인 → 처리 → 보고
- **팀 구조** — 다른 에이전트와의 관계 (누가 만들고 누가 검증하는가)

예시 템플릿: [../examples/agents/developer-agent.md](../examples/agents/developer-agent.md) ·
[../examples/agents/verifier-agent.md](../examples/agents/verifier-agent.md)

### 개발 / 검증 분리 패턴

흔한 구성은 **생산자 / 검증자 분리**다:

- **Developer agent** — 설계·구현·작성. 프로젝트를 전진시키는 주체.
- **Verifier agent** — 산출물을 독립 검증·리뷰. over-claim 거부. 생산자와 다른 시각.

명령 큐가 둘을 잇는다: developer 가 구현 후 `q.send(to="verifier", ...)` 로 검증을 요청하고,
verifier 가 `q.complete()` 의 `summary` / `findings` 에 PASS/FAIL 과 근거를 기록한다.

```
 ┌───────────┐   q.send(to="verifier")    ┌──────────┐
 │ Developer │ ─────────────────────────▶ │ Verifier │
 │  (구현)   │                            │  (검증)  │
 └───────────┘ ◀───────────────────────── └──────────┘
              q.complete(PASS/FAIL, findings)
```

---

관련 문서: [working-mode.md](working-mode.md) · [../README.md](../README.md)
