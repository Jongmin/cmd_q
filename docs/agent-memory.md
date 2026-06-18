# Agent Memory

**File-based memory** that persists across sessions. It stores an agent's identity, role, user preferences, and project context
as small files, and loads an index at the start of every session.

If the command queue handles *"what to do right now"*, memory handles *"who I am and how I work"*.
Step 1 of the working-mode session start protocol is loading this memory. → [working-mode.md](working-mode.md)

---

## Directory structure

```
<project-memory>/
├── MEMORY.md                    # Index (loaded every session, one line = one memory)
├── project_<role>_role.md       # Agent identity / role
├── feedback_<topic>.md          # User feedback / work rules
├── project_<topic>.md           # Project goals / constraints
└── reference_<topic>.md         # Pointers to external resources
```

Keep a separate memory directory per project (the same principle as isolating the queue DB via `CMD_Q_DB`).

---

## A memory file = one fact

Each file holds **one fact** and has frontmatter:

```markdown
---
name: <short-kebab-case-slug>
description: <one-line summary — used to judge relevance during recall>
metadata:
  type: user | feedback | project | reference
---

<Fact body. feedback / project add **Why:** and **How to apply:** lines.
Link related memories with [[their-name]].>
```

### The 4 types

| type | Purpose |
|---|---|
| `user` | Who the user is (role, expertise, preferences) |
| `feedback` | Guidance on how to work (corrected, confirmed approaches) — **includes why** |
| `project` | Ongoing tasks, goals, and constraints that can't be inferred from code / git (convert relative dates to absolute dates) |
| `reference` | Pointers to external resources (URLs, dashboards, tickets) |

---

## The MEMORY.md index

The index loaded into context every session. **One memory per line, no frontmatter**:

```markdown
- [Developer agent identity](project_developer_role.md) — Main development agent identity, behavior rules, session start protocol
- [Verifier agent role](project_verifier_role.md) — Handles independent verification
- [Command queue](reference_command_queue.md) — How to use the SQLite command queue
- [Working-mode auto-stop](feedback_working_mode.md) — The loop stops automatically when all worker queues are empty
```

Rules:

- Before saving, check whether an existing file already holds that fact — **update instead of creating a duplicate**.
- Delete memories that turn out to be wrong.
- Don't store what code / git / config already records (memory is only for what *can't be inferred*).
- A memory is an observation from the time it was written — if it mentions a file, function, or flag, re-confirm against the current code before asserting it.

---

## Role-based agent identity

In multi-agent collaboration, each agent has its own identity as a `project` type memory.
What an identity file contains:

- **Who I am** — Role (development / verification / coordination), scope of responsibility
- **Work principles** — Carry out commands precisely, prove with code, say "I don't know" when you don't, act without asking …
- **Session start behavior** — Check memory → check the queue → process → report
- **Team structure** — Relationships with other agents (who builds and who verifies)

Example templates: [../examples/agents/developer-agent.md](../examples/agents/developer-agent.md) ·
[../examples/agents/verifier-agent.md](../examples/agents/verifier-agent.md)

### The development / verification separation pattern

A common setup is a **producer / verifier separation**:

- **Developer agent** — Designs, implements, and writes. The one that moves the project forward.
- **Verifier agent** — Independently verifies and reviews deliverables. Rejects over-claims. A perspective different from the producer's.

The command queue connects the two: the developer implements, then requests verification with `q.send(to="verifier", ...)`, and
the verifier records PASS/FAIL and the rationale in the `summary` / `findings` of `q.complete()`.

```
 ┌───────────┐   q.send(to="verifier")    ┌──────────┐
 │ Developer │ ─────────────────────────▶ │ Verifier │
 │ (implement)│                           │ (verify) │
 └───────────┘ ◀───────────────────────── └──────────┘
              q.complete(PASS/FAIL, findings)
```

---

Related docs: [working-mode.md](working-mode.md) · [../README.md](../README.md)
