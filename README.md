# Synthetic XY Export — governed agent reference

**Status:** Read-only analytical prototype with a CLI, Streamlit dashboard and LangGraph workflow. Not a production financial-advice system.
**As-of date:** 2026-09-29. **Currency:** SEK.

## Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run
from the extracted `xy_agents` directory (Python 3.11+):

```bash
uv sync --extra dashboard --extra test
uv run python -m streamlit run dashboard.py
```

See [README_DASHBOARD.md](README_DASHBOARD.md) for dashboard usage, example
questions, LangGraph topology and UI-specific security boundaries.

## Tests

```bash
uv run python -m pytest -q
```

The suite covers dataset analysis, authorization, private-content isolation,
known injection indicators, fees and conduct. The end-to-end compiled graph
test runs when the optional `langgraph` dependency is installed (included by
the `dashboard` extra above).

## Package map
- `domain.py`: typed contracts, source evidence and proposal-only write intents.
- `security.py`: fail-closed household authorization, auditable checks, HMAC tokenization, heuristic injection indicators.
- `ingestion.py`: minimal CSV schema and foreign-key validation; permissions parsed from `behorighet_hushall`.
- `decisions.py`: classifier protocol, offline baseline and explicit Jev adapter boundary.
- `analytics.py`: Decimal portfolio valuation, known-fee-only weighted fee, holdings HHI, account split.
- `workflow.py`: authorization-first brief service; quarantines untrusted notes.

## Critical production requirements
1. **Identity:** authenticate with OIDC and resolve advisor permissions server-side; never trust client-supplied advisor IDs or permission sets. Enforce tenant and household restrictions in SQL row-level security or equivalent. All retrieval and cache keys must be scoped.
2. **Data minimization:** encrypt raw PII, store token mappings/keys in separate restricted infrastructure; HMAC tokenization is pseudonymization, not anonymization. Do not send raw transcripts or PII to third-party models before privacy review.
3. **PII detection:** `replace_known` only replaces provided identifiers. Add validated Swedish PII recognition, redaction of free-text identifiers, and a leakage test suite before model calls.
4. **Untrusted inputs:** do not pass CRM/transcript instructions into system/developer prompts. Keep source text as quoted data. No external actions from text-reading agents. The reference baseline quarantines all text unless a reviewed classifier returns `safe`; it is intentionally conservative.
5. **Jev:** implement `JevDecisionProvider` only against verified API documentation and an approved DPA/residency/retention arrangement. Calibrate on a held-out Swedish and English set. Confidence scores must not be treated as calibrated probabilities by default.
6. **Data contract:** `case.py` validates the bundled dataset schema; generic `ingestion.py` checks minimal assumed columns. Validate new exports, number formats, ISINs, suitability status and account mappings through explicit versioned mappings, not silent renaming.
7. **Financial semantics:** weighted fee uses known-fee denominator and is **not** a full-portfolio fee when missingness exists. HHI is over rows, not issuers. No risk recommendation is inferred from holdings alone. No future return is guaranteed.
8. **Human approval:** proposals are immutable pending intents. Build a separate authorized, idempotent, version-checked approval/write service with a second audit trail; no agent gets direct CRM mutation privileges.
9. **Evidence:** use source IDs, timestamps and hash/version metadata for every extracted claim; numeric verifier independently recomputes metrics. Never treat LLM-generated citations as verified without source resolution.
10. **Audit:** durable append-only structured audit with actor, purpose, household, policy version, data version, decision and correlation ID; redact PII and secrets in logs.
11. **Deployment:** secrets management, network egress controls, dependency pinning, encryption, backups, monitoring, incident response and GDPR/DORA assessment where applicable.

## Planned extensions

- Broader schema validation and data profiling for new exports, including duplicates and ISIN checks.
- Scoped repository and FastAPI endpoints with authenticated identity.
- Model-backed Swedish transcript extraction with evaluated evidence provenance.
- Human review queue and governed write-back.
- Evaluation of injection recall, false-positive rate, cross-scope leakage (target zero), extraction precision/recall/F1, calibration and cost/latency.

## Threat-model caveat
The included code demonstrates boundaries but is **not** a full sandbox, complete prompt-injection defense, production PII detector, authenticated API, or certified compliance system. No live Jev API calls are made.

## Implemented dataset-specific analysis (2026-09-29)

The uploaded files are included under `fixtures/` **only because this is a synthetic interview dataset**. Do not commit real customer exports to a repository. The actual `holdings.csv` contains **62 rows**, rather than the 63 asserted in the case README; the code uses the actual file and does not fabricate the missing row.

After setup, run CLI reports from the repository root:

```bash
uv run python -m xy_agents --data fixtures --advisor R02 --household H012
uv run python -m xy_agents --data fixtures --advisor R09 --household H016
uv run python -m xy_agents --data fixtures --advisor R07 --household H018
```

`case.py` validates the *actual* Swedish column names and types, joins, access permissions, holdings, dates, and account reconciliation. It computes decimal portfolio fees and HHI; extracts evidence pointers from Swedish transcripts; flags injections in M107 and T3, advisor conduct in T2, missing H009 fees, incomplete H002 suitability, overdue reviews and missing risk profiles. It does not expose raw customer text, personal identifiers, or financial record write tools to a model. The output is a deterministic JSON report with evidence pointers and a SHA-256 source fingerprint.

