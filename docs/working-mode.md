# Working Mode

Working mode is an operating model in which an agent **autonomously and repeatedly processes** the command queue addressed to it.
Without the user issuing every command, the agent polls the queue, processes `pending` commands in priority order, and stops on its own when the queue is empty.

If the command queue is about "what to do right now," working mode is about "by what procedure to carry it through to completion."

---

## Session Start Protocol

The order when entering working mode (or when starting a regular session):

1. **Check global memory** — Load the project memory index (`MEMORY.md`) and reference relevant memories.
   → [agent-memory.md](agent-memory.md)
2. **Check the command queue** — Use `q.check()` or `cmd_q check <agent>` to check my `pending` / `in_progress` commands.
3. **Process by priority** — A direct instruction from the user takes top priority. Otherwise, process the `pending` commands in the queue in priority order (`critical` > `high` > `medium` > `low`).
4. **Report completion** — On completing each command, explicitly record the result (`q.complete`) and report to the user.

---

## Command Processing Loop (single command)

Each command must go through the status transitions:

```
pending  ──start()──▶  in_progress  ──complete()──▶  completed
```

```python
q.start(cmd_id)      # pending → in_progress
# ... do the work: write code, run tests, measure results ...
q.complete(cmd_id, summary=..., detail=..., findings=[...])
```

> ⚠️ **Status transition pitfall.** The UPDATE in `complete()` uses the `WHERE status='in_progress'` condition.
> If you do not go through the `in_progress` transition via `start()`, the status change in `complete()` becomes a **silent NOOP**
> (the `results` row is inserted, but `commands.status` remains `pending`). This is commonly missed when closing out a received command —
> always follow the order **start → work → complete**.

---

## Autonomous Loop and Automatic Stop

When running working mode as a cron/periodic loop (e.g., periodically polling the queue DB), the **stop condition** is key.

On every tick, check the number of incomplete commands of the worker agents:

```sql
SELECT COUNT(*) FROM commands
WHERE to_agent IN (<worker agents>)
  AND status IN ('pending','in_progress');
```

- **If 0** → all workers' queues are empty, so **automatically stop** the loop and report to the user.
- **If greater than 0** → keep the loop running. Even if my own queue is empty, as long as the other worker still has work left, follow-up commands (verification requests, fix requests, etc.) may arrive, so keep waiting.

### Design Notes

- **A simple no-activity counter ("stop after N consecutive idle ticks") is not recommended.** If the interval in which worker A waits for worker B to finish its implementation is counted as "no activity," the loop stops prematurely. Stopping based on the remaining queue avoids this problem.
- **Waiting for a report to reach a superior (boss) is not included in the stop decision** — an unread report (`pending`) is not a reason to keep the loop running. Look **only at the worker queues**.
- If all worker queues are already empty when the loop starts, it stops immediately on the first tick.

---

## Working Principles (common to working mode)

- **Act without asking** — For reversible work, do not ask "Shall I?"; just proceed. Confirm in advance only for destructive / externally public actions.
- **Prove with code** — Do not stop at "it should work." Run it and leave a PASS/FAIL log.
- **Say you don't know when you don't** — Do not pretend to know by guessing. Acknowledge and fix an incorrect claim immediately.
- **Execute commands exactly** — Do what you were told, as you were told. No arbitrary scope expansion. Do not miss any requirement.
- **Report completion explicitly** — What you did and how you verified it. Report a failure as a failure, together with the log.

---

Related documents: [agent-memory.md](agent-memory.md) · [../README.md](../README.md)
