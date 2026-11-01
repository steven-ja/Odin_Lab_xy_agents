# Synthetic XY Export — governed agent reference

**Status:** Read-only analytical prototype with a CLI, Streamlit dashboard and LangGraph workflow. Not a production financial-advice system.
**As-of date:** 2026-09-29. **Currency:** SEK.

## Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run
from the extracted `xy_agents` directory (Python 3.11+):

```bash
uv sync --extra dashboard --extra test
uv run streamlit run dashboard.py
```

See [README_DASHBOARD.md](README_DASHBOARD.md) for dashboard usage, example
questions, LangGraph topology and UI-specific security boundaries.

## Tests

```bash
uv run pytest -q
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

**Limitations:** This is an offline, rule-driven, evidence-based prototype, not a trained AI agent. Swedish pattern rules do not guarantee detection of paraphrases. Jev remains an unimplemented adapter until its API and data-processing terms are verified. The CLI `--advisor` option is a demonstration of authorization logic, not authentication; a production API must obtain advisor identity from a verified authentication token, enforce database row-level security, and use durable audit storage. Account reconciliation uses reported balances and holdings as recorded, which may have different valuation dates. No suitability decision, investment recommendation, or client update is automated.
