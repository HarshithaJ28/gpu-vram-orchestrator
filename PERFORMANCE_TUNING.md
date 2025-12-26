# Performance Tuning Guide

Optimize GPU VRAM Orchestrator for your specific workload.

## Baseline Performance

First, establish baseline metrics before tuning:

```bash
# Run baseline load test
k6 run load_tests/inference_load_test.js --vus=20 --duration=5m

# Record metrics from Prometheus at end
curl 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=latency:p99:5m' | jq

# Cache hit rate
curl 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=cache:hit_rate:5m * 100' | jq

# GPU utilization
curl 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=gpu:memory_utilization:5m' | jq
```

Document baseline:
- P50/P95/P99 latency: _______________
- Cache hit rate: _______________
- GPU utilization: _______________
- Error rate: _______________
- Throughput: _______________

## 1. Cache Optimization

### Increase Cache Size

Cache size directly impacts hit rate and model load latency.

```bash
# Current: 24GB (24000 MB)
# Increase for higher hit rate

# V100 (24GB GPU):
export CACHE_SIZE_MB=22000  # Reserve 2GB for system

# A100 (40GB GPU):
export CACHE_SIZE_MB=38000  # Reserve 2GB

# H100 (48GB GPU):  
export CACHE_SIZE_MB=46000  # Reserve 2GB

# Kubernetes
kubectl set env deployment/gpu-vram-orchestrator \
  CACHE_SIZE_MB=40000 --record

# Docker
docker exec gpu-vram-orchestrator \
  env CACHE_SIZE_MB=40000
```

**Expected Impact**:
- Cache hit rate: +5-15%
- P99 latency: -20-30ms
- Memory usage: +16GB

### Pin Critical Models

Prevent frequently-used models from being evicted:

```python
from src.client.api_client import GPUOrchestratorClient

client = GPUOrchestratorClient("http://localhost:8000")

# Identify top 3 models
models = ['fraud-detection-v1', 'sentiment-v2', 'recommendation-v1']

for model in models:
    client.pin_model(model)
    print(f"Pinned {model}")
```

**Expected Impact**:
- Cache hit rate: +10-25%
- Predictable latency: ✓
- Memory wasted: 3-5GB per pinned model

### Optimize Eviction Policy

Current: LRU (Least Recently Used)
Future: LFU (Least Frequently Used), ARC

```bash
# Monitor evictions
watch -n 5 'curl -s http://localhost:8000/status | jq ".cache.evictions"'

# If evictions > 100/min, increase cache or adjust weights
```

## 2. Scheduler Optimization

### Tune Scheduler Weights

Balance GPU selection based on your workload pattern:

#### For Memory-Intensive Workloads
```bash
export SCHEDULER_MEMORY_WEIGHT=0.7    # 70% - prioritize space
export SCHEDULER_LOAD_WEIGHT=0.2      # 20%
export SCHEDULER_AFFINITY_WEIGHT=0.1  # 10% - don't care about colocation
```

Expected: Better model loading, fewer evictions

#### For Latency-Sensitive Workloads
```bash
export SCHEDULER_MEMORY_WEIGHT=0.3    # 30%
export SCHEDULER_LOAD_WEIGHT=0.5      # 50% - balance load
export SCHEDULER_AFFINITY_WEIGHT=0.2  # 20% - spread across GPUs
```

Expected: Lower latency variance, better distribution

#### For Throughput Optimization
```bash
export SCHEDULER_MEMORY_WEIGHT=0.4    # 40%
export SCHEDULER_LOAD_WEIGHT=0.4      # 40% - keep balanced
export SCHEDULER_AFFINITY_WEIGHT=0.2  # 20% - colocate similar
```

Expected: Maximize GPU utilization, high throughput

### Increase Scheduler Threads

More threads = faster GPU selection, higher CPU usage:

```bash
# Current: 4 workers
export SCHEDULER_WORKERS=8

# Monitor CPU usage
kubectl top pod -n gpu-orchestrator

# If CPU < 30%, increase more
export SCHEDULER_WORKERS=12
```

