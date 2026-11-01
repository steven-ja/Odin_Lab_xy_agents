# XY Advisory Intelligence — Streamlit + LangGraph

A read-only, permission-scoped analytical **prototype** for the Synthetic XY
financial advisory dataset. Optional local model inference; no CRM writes or cloud API keys.
The workflow uses **real LangGraph `StateGraph` nodes** to coordinate existing
Python data-science and governance logic. The main chat uses a deterministic intent router and report writer; a separate local-model panel provides generated evidence reviews.

## Quick start

Follow the [project quick start](README.md#quick-start) to install dependencies
with uv and launch the dashboard.

Open Streamlit's URL, typically `http://localhost:8501`.
Select the **demo** advisor (R02, R07 or R09), then a household in their
explicit permission list, and ask a question in **Ask the agents**.

Example prompts:

- R02 / H012 — "What is the risk profile conflict and conduct issue?"
- R07 / H018 — "Was there a prompt injection attempt?"
- R09 / H016 — "Show injection security flags"
- R07 / H009 — "Which fees are missing?"
- R07 / H002 — "What suitability data quality issues exist?"

Select **LangGraph execution** to see the *actual compiled graph* (`get_graph`)
and which nodes were executed during the last question. Click **Mermaid source**
to inspect the compiled graph's Mermaid definition.

## Architecture

```mermaid
flowchart LR
    START --> authorize
    authorize --> analyze
    analyze --> portfolio
    portfolio --> transcript
    transcript --> compliance
    compliance --> quality
    quality --> compose
    compose --> verify
    verify --> END
```

- **authorize**: fail-closed household permission gate; no privileged query before authorization.
- **analyze**: immutable, dataset-specific portfolio and evidence analysis; raw notes remain in repository.
- **portfolio**: numerical subset of the validated report.
- **transcript**: timestamped evidence pointers, not raw transcript or embedded instructions.
- **compliance**: risk-profile conflicts, assurances, injection indicators.
- **quality**: missing data, valuation reconciliation and review gaps.
- **compose**: question-dependent, deterministic sourced narrative (no probabilistic claims).
- **verify**: independently reconciles totals and fee coverage; asserts no write actions.

The graph is compiled in `src/xy_agents/graph.py` using `StateGraph`, `START`,
`END`, `add_node`, `add_edge` and `.compile()`. The UI calls `.stream(...,
stream_mode='updates')` to show **actual execution order**. The graph does not
use LangGraph persistence or an LLM; these are explicit, future extensions.

## Dashboard tabs

1. **Overview** — aggregate *authorized* households, portfolio totals and severity distributions.
2. **Household & sources** — holdings, metrics, findings, permission-gated, redacted excerpts.
3. **Ask the agents** — role- and household-scoped chat; evidence citations are dataset pointers.
4. **LangGraph execution** — dynamic compiled graph visualization, node trace and verifier checks.
5. **Audit & governance** — authorization events, prototype security boundaries and requirements.

## Security boundaries

The advisor dropdown simulates an authenticated principal but **is not login**:
any user who can open this demo can choose any advisor. Do not deploy this UI to
real financial clients as-is. See the [production requirements](README.md#critical-production-requirements) for authentication, data protection, audit and deployment controls.

Read permissions are enforced before each analytical read. Raw CRM notes and
transcripts are **never passed into graph state** or a language model; the UI
shows authorized, PII-redacted excerpts only after explicit user action.
Some PII could evade regex redaction: do not use real sensitive transcripts
without a vetted detection and privacy-review pipeline.

Injection screening uses heuristics and is **not a complete prompt-injection
security solution**. It quarantines known test indicators; review required.
The source dataset intentionally contains missing fees, mismatches and
suitability gaps. Missing fees are not silently inferred. Nothing in this
prototype executes customer-profile updates or investment orders.

## Limits

The app uses in-memory session audit logs, read-only generated briefs and
rule-based verified findings. Optional Gemma 2B and Decision 3.0 d3-edge typed decisions are available in a separate review panel; see [local model setup](README.md#local-models). Jev is not integrated.
While this is a valid LangGraph orchestration, the nodes are specialized
analytical services, not self-directed model-backed agents. No vendor privacy
contract or calibrated Swedish model classifier is implied.