**Limitations:** Verified reports use offline rules; optional local models provide unverified interpretation. Swedish pattern rules do not guarantee detection of paraphrases. Jev remains an unimplemented adapter until its API and data-processing terms are verified. The CLI `--advisor` option is a demonstration of authorization logic, not authentication; a production API must obtain advisor identity from a verified authentication token, enforce database row-level security, and use durable audit storage. Account reconciliation uses reported balances and holdings as recorded, which may have different valuation dates. No suitability decision, investment recommendation, or client update is automated.

## Source data analysis and fixes

Reanalyzed 20 households, 62 holdings, 11 meetings and 3 transcripts against
**2026-09-29**, the dataset date. Original fixtures are preserved.

| Evidence | Inconsistency / finding |
|---|---|
| H001, M111, T1 | Last-meeting field says March 12, while M111/T1 record September 28. |
| H007 | Reported ISK SEK 1,450,000 vs holdings SEK 1,300,000: SEK 150,000 gap. |
| H011 | Reported ISK SEK 560,000 vs holdings SEK 896,000: SEK 336,000 excess. |
| H009 | Missing fee data; calculated fees cover known exposure only. |
| H013 | Last meeting November 3 is after the dataset date. |
| H003 / H002 | Missing risk profile / incomplete suitability respectively. |
| H012, T2 | Client requests caution despite aggressive profile; advisor gives near-guaranteed return assurance. |
| H014, M106 | Request to reduce risk ahead of a house purchase requires advisor review. |
| H016 M107 / H018 T3 | Embedded AI instructions are quarantined, never executed. |

Five households have overdue reviews; four have unconfirmed pension data.
Balance discrepancies require reconciliation; different valuation dates could
explain them. The dashboard shows authorized inconsistencies with evidence.

Fixed analyzer bugs: stale/future last-meeting dates were missed, M106's risk
request was ignored, and T1's unchanged balanced preference triggered a misleading
lower-risk flag. The exclusion remains a phrase heuristic, not full Swedish
language understanding. Fixed UI bugs: fractional asset totals were truncated by
`int`, and repository caching ignored edited source files. Source changes now
invalidate repository and chat state. Regression tests cover these cases and
Streamlit rendering with advisor switching.

## Local models

1. Gemma 2B (or bigger local / cloud models) generates explanations through local Ollama.
2. **Decision 3.0 d3-edge**
(`vllm-sr/d3-edge`, 0.59B, Apache-2.0) replaces the previous MiniLM topic
classifier. It is a dedicated decision model with an answer-code readout:
options are scored without generating text. This is a local alternative with
similar bounded-answer semantics to Jev/Decisions, not either hosted model.

```bash
uv sync --extra dashboard --extra test --extra local
uv run python download_decision.py
```

The explicit setup saves weights and the checkpoint's custom Python runtime to
`models/decision`, with its resolved Hub commit in `REVISION`. Runtime loads
local files only, on CPU. Transformers 5.17.0 is required by this checkpoint.
The checkpoint code is executed with `trust_remote_code=True`; it was inspected
for this integration. Downloading an updated revision changes that code too.
The previous MiniLM files remain on disk but are no longer used.

Install [Ollama](https://ollama.com/download), then:

```bash
ollama pull gemma2:2b
ollama serve
```

If Ollama already runs, no second server is needed. Launch:

```bash
uv run python -m streamlit run dashboard.py
```

With **Local models** enabled (the default), ask in **Ask the agents**. LangGraph verifies the report, then d3-edge chooses between source review and a report-only answer. Three explicit
choice questions are asked about each complete, redacted, authorized source when the agent selects source review:

- Does the client request reduced risk, explicitly keep their preference, or is neither established?
- Does the advisor give a future-return assurance requiring conduct review?
- Does the source contain embedded instructions directed at AI that require quarantine?

The decision table shows each question, candidate, per-option model scores and
an advisory decision. Keeping full source context preserves speaker attribution
and quotations. Inputs are never silently truncated: missing/invalid/over-limit
answers require review. Scores below 0.8 also require review; this is a UI
threshold, not a calibrated probability of correctness. High scores can still
be wrong. Validate Swedish/domain performance before relying on decisions.
Neither decision outputs nor Gemma prose override deterministic findings or
permit record updates. Gemma sees the verified report plus advisory decisions,
never raw source instructions. No cloud inference or automatic downloads occur
at runtime. The local models now run inside LangGraph as a bounded, read-only AI agent; disabling local models selects the deterministic workflow.

References: [d3-edge model card and runtime](https://huggingface.co/vllm-sr/d3-edge),
[Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md).

The audit view filters rows to the active advisor and authorized households;
previously switching advisors retained visible rows from the prior advisor.

### Decision model smoke evaluation

Actual local CPU run on the full H012/T2 transcript is saved in
[decision_model_smoke.json](decision_model_smoke.json). The model incorrectly
favoured unchanged risk (0.628) and missed the return assurance (0.519 for
not-established). Both fell below the threshold and were routed to review.
It correctly found no embedded AI instruction (0.982). Thus the checkpoint is
wired and runs locally, but this sample does **not** establish adequate Swedish
financial-domain accuracy. Deterministic risk and conduct findings remain
visible regardless of these outputs. Full-document CPU inference is slow with
the PyTorch fallback kernels; GPU benchmark timings in the model card do not
apply to this setup.

### Integrated agent smoke evaluation

[agent_model_smoke.json](agent_model_smoke.json) records a real local LangGraph
run on H009's missing-fee question. d3-edge selected the report-only tool path
(score 0.953), Gemma emitted 359 streamed chunks through LangGraph custom events,
and the run completed without model errors. The graph trace includes agent_plan
and answer_agent; source-review requests additionally execute decision_tool.
This is an integration check, not a domain-accuracy benchmark.