**Expected Impact**:
- Selection latency: -20-40%
- CPU usage: +2-5%

## 3. Predictor Optimization

### Increase Prediction History Window

More history = better accuracy, higher memory:

```bash
# Current: 24 hours
export PREDICTION_WINDOW_HOURS=48

# For rapid model changes:
export PREDICTION_WINDOW_HOURS=12

# For stable workloads:
export PREDICTION_WINDOW_HOURS=72
```

**Expected Impact**:
- Prediction accuracy: +5-10% (with more data)
- Preload effectiveness: +3-8%
- Memory: +10-20MB per hour increase

### Adjust Prediction Confidence Threshold

Lower threshold = more preloading, higher cache churn:

```bash
# Current: 60% confidence
export PREDICTION_MIN_CONFIDENCE=0.50  # More aggressive

# For conservative preloading:
export PREDICTION_MIN_CONFIDENCE=0.75  # Less preloading

# Monitor prediction accuracy
curl http://localhost:8000/stats/predictor | jq '.accuracy'
```

**Expected Impact**:
- Cache hit rate: +5-15% (aggressive)
- Wasted preloads: +10-20%
- Load time: -50-100ms for hits

## 4. Multi-GPU Optimization

### Enable GPU Affinity

Improve cache locality by keeping related models on same GPU:

```python
# Load related models on same GPU
client.load_model('fraud-detection-v1', gpu_id=0)
client.load_model('fraud-detection-v2', gpu_id=0)
client.load_model('fraud-detection-ensemble', gpu_id=0)

# Set affinity
client.set_model_affinity('fraud-detection-v1', preferred_gpus=[0])
```

**Expected Impact**:
- Cache locality: Improved
- P2P transfers: Reduced (if using NVLink)

### Enable Peer-to-Peer (P2P) for Multi-GPU

```bash
# Check P2P capability
nvidia-smi topo -p2p

# NVLink available: Extremely fast GPU-GPU transfer
# PCIe Cascade Lake: Moderate speed (~10GB/s)
```

If using distributed cache (Redis):
```bash
# P2P benefits across GPUs
client = GPUOrchestratorClient(
    cache_backend='redis',  # Future feature
    p2p_enabled=True
)
```

## 5. API Gateway Optimization

### Connection Pooling

For client-side optimization:

```python
from src.client.api_client import GPUOrchestratorClient
import aiohttp

# Connection pooling (async)
connector = aiohttp.TCPConnector(limit_per_host=100, limit=1000)
client = GPUOrchestratorClient(
    connector=connector,
    timeout=10
)
```

### Request Batching

Batch multiple predictions:

```python
# Instead of N individual requests
for item in items:
    client.predict(item)  # N network roundtrips

# Use batch endpoint
results = client.batch_predict(
    model_id='model',
    items=items,
    batch_size=32
)  # 1 or fewer roundtrips
```

**Expected Impact**:
- Throughput: +3-5x
- Latency: +10-20% (due to batching)
- Network overhead: -90%

## 6. Container Optimization

### Resource Limits

Balance between performance and isolation:

```yaml
resources:
  requests:
    memory: 2Gi
    cpu: 1
  limits:
    memory: 4Gi
    cpu: 2
```

Monitor and adjust:
```bash
# Check if hitting limits
kubectl top pod gpu-vram-orchestrator

# If CPU throttled:
#   Increase cpu limit
# If OOM:
#   Increase memory limit
# If neither, reduce for better packing
```

### Run on Performance Nodes

For latency-sensitive deployments:

```yaml
nodeSelector:
  instance-type: c5.2xlarge  # Compute optimized
  # OR
  workload: high-performance
```

## 7. Monitoring and Profiling

### Enable Detailed Metrics

```bash
# Set log level to DEBUG (warning: verbose)
export LOG_LEVEL=DEBUG

# Profile specific code path
python -c "
import cProfile
import pstats
from src.scheduler import GPUScheduler

profiler = cProfile.Profile()
profiler.enable()

scheduler = GPUScheduler(num_gpus=4)
for _ in range(10000):
    scheduler.select_gpu({'available': [20000, 15000, 25000, 18000]})

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
"
```

