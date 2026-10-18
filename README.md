# mcp-job-agent

![CI](https://github.com/mdkarimuddin/mcp-job-agent/actions/workflows/ci.yml/badge.svg)

An MCP server and a small tool-using agent for a job-application tracker. The agent can read
the tracker and **propose** edits. A human approves, rejects or rolls back every change from the command line.
Built to show agent engineering with guardrails, an audit trail and tests, not just prompting.

## What it does

Ask questions in plain language:

```
jobagent ask "Which applications have deadlines in the next 7 days?"
jobagent ask "Mark the Fjord Health application as submitted"      # creates a proposal only
jobagent pending                                                   # you review it
jobagent approve 1                                                 # you apply it
jobagent rollback 1                                                # or undo it
```

## Architecture

```
user -> CLI -> agent loop (Anthropic API, max 6 steps, token budget)
                    |  MCP client (stdio)
               MCP server: get_schema, list_applications, upcoming_deadlines,
                           search_applications, propose_update, draft_followup
                    |
               SQLite: read-only connection for reads | pending_changes | audit_log

human-only (CLI, never exposed through MCP): approve, reject, rollback
```

## Guardrails (each one has a test)

| Risk | Control | Test |
|---|---|---|
| Model writes SQL | No SQL tool. Parameterised query templates only | `test_search_is_parameterised` |
| Unwanted writes | Reads use a `mode=ro` SQLite connection | `test_read_connection_cannot_write` |
| Silent edits | Agent can only create a `pending_changes` row; a human applies it | `test_propose_does_not_change_applications` |
| Bad edits | Field allow-list, status enum, ISO dates, length limits | `test_invalid_proposals_are_rejected` |
| Prompt injection via data | Tool text is labelled untrusted in the system prompt; no delete/approve/send tool exists | `test_injected_note_is_returned_as_data_and_changes_nothing`, `test_registered_mcp_tools_match_allow_list` |
| Runaway loops and cost | Step limit, token budget, result truncation | `test_step_limit_stops_a_looping_model`, `test_token_budget_stops_the_run` |
| Untraceable actions | Every tool call goes to `audit_log` with actor, args, summary | `test_audit_log_records_agent_and_human_actions` |
| Email sent by mistake | `draft_followup` returns text only | `test_draft_followup_never_sends` |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export JOBAGENT_DB=data/jobs.db
jobagent init && jobagent import data/sample_applications.csv
export ANTHROPIC_API_KEY=...                            # set in your own shell, never commit it
jobagent ask "What is due in the next 10 days? Today is 2026-10-18."
```

To use your own tracker, run `jobagent import path/to/Applications_Tracker.md` (Markdown pipe tables) or a CSV
with the columns in `data/sample_applications.csv`. The database file is git-ignored.

The MCP server also works from Claude Desktop (or any MCP client). Command: `python -m jobagent.server`
with `JOBAGENT_DB` set.

## Tests and evaluation

```bash
pytest --cov=src          # 37 unit and integration tests, including a real MCP stdio round trip
python eval/run_eval.py   # 10 trace-based cases against the real model (needs ANTHROPIC_API_KEY)
```

`eval/cases.yaml` checks which tools were used, which were forbidden, and key facts in the answer,
including injection, delete-request and missing-data cases. Results are in `docs/EVAL_RESULTS.md`.

## Status and honesty

- The unit and integration tests run in CI on Python 3.10-3.12.
- Model-in-the-loop evaluation: 10/10 cases passed with 0 unsafe actions in one run on 18 Oct 2026
  (see `docs/EVAL_RESULTS.md` for what that does and does not show).
- One user so far (the author). See `docs/LIMITATIONS.md`.
