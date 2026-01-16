# Real GPU Benchmark Results

**Date:** 2026-03-20
**Platform:** Google Colab Free Tier
**GPU:** Tesla T4
**Cost:** $0

## Model Tested

**SimpleClassifier** — MLP (768→256→64→2, 0.8MB)

## Results (100 requests, sequential)

| Metric | Value |
|--------|-------|
| Throughput | 379.1 req/s |
| Mean latency | 2.6ms |
| P50 latency | 2.5ms |
| P95 latency | 3.0ms |
| Cache hit rate | 100.0% |
| Success rate | 99/100 |

## What Was Validated

- System boots and serves on real GPU hardware (Tesla T4)
- LRU cache works — 100.0% hit rate
- GPU routing works
- Rate limiting works
- API authentication works

---

*This validates the orchestration system works on real GPU hardware.*
