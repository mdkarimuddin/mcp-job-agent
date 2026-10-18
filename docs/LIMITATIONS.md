# Limitations

- **One user.** The only real user so far is the author. Add other users' feedback here when you have it.
- **Small evaluation.** 10 cases, one run each, written by the author on synthetic data (10/10 passed).
  Treat it as a smoke test of the guardrails, not a robustness claim. See `docs/EVAL_RESULTS.md`.
- **Prompt injection is mitigated, not solved.** The agent has no destructive tools and writes need approval, but a
  model can still be misled into a wrong answer or a bad *proposal*. Human review is the final control.
- **Markdown importer is heuristic.** It guesses status, fit and deadlines from table text; some rows land in the
  wrong status. Check the import, or use the CSV format.
- **Single machine, single user.** SQLite file, no authentication, no multi-tenant access control.
- **Dates.** Deadlines are ISO strings and no time zone is stored.
- **Cost and latency not measured.** Token totals are printed per run; no dashboard.
- **No deployment pipeline.** CI runs lint, tests and a Docker build. There is no automated release or hosted instance.
