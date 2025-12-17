# GPU VRAM Orchestrator - Architecture

## System Overview

The GPU VRAM Orchestrator is a sophisticated system for managing GPU memory efficiently in multi-model inference environments. It uses predictive loading, intelligent scheduling, and LRU caching to maximize GPU utilization while minimizing latency.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI REST API                         │
│  /health, /status, /predict, /models, /metrics, /stats      │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
    ┌───▼────────┐         ┌─────────▼────┐
    │  Scheduler │         │ Predictor    │
    │            │         │              │
    │- Select    │         │- Learn       │
    │  best GPU  │         │  patterns    │
    │- Multi-    │         │- Predict     │
    │  factor    │         │  next models │
    │  scoring   │         │- Preload     │
    └───┬────────┘         └──────┬───────┘
        │                         │
        └──────────────┬──────────┘
                       │
        ┌──────────────▼────────────────┐
        │   GPU Model Cache (LRU)       │
        │                              │
        │- Memory tracking             │
        │- Pinned models               │
        │- Eviction policy             │
        └──────────────┬────────────────┘
                       │
        ┌──────────────▼────────────────┐
        │   GPU Detector & Mem Manager  │
        │                              │
        │- Detect GPUs                │
        │- Monitor memory              │
        │- Allocate/deallocate        │
        └──────────────┬────────────────┘
                       │
        ┌──────────────▼────────────────┐
        │    PyTorch CUDA/NVIDIA GPU   │
        │                              │
        │- Model execution             │
        │- Memory management           │
        └───────────────────────────────┘
```

## Core Components

### 1. GPU Detector (`gpu/detector.py`)
**Purpose**: Detect available GPU hardware and monitor real-time metrics

**Key Functions**:
- `detect_gpus()` - Discover all CUDA-capable GPUs
- `get_free_memory_mb(gpu_id)` - Query free GPU memory
- `get_utilization_percent(gpu_id)` - Monitor GPU load
- `get_gpu_count()` - Return total GPUs available

**Critical Path**: Must never crash on initialization (tested)

### 2. Memory Manager (`gpu/memory_manager.py`)
**Purpose**: Track GPU memory allocation and prevent over-subscription

**Key Functions**:
- `allocate(gpu_id, size_mb, model_id)` - Reserve memory
- `deallocate(gpu_id, model_id)` - Release memory
- `can_allocate(gpu_id, size_mb)` - Check availability
- `get_stats(gpu_id)` - Memory statistics

**Critical Path**: Never exceeds available memory (tested)

### 3. GPU Scheduler (`scheduler/gpu_scheduler.py`)
**Purpose**: Intelligently select the best GPU for each model

**Scoring Algorithm** (Multi-Factor):
```
Score = 0.50 × Memory_Score + 0.30 × Load_Score + 0.20 × Affinity_Score

Memory_Score:
  - 100%  if free_memory >= required_memory
  - 50%   if free_memory >= 0.5 × required_memory
  - 0%    otherwise

Load_Score:
  - 100%  if pending_requests = 0
  - Decreases with pending queue length
  - Avoids bottleneck GPUs

Affinity_Score:
  - High if similar models loaded (fraud-detection family)
  - Colocates related models for efficiency
  - Reduces context switching
```

**Category Extraction**: `fraud-detection-v2` → `fraud-detection`

### 4. GPU Cache with LRU Eviction (`cache/gpu_cache.py`)
**Purpose**: Keep frequently used models loaded for fastest inference

**Key Features**:
- **LRU Policy**: Least Recently Used models evicted first
- **Pinned Models**: Protected from eviction (e.g., critical inference models)
- **Thread-Safe**: Uses RLock for concurrent access
- **Memory Tracking**: Prevents cache from exceeding GPU capacity

**Algorithm**:
```
When cache is full and new model arrives:
  1. Check if model already in cache → use existing
  2. Pre-allocate memory for new model
  3. Evict least-recently-used unpinned models
  4. Load new model
  5. Update access timestamps
