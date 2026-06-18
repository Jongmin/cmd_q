# cmd_q

SQLite-based inter-agent command queue. Multiple agent sessions exchange commands through a SQLite file. WAL mode makes concurrent reads/writes safe.

It is organized around three pillars for multi-agent collaboration:

1. **Command queue** — passing commands between agents (this README) · SQLite + WAL
2. **Working mode** — autonomously process the queue in a loop and exit when the queue is empty → [docs/working-mode.md](docs/working-mode.md)
3. **Agent memory** — identity, role, and preferences that persist across sessions → [docs/agent-memory.md](docs/agent-memory.md)

## Installation

```bash
pip install git+https://github.com/Jongmin/cmd_q.git
```

Or pin a version:

```bash
pip install "git+https://github.com/Jongmin/cmd_q.git@v0.1.0"
```

## DB path

Priority:

1. `CommandQueue(agent, db_path=...)` argument
2. Environment variable `CMD_Q_DB`
3. `~/.cmd_q/queue.db` (directory created automatically)

To use a different DB per project, separate the environment variable.

```bash
export CMD_Q_DB=/path/to/project/.cmd_q.db
```

## Python API

```python
from cmd_q import CommandQueue

q = CommandQueue("alice")

# Check my pending commands
pending = q.check()
# → [{"id": 27, "from_agent": "bob", "title": "...", "priority": "high", "status": "pending"}, ...]

# Command details
cmd = q.get(27)
# → {"id": 27, "body": "...", "ref_files": ["src/test.py"], ...}

# Start task → complete
q.start(27)
q.complete(27,
    summary="All verifications passed",
    detail="| # | Item | Result |\n...",
    findings=[
        {"severity": "P0", "title": "Bug found", "file": "x.py", "line": 42},
    ],
)

# Send a command to another agent
q.send(
    to="charlie",
    title="Review DB schema",
    body="### Change log\n...",
    priority="high",       # critical, high, medium, low
    ref_files=["src/db/schema.py"],
)

# Cancel
q.cancel(27, reason="Removed due to requirement change")

# Query
q.history(days=7)
q.history(agent="alice")
q.search("schema")
q.get_result(27)
q.stats()
```

## CLI

```bash
cmd_q check alice           # Check pending commands
cmd_q history 7             # History for the last 7 days
cmd_q search "schema"       # Keyword search
cmd_q stats                 # Per-agent statistics
cmd_q get 27                # Command details + result
cmd_q archive 30            # Clean up completed items older than 30 days
```

## Schema

### commands
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | autoincrement |
| from_agent | TEXT | Sending agent |
| to_agent | TEXT | Receiving agent |
| title | TEXT | Title |
| body | TEXT | Body (Markdown recommended) |
| priority | TEXT | critical / high / medium / low |
| status | TEXT | pending / in_progress / completed / cancelled |
| ref_files | TEXT(JSON) | List of related file paths |
| cancel_reason | TEXT | Cancellation reason |
| created_at / started_at / completed_at | DATETIME | |

### results
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| command_id | INTEGER FK | commands.id |
| agent | TEXT | Agent that wrote the result |
| summary | TEXT | 1-2 line summary |
| detail | TEXT | Details (Markdown) |
| findings | TEXT(JSON) | `[{severity, title, file, line}, ...]` |

## Usage rules guide (adopt in each project)

State the following in your project rules file (e.g., AGENTS.md):

- At session start, run `q.check()` to check my pending commands
- Use `q.send()` when requesting work from another agent
- Always call `q.complete()` after finishing a review/verification
- When you receive an instruction like "ask X to do Y" → summarize the work you just did and include it in the body of `q.send()`

## Working mode and agent memory

The command queue is only a delivery mechanism. Actual multi-agent operation is defined by two documents together:

- **[docs/working-mode.md](docs/working-mode.md)** — autonomous queue processing loop, session start protocol,
  state transition pitfalls (calling `complete` without `start` is a silent NOOP), automatic shutdown based on remaining queue volume.
- **[docs/agent-memory.md](docs/agent-memory.md)** — file structure of memory that persists across sessions,
  frontmatter schema, four types (user / feedback / project / reference), `MEMORY.md` index,
  role-based agent identity (development / verification separation pattern).

Agent identity templates:
[examples/agents/developer-agent.md](examples/agents/developer-agent.md) ·
[examples/agents/verifier-agent.md](examples/agents/verifier-agent.md)

## License

MIT
