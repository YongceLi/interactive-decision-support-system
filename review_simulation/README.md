# Review Simulation Toolkit (Electronics)

This package mirrors the **`recommendation_testing`** branch workflow for the
electronics domain. It converts raw PC part reviews into persona-rich test cases
and runs single-turn evaluations against `scripts/test_recommendation_methods.py`.

## Workflow

1. **Enrich reviews**
   ```bash
   python scripts/review_enricher.py data/reviews raw_enriched.csv
   ```
   - Input CSV columns: `Brand | Product | Norm_Product | Review | Rating | Date | Source`
   - Extracts `mentioned_like`, `mentioned_dislike`, `mentioned_setup`
   - Derives persona fields: performance tier, newness (1–10), price range, openness-to-alternative (1–10)
   - Builds explicit/implicit preference JSON blocks and canonical queries

2. **Evaluate single-turn recommendations**
   ```bash
   python - <<'PY'
   from review_simulation.evaluator import run_single_turn_evaluations
   run_single_turn_evaluations('raw_enriched.csv', 'evaluation.csv', method='1')
   PY
   ```
   - Pipes each generated query into Method 1 or Method 2
   - Captures first recommended product (`product_name`, `product_brand`, `price`, `_vector_score`)
   - Scores alignment vs persona brand/product focus and saves CSV for downstream analysis

3. **Visualize** (optional)
   ```bash
   streamlit run review_simulation/ui/app.py -- --dataset raw_enriched.csv --results evaluation.csv
   ```
   - Sidebar lets you jump between personas
   - Main panel shows persona summary, explicit/implicit preferences, mentioned likes/dislikes, and top recommendation diagnostics

## Module overview

| File | Description |
| --- | --- |
| `review_simulation/enrichment.py` | Deterministic heuristics for persona creation, mentions, and query generation |
| `review_simulation/dataset.py` | Load/save helpers for CSV datasets with nested JSON |
| `review_simulation/evaluator.py` | Feeds personas into `test_recommendation_methods.py` pipelines |
| `review_simulation/ui/app.py` | Lightweight Streamlit dashboard for reviewing personas & evaluation outputs |

The toolkit ensures **product name, brand, and price** replace the older
make/model/year logic from the vehicle-focused prototype while still surfacing
explicit/implicit preferences and `_vector_score` values in the UI.
