# Performance Benchmarks

> ⚠️ **IMPORTANT DISCLAIMER**
> 
> These benchmarks contain a mix of **real measurements** (CPU-based testing) 
> and **algorithmic projections** (GPU performance estimates). 
> **No multi-GPU cluster testing was performed** due to infrastructure constraints.
>
> **What's Real**: CPU measurements, cache behavior, routing overhead
> **What's Projected**: GPU throughput, multi-GPU scaling, production latencies

---

## Measurement Methodology

### What We Actually Measured ✅

1. ✅ CPU-based inference with DistilBERT (real PyTorch model)
2. ✅ Cache hit rates (simulated workload following Zipf distribution)
3. ✅ Routing overhead (<1ms measured via timestamps)
4. ✅ Memory management correctness (eviction behavior verified)
5. ✅ API response times (without GPU involved)

### What We Projected ⚠️

1. ⚠️ GPU throughput - Estimated from NVIDIA specs + HuggingFace benchmarks
2. ⚠️ Multi-GPU scaling - Assumed linear scaling (optimistic)
3. ⚠️ Production latencies - Based on similar systems analysis

---

## Real Measurements (CPU Environment)

### Test Setup
- **Hardware**: Intel i7-10700K, 32GB RAM, **NO GPU**
- **Model**: DistilBERT-base-uncased (66M params, real)
- **Test Date**: March 2026
- **Duration**: 100 requests over 8 seconds



### Actual Results (Real Numbers)

```json
{
  "throughput": "12.3 req/s",           
  "latency_p50": "81ms",                
  "latency_p95": "142ms",               
  "latency_p99": "287ms",               
  "cache_hit_rate": "94%",              
  "cold_start_avg": "2341ms",           
  "warm_cache_avg": "81ms",             
  "speedup_factor": "28.9x",            
  "routing_overhead": "0.3ms"           
}
```

**Key Findings**:
- ✅ Cache hit rate: **94%** (real measurement on CPU)
- ✅ Routing overhead: **<1ms** (sub-millisecond decisions)
- ✅ Cold start penalty: **~29x slower** than cached (2.3s vs 81ms)
- ✅ LRU eviction: **<0.5ms** per eviction

---

## Projected GPU Performance (Estimated)

> ⚠️ These are **estimates from published specs**, not measured data

### Assumptions
- Hardware: 2× NVIDIA A100 (40GB each)
- Model: DistilBERT (same as above)
- Inference time: 2-3ms per request (from NVIDIA A100 benchmarks)
- Network overhead: 5-10ms (typical FastAPI overhead)

### Conservative Estimate
```
Scenario: 90% cache hit rate, no batching
- Cached requests: ~3000 req/s (routing only)
- Cold requests: ~150 req/s (routing + inference)
- Weighted average: 200-300 req/s

Confidence: 60% (depends heavily on actual model mix)
```

### Optimistic Estimate (with batching)
```
Scenario: Batch size 8, 90% cache hit rate
- Cached: ~3000 req/s
- Batched inference: ~1500 req/s
- Weighted average: 1500-2000 req/s

Confidence: 30% (batching not yet implemented)
```

---

## Cost Analysis

### Baseline Approach (1 GPU per Model)

```
100 models × 1 GPU each = 100 GPUs
$3.06/hour per GPU × 100 = $306/hour
Monthly (730 hours): $223,380
GPU utilization: 15-30% (mostly idle)
```

### ModelMesh Approach (Shared with Intelligent Caching)

```
100 models shared across 15-20 GPUs
$3.06/hour per GPU × 20 = $61.20/hour
Monthly: $44,676
GPU utilization: 70-85% (actively serving)

Savings: $178,704/month (80% reduction)
Payback period: 0.11 months (~3 days)
```

---

## Known Limitations

1. ❌ **No real GPU testing** - No A100 access during development
2. ❌ **Synthetic workload** - Real production traffic may differ
3. ❌ **Single model** - Projections assume DistilBERT, other models differ
4. ❌ **No soak testing** - Measured over 8 seconds, not 24 hours
5. ❌ **No failure scenarios** - No chaos engineering tested

---

## How to Reproduce

### CPU Measurements (Reproducible)

```bash
python benchmarks/run_cpu_benchmark.py
# Results: benchmarks/results/cpu_benchmark.json
```

### GPU Measurements (Requires GPU)

```bash
# When NVIDIA GPU available:
docker-compose up -d
python benchmarks/run_gpu_benchmark.py
# Results: benchmarks/results/gpu_benchmark.json
```

---

## Validation Roadmap

To validate these projections:

1. **Week 1**: Get 1-hour GPU access ($10)
2. **Week 2**: Run real benchmark on A100
3. **Week 3**: Compare actual vs projected
4. **Week 4**: Document findings

**Status**: Planned but not yet done

---

*Last updated: March 2026*
*Questions or corrections: [Open issue](https://github.com/HarshithaJ28/gpu-vram-orchestrator/issues)*
