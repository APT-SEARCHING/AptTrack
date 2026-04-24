# Scraper Robustness Retro (Phases 1–4)

> **Status**: template — fill in numbers after post-rollout audit runs.
> Run commands:
> ```
> python dev/audit.py > audit-pre-robustness.txt      # before deploy
> python dev/audit.py > audit-post-robustness.txt     # after 24h cron cycle
> python dev/coverage_report.py --days 1 > coverage-post-robustness.txt
> python dev/coverage_report.py --days 1 --per-apt > per-apt-post.txt
> ```

---

## Coverage delta

| Metric | Pre | Post | Target |
|--------|-----|------|--------|
| Successful scrapes (% of runs) | ___ | ___ | ≥ 85% |
| platform_direct (% of runs) | ___ | ___ | ≥ 30% |
| LLM agent activations (% of runs) | ___ | ___ | < 5% |
| Daily LLM cost | ___ | ___ | < $0.20 |
| PlanPriceHistory rows/day | ___ | ___ | ≈ 90 |
| Plans with sqft coverage (%) | ___ | ___ | ≥ 60% |
| Plans with clean names (%) | ___ | ___ | ≥ 90% |

---

## Per-phase contribution

| Phase | What it did | Key metric |
|-------|-------------|------------|
| Phase 1 (platform adapters) | JonahDigital / FatWin / AvalonBay / Windsor / LeaseStar / SightMap / Greystar / RentCafe / GenericDetail | ___ apts handled |
| Phase 2 (UniversalDOMExtractor) | Generic DOM fallback for unseen card layouts | ___ apts handled |
| Phase 3 (data_source_type) | Skips unscrapeable sites, honest frontend UI | ___ sites marked |
| Phase 4 (adapter_name telemetry) | Per-adapter observability, cost attribution | enables this table |

---

## What's still failing

Fill in from `per-apt-post.txt` failures section:

| Apt | City | Outcome | Decision |
|-----|------|---------|----------|
| | | | LLM path / mark unscrapeable / new adapter (only if ≥3 share pattern) |

---

## Residual adapter candidates

Only list if ≥3 failing sites share the same DOM pattern that UniversalDOMExtractor can't catch.
Otherwise: mark unscrapeable or accept LLM fallback.

| Pattern | Sites | Action |
|---------|-------|--------|
| _none yet_ | | |

---

## Cost notes

- Pre-robustness daily cost: $___
- Post-robustness daily cost: $___
- Estimated annual saving at current scrape cadence: $___
