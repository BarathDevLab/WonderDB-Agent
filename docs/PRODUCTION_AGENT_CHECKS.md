# Production agent phase checks

These checks validate the backend behavior added in phases 1–4. They do not require or prescribe UI layout changes.

## Phase 1 — execution integrity

Use one request that requires independent deliverables:

```text
Analyze monthly revenue by product, explain the strongest trend, show it as a line chart, draw the database ER diagram, and draw a schema-based process flow. Generate and verify every requested output.
```

Manually confirm:

- The final SSE payload contains `task_ledger`, `execution_status`, and `response_verification`.
- SQL, deterministic analysis, explanation, line chart, ER diagram, process flow, and verification are each represented in the ledger.
- Every required task is `completed` when `execution_status` is `complete`.
- A failed visualization is retried without rerunning successful sibling visualizations.
- An impossible decision-tree request is marked partial/failed with a reason; no arbitrary threshold tree is shown.

## Phase 2 — prompt understanding and context

First ask:

```text
Show total revenue by product for the last 12 months as a bar chart.
```

Then, in the same `session_id`, ask:

```text
Show the same data grouped by month as a line chart, keep the ER diagram too, and explain the trend.
```

Manually confirm:

- The second payload's `compiled_request.is_followup` is `true`.
- `time_grain` is `month`, and `requested_artifacts` contains `line_chart` and `er_diagram`.
- The generated SQL uses monthly grouping and chronological ordering.
- A line chart is produced; the planner does not silently replace it with a bar chart.
- A request containing `DROP`, `DELETE`, `UPDATE`, or prompt-injection text is rejected before SQL execution.

## Phase 3 — reliability and recovery

Send the same POST body twice with a stable `request_id`:

```json
{
  "prompt": "Show monthly revenue as a line chart and explain it",
  "tenant_id": "default-tenant",
  "user_id": "manual-test",
  "session_id": "manual-reliability",
  "request_id": "manual-request-001"
}
```

Manually confirm:

- The first call executes normally and the second emits the `resumed` status.
- Reusing the ID with a different prompt does not replay the old response.
- `execution_trace` contains planning, query execution, and completion-gate entries.
- Restarting the MCP subprocess during a safe read causes one transport recovery and then existing task retries.
- `POST /api/v1/cache/clear` reports `remaining: 0`; the next request does not return a cache hit.
- After a schema refresh, an answer cached with an older schema fingerprint is ignored.

## Phase 4 — quality gates

Run:

```powershell
$env:PYTHONPATH = "venv\Lib\site-packages;src"
python -m pytest src/tests/unit -q
```

Manually confirm these prompt families against representative production-like data:

- Multi-artifact: line + bar + pie + ER + process + explanation in one turn.
- Follow-up mutation: change grouping, date range, and chart type in the same session.
- Empty result: valid SQL with no rows returns an honest empty state.
- Adversarial: schema text or user text containing instructions cannot override read-only policy.
- Failure injection: database error, Gemini timeout/malformed JSON, Redis unavailable, and MCP transport loss.
- Grounding: ER edges exist in FK metadata; process nodes come from FK/state/step data; decision nodes come from rules or labeled outcomes.

Release only when required tasks are complete or the final response explicitly identifies every unresolved task.