```

### 5. Predictive Preloader (`predictor/`)
**Purpose**: Predict upcoming model requests and pre-warm GPU cache

**Pattern Types**:
- **Time-of-Day**: 24-hour histogram (e.g., fraud detection peaks at 9 AM)
- **Day-of-Week**: 7-day pattern (e.g., high volume weekdays)
- **Sequential**: Model A frequently followed by Model B

**Prediction Algorithm**:
```
current_time = 14:30 Friday
predictions = {
  "fraud-detection": 0.92,     # High confidence (time-of-day pattern)
  "recommendation": 0.78,      # Medium confidence (sequential)
  "image-classifier": 0.45     # Low confidence (rare at this time)
}
```

**Pre-warming Strategy**:
- Runs every 60 seconds
- Loads predicted models without displacing cached ones
- Graceful degradation if GPU memory full

### 6. Metrics Collection (`monitoring/metrics.py`)
**Purpose**: Export performance metrics for observability

**Metrics Tracked**:
- Cache: hits, misses, hit rate, evictions
- GPU: utilization %, models loaded per GPU
- Scheduler: selection time (p95, p99)
- Latency: inference, model loading
- Cost: GPU hours, estimated savings

**Dual Mode**:
- **Prometheus**: Native Prometheus client for production
- **In-Memory Fallback**: For CI/testing environments

### 7. Benchmark Suite (`monitoring/benchmarks.py`)
**Purpose**: Validate performance against SLOs

**Performance Targets**:
- Cold start latency: < 3000 ms
- Cache hit rate: > 75%
- Scheduler speed: < 1 ms
- GPU utilization: > 70%
- Prediction accuracy: > 70%
- Cost reduction: > 75%

## Data Flow

### Request Processing Pipeline
```
1. Client Request
   ↓
2. FastAPI Endpoint (/predict)
   ↓
3. Scheduler selects best GPU
   - Scores all available GPUs
   - Returns selected GPU ID
   ↓
4. Cache Check
   - Is model loaded on selected GPU?
   ↓
5a. Cache HIT
   - Return loaded model
   - Record hit metric
   - Update LRU timestamp
   ↓
5b. Cache MISS
   - Predictor records access pattern
   - Check available GPU memory
   - Load model from disk
   - Record latency metric
   ↓
6. Model Inference
   - Execute on selected GPU
   - Return predictions
   ↓
7. Metrics Recording
   - Cache hit/miss
   - Inference latency
   - GPU utilization update
```

### Background Processes
```
Preloader (runs every 60s)
├─ Get current time pattern
├─ Predict next models
├─ Check GPU memory
└─ Pre-load predicted models (safe)

Metrics Export (every 60s)
├─ Aggregate metrics
├─ Export to Prometheus
└─ Update dashboards (Grafana)
```

## Thread Safety

All components use `RLock` (Reentrant Lock) for thread safety:
- GPUCache: Protects OrderedDict during LRU operations
- MemoryManager: Serializes allocation/deallocation
- MetricsCollector: Ensures atomic metric updates
- Scheduler: Thread-safe GPU selection

## Performance Characteristics

### Latencies (p95 measurements)
- GPU Detection: < 10 ms
- Memory Query: < 5 ms
- Scheduler Selection: < 1 ms (target: < 1 ms)
- Cache Lookup: < 1 ms
- Model Loading: 100-1000 ms (depends on model size)

### Memory Overhead
- Per GPU: ~50 MB for orchestrator memory
- Per Model Entry: ~1 MB (metadata)
- Cache Manager: ~10 MB

### Throughput
- Single GPU: 100-500 inferences/second (depending on model)
- Multi-GPU: Linear scaling up to network limits

## Deployment Architecture

### Development
- Docker Compose with GPU support
- Prometheus + Grafana stack
- AlertManager for notifications
- Local GPU device passthrough

### Production (Kubernetes)
- Deployment controller (2-10 replicas)
- HPA (Horizontal Pod Autoscaler)
- PDB (Pod Disruption Budget) for high availability
- Service with metrics endpoint for Prometheus scraping
- PersistentVolume for model cache across pod restarts

### Monitoring
- Prometheus scrapes metrics every 15 seconds
- Grafana dashboards for visualization
- AlertManager sends critical alerts
- ELK stack integration ready (logs to stdout)

## Failure Modes & Recovery

### GPU Device Failure
- **Detection**: Health check fails
- **Recovery**: Pod restart via Kubernetes
- **Impact**: Brief service disruption, other replicas continue

### Memory Exhaustion
- **Detection**: Memory allocation fails
- **Recovery**: Trigger aggressive LRU eviction
- **Impact**: Evicted models must reload (latency spike)

### Scheduler Crash
- **Detection**: Request timeout
- **Recovery**: Timeout + retry with different GPU
- **Impact**: Single request fails, subsequent requests succeed

### Network Partition
- **Detection**: Prometheus scrape fails
- **Recovery**: Automatic reconnection
- **Impact**: Missing metrics points (dashboard gap)

## Optimization Opportunities

1. **GPU Memory Pinning**: Reduce copy latency for large models
2. **Model Sharding**: Split large models across multiple GPUs
3. **Quantization**: Reduce memory footprint of cached models
4. **Compression**: Compress models in cache using zstandard
5. **ML-based Scheduling**: Use DQN for adaptive scheduling weights
6. **NUMA Awareness**: Consider CPU-GPU NUMA affinity