### Track Performance Regressions

Automated benchmarking:

```bash
# Run benchmark before code change
python examples/performance_benchmarks.py > baseline.txt

# Make code changes

# Run benchmark after
python examples/performance_benchmarks.py > current.txt

# Compare
diff baseline.txt current.txt
```

## 8. Workload-Specific Tuning

### Real-time Inference (Fraud Detection)

Priority: Latency < Resource usage

```bash
export SCHEDULER_MEMORY_WEIGHT=0.2
export SCHEDULER_LOAD_WEIGHT=0.6  # Spread to avoid hotspots
export SCHEDULER_AFFINITY_WEIGHT=0.2

export PREDICTION_MIN_CONFIDENCE=0.75  # Conservative preloading
export CACHE_SIZE_MB=22000  # Smaller cache, faster eviction

# Pin fraud models
models = ['fraud-v1', 'fraud-v2', 'fraud-ensemble']
for model in models:
    client.pin_model(model)
```

Expected: P99 latency < 100ms, predictable

### Batch Processing (Daily Reports)

Priority: Throughput > Latency variation

```bash
export SCHEDULER_MEMORY_WEIGHT=0.5
export SCHEDULER_LOAD_WEIGHT=0.3
export SCHEDULER_AFFINITY_WEIGHT=0.2  # Colocate similar

export PREDICTION_MIN_CONFIDENCE=0.5  # Aggressive preloading
export CACHE_SIZE_MB=40000  # Large cache, fewer reloads

# Use batch API
results = client.batch_predict(
    model_id='model',
    items=items,
    batch_size=128  # Large batches
)
```

Expected: 10,000+ predictions/minute

### Research/Development (Experimentation)

Priority: Flexibility > Performance

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Smaller cache for experimentation
export CACHE_SIZE_MB=5000

# Disable pinning
client = GPUOrchestratorClient()
# models auto-evict based on usage
```

## Tuning Checklist

Priority Order:

1. **High Impact, Easy**
   - [ ] Pin critical models
   - [ ] Increase cache size
   - [ ] Tune scheduler weights for workload

2. **High Impact, Moderate Effort**
   - [ ] Adjust prediction confidence
   - [ ] Increase scheduler workers
   - [ ] Enable batch API

3. **Moderate Impact, Moderate Effort**
   - [ ] Fine-tune prediction history
   - [ ] Optimize connection pooling
   - [ ] Set up performance monitoring

4. **Specialized Optimizations**
   - [ ] Enable P2P transfers
   - [ ] Custom eviction policy
   - [ ] Model quantization (future)

## A/B Testing Framework

Compare two tuning approaches:

```bash
# Setup two deployments
kubectl apply -f deployment-tuning-a.yaml
kubectl apply -f deployment-tuning-b.yaml

# Route 50% traffic to each
kubectl set traffic deployment-a=50 -n gpu-orchestrator
kubectl set traffic deployment-b=50 -n gpu-orchestrator

# Collect metrics for 1 hour
# Compare via Prometheus/Grafana

# Deploy winner
kubectl apply -f deployment-winner.yaml
```

## Performance Regression Testing

Add to CI pipeline:

```bash
# Run on every commit
k6 run load_tests/inference_load_test.js \
  --threshold 'http_req_duration{staticAsset:true}p(95)<500' \
  --threshold 'http_req_failed<0.1'

# Fail build if thresholds exceeded
```

## Escalation Path

If performance goals not met after tuning:

1. **Investigate Bottleneck**
   ```bash
   # Profile to find limiting factor
   python -c "... profiling code ..."
   ```

2. **Review Architecture Docs**
   - See [ARCHITECTURE.md](../ARCHITECTURE.md)

3. **Consider Scaling**
   - Add more GPUs
   - Distribute to multiple nodes
   - Use distributed cache

4. **Contact Support**
   - Open GitHub issue with metrics
   - Include performance profile
   - Describe workload characteristics

---

### Additional Resources

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System design details
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - Common issues
- [API.md](../API.md) - API reference
- Email: support@example.com
