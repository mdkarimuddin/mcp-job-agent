# Design decisions

**No SQL tool for the model.** A text-to-SQL tool is flexible but turns every prompt injection into a possible
write or data leak. The tracker has a handful of questions people actually ask, so each is a parameterised tool.

**Propose, then approve.** Writes are two-step. The agent creates a `pending_changes` row that stores the previous
values; a human applies it from the CLI. This keeps rollback trivial and makes unsafe-action rate measurable (target 0).

**Approve, reject and rollback are not MCP tools.** The safest tool is the one the model cannot call. The allow-list
is asserted in a test against the live MCP registry, so adding a tool by accident fails CI.

**Read-only connection for queries.** Defence in depth: even a bug in a read tool cannot modify data.

**LLM behind a small interface.** `run_agent` takes any object with `complete()`. Unit tests use a scripted fake,
so the loop, limits and error handling are tested without network or keys; `AnthropicLLM` is a thin adapter.

**SQLite.** One user, one file, no server. Concurrency and multi-user access are out of scope (see limitations).

**Pinned `mcp<2`.** MCP SDK 2.x renamed the server API; v1 is pinned until the project migrates.

**Tool errors go back to the model.** A failed call returns `is_error` text so the model can recover or explain,
instead of crashing the loop.
