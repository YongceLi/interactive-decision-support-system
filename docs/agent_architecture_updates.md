# Agent Architecture Updates – November 2025

## Overview

This document summarizes the code changes introduced to improve agent latency, reliability, and observability. Each section references the affected files and key line ranges for quick inspection.

## Parallel Intent Analysis & Semantic Parsing

- Files: `idss_agent/core/supervisor.py` (`SupervisorOrchestrator._run_parallel_intent_and_parsing`)  
- Highlights:
  - Introduced a `ThreadPoolExecutor` to run `analyze_request` and `semantic_parser_node` concurrently.
  - Added telemetry spans for both tasks plus the combined wall-clock window.
  - Ensures `_semantic_parsing_done` is set once parsing finishes.

## Incremental Semantic Parsing

- Files: `idss_agent/processing/semantic_parser.py`
- Highlights:
  - Restricts LLM context to the most recent dialogue window (`limits.semantic_parser_history_window`).
  - Adds deterministic merge helpers `_merge_explicit_filters` and `_merge_implicit_preferences`.
  - Returns a copied state object rather than mutating the shared instance so callers can safely operate in parallel.

## Request Analysis Prompt Cache

- Files: `idss_agent/core/request_analyzer.py`
- Highlights:
  - Maintains an LRU cache (size 128) keyed by user input plus lightweight state summary.
  - Cache hits skip an LLM round trip, reducing latency for repeated clarifications.

## Analytical Agent Evidence & Verification

- Files: `idss_agent/agents/analytical.py`
- Highlights:
  - Collects tool outputs (`ToolMessage`) as an evidence buffer.
  - Runs a post-response verifier (reusing the analytical post-process model) to flag unsupported claims and annotate the response with caveats.
  - Persists diagnostics under `state['diagnostics']['analytical']` for downstream inspection.

## Pluggable Recommendation Pipeline

- Files: `idss_agent/processing/recommendation.py`, `idss_agent/processing/providers/*`
- Highlights:
  - Introduces a provider registry (`processing.providers`) so the search backend can be swapped without code edits.
  - Optional vector re-ranking via `rank_local_vehicles_by_similarity` gated by `features.enable_vector_ranker` and `paths.vehicle_embedding_db`.
  - Maintains compatibility with the RapidAPI electronics provider (`RapidApiElectronicsProvider` wrapper).

## Telemetry Instrumentation

- Files: `idss_agent/utils/telemetry.py`, `idss_agent/core/agent.py`, `idss_agent/core/supervisor.py`
- Highlights:
  - Adds `start_span`/`finish_span` helpers to capture duration in milliseconds.
  - `run_agent` now appends a per-turn span, while supervisor captures request-level and stage-level spans.
  - Telemetry is stored in `state['_telemetry']` (list of dicts) to be streamed to clients or persisted.

## Testing Latency Using Web Logs

The web client already emits latency metrics. To compare before vs. after:

1. Capture a baseline sample (pre-change) of the frontend latency logs, e.g., using the existing log aggregation in `web/src/services/logging.ts`.
2. After deploying the updated agent, capture an equivalent sample window (same number of turns or users).
3. For each dataset, compute summary statistics (p50/p90/p99) grouped by `stage` or `span name` (the telemetry spans now propagate to the web payload).
4. Use a simple script or notebook to read the exported CSV/JSON logs and compare deltas; flag regressions greater than an agreed threshold (e.g., >10%).

Example shell command (assuming logs stored as NDJSON with a `latency_ms` field):

```bash
jq -s '
  group_by(.stage) |
  map({
    stage: .[0].stage,
    count: length,
    p50: (map(.latency_ms) | sort | .[(length*0.5)|floor]),
    p90: (map(.latency_ms) | sort | .[(length*0.9)|floor]),
    p99: (map(.latency_ms) | sort | .[(length*0.99)|floor])
  })
' baseline_logs.ndjson
```

Run the same for the post-change dataset and compare the metrics. With the new telemetry spans, you can slice by `intent_analysis`, `semantic_parser`, or the overall `turn` span to confirm the expected latency reductions.




