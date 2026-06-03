---
name: curate-topics
description: Curate the Bio-trend biology taxonomy — decide whether new candidate keywords are noise, existing-topic synonyms, new topics, or parked.
---

# curate-topics

The reasoning core between candidate extraction and topic assignment. Run commands
as `PYTHONNOUSERSITE=1 ./env/bin/bio-trend ...` (needs the `[curate]` extra:
`pip install -e '.[curate]'` for scispaCy).

## Procedure

1. **Extract candidates**:
   ```
   bio-trend candidates "<CSV>" --journal <label> --period <YYYY-MM> -o /tmp/candidates.json
   ```
   The payload has `existing_topics` (anchor on these) and `candidates` (most
   frequent first), each with a count and example titles.

2. **Decide every candidate** — one of:
   - `existing` — a synonym/variant of an existing topic (give `topic`).
   - `new` — a genuinely distinct biology theme (count ≥ ~8, coherent examples).
   - `noise` — generic science vocabulary (study, analysis, method, model, tissue…).
   - `other` — real but niche/uncertain; parked, not assigned yet.

3. **Write `/tmp/decision.json`**: `{"decisions": [{"keyword": ..., "action": ..., "topic": ...}, ...]}`.

4. **Apply & verify**:
   ```
   bio-trend curate --dry-run /tmp/decision.json   # preview
   bio-trend curate /tmp/decision.json             # apply (updates config/*.json)
   bio-trend assign "<CSV>"                         # relabel with the new taxonomy
   ```

## Decision principles

- **Anchor on existing taxonomy** — prefer `existing` over `new`.
- **Keywords must be lowercase** — assignment matches case-sensitively against
  lowercased text, so always emit lowercase keywords. Reuse topic labels exactly as
  in `existing_topics`.
- **Be conservative with `new`** — a handful of genuinely new biology topics per
  cycle is normal; use `other` when unsure.
- Biology month buckets are smaller than conference dumps, so counts run lower —
  judge by coherence of examples, not just raw count.
