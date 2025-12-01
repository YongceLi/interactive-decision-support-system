# Review Simulation

Tools for generating persona-based evaluation runs of the interactive decision support system for GPU shopping scenarios.

## Components
- **generate_persona_queries.py**: Builds persona prompts and single-turn user queries (including inferred upper price limits) from enriched GPU review CSVs.
- **run.py**: Evaluates generated personas against recommendation pipelines, renders console UI, and optionally exports detailed metrics and product judgements (with per-attribute checks and confidence).
- **replay_results.py**: Recreates the console UI from an exported CSV and can persist aggregated metrics (precision, diversity, NDCG, satisfied@k, and attribute-level satisfied@k averages).

## Usage

### Generate personas and queries
```bash
python review_simulation/generate_persona_queries.py data/reviews_enriched.csv --output data/personas.csv
```

### Run simulation
```bash
python review_simulation/run.py data/personas.csv --limit 20 --metric-k 20 --export data/persona_results.csv
```
The UI displays per-product attribute checks (price, brand, product name, normalized family, performance tier, and misc preferences), overall satisfaction with rationale, and confidence. Final averages across personas are shown after all rows.

### Replay exported results
```bash
python review_simulation/replay_results.py data/persona_results.csv --metric-k 20 --stats-output data/persona_results_stats.json
```
This recreates the UI from the CSV and saves run-level aggregates (precision, product diversity, NDCG, satisfied@k, and attribute-level satisfied@k averages) to the optional stats path.
