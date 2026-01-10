# GPU VRAM Orchestrator

[![Tests](https://github.com/HarshithaJ28/gpu-vram-orchestrator/workflows/Tests/badge.svg)](https://github.com/HarshithaJ28/gpu-vram-orchestrator/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Intelligent GPU memory orchestration for multi-model inference environments. Maximizes GPU utilization through predictive loading, LRU caching, and multi-factor scheduling.

## Features

- **🚀 Intelligent Scheduling**: Multi-factor GPU selection (memory, load, affinity)
- **💾 Smart Caching**: LRU cache with model pinning to prevent eviction
- **🔮 Predictive Loading**: Statistical access pattern prediction
- **📊 Observable**: Prometheus metrics, Grafana dashboards, performance benchmarks
- **⚙️ Kubernetes Ready**: Full K8s manifests with HPA and pod disruption budgets
- **🐳 Docker Support**: Production-ready Dockerfile and docker-compose stack
- **📈 Scalable**: Auto-scaling from 2-10 replicas based on load
- **🛡️ Reliable**: Thread-safe operations, graceful error recovery
- **📚 Well-Documented**: Comprehensive API, deployment, and architecture guides

## Quick Start

### Local Development

```bash
# Clone repository
git clone https://github.com/HarshithaJ28/gpu-vram-orchestrator.git
cd gpu-vram-orchestrator

# Install dependencies
pip install -r requirements.txt

# Run tests
cd backend
python -m pytest tests/ -v

# Start server
python -m uvicorn src.app:app --host 0.0.0.0 --port 8000

# View API docs
# Open: http://localhost:8000/docs
```

### Docker Deployment

```bash
# Build image
docker build -f Dockerfile -t gpu-vram-orchestrator:latest .

# Run with docker-compose (includes Prometheus + Grafana)
docker-compose up -d

# Access services
# API: http://localhost:8000
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin/admin)
```

### Kubernetes Deployment

```bash
# Apply manifests
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/deployment.yaml
kubectl apply -f kubernetes/service.yaml

# Port forward for testing
kubectl port-forward svc/gpu-vram-orchestrator 8000:80

# Check status
kubectl get pods -l app=gpu-vram-orchestrator
kubectl logs -f deployment/gpu-vram-orchestrator
```

### Helm Deployment

```bash
# Install using Helm
helm install gpu-orchestrator ./helm/gpu-vram-orchestrator \
  --set image.tag=latest \
  --set replicas=3

# Upgrade configuration
helm upgrade gpu-orchestrator ./helm/gpu-vram-orchestrator \
  --set cache.size_mb=28000
```

## Architecture

### System Overview

```
┌──────────────────────────────────────┐
│     FastAPI REST API                 │
│  /predict /status /metrics /models   │
└──────────────┬───────────────────────┘
               │
      ┌────────┴───────────┐
      │                    │
   ┌──▼─────┐        ┌────▼──────┐
   │Scheduler│        │Predictor  │
   │         │        │           │
   │- Multi- │        │- Learn    │
   │  factor │        │  patterns │
   │  scoring│        │- Preload  │
   └────┬────┘        └─────┬─────┘
        │                   │
        └────────┬──────────┘
                 │
        ┌────────▼──────────┐
        │  GPU Cache (LRU)  │
        │                  │
        │- Models loaded   │
        │- Pinned models   │
        │- Eviction policy │
        └────────┬──────────┘
                 │
        ┌────────▼──────────────┐
        │ GPU Memory Manager    │
        │                      │
        │- Allocation tracking │
        │- Memory validation   │
        └────────┬──────────────┘
                 │
        ┌────────▼──────────────┐
        │  PyTorch/NVIDIA GPUs  │
        │                      │
        │- Model execution     │
        │- Memory management   │
        └───────────────────────┘
```

## API Example

```python
from src.client.api_client import GPUOrchestratorClient

client = GPUOrchestratorClient("http://localhost:8000")

# Check system status
status = client.status()
print(f"Available GPUs: {status['gpus']['count']}")
print(f"Cache hit rate: {status['cache']['hit_rate']:.2%}")

# Run inference
result = client.predict(
    model_id="fraud-detection-v2",
    input_data={"features": [0.1, 0.2, 0.3, 0.4, 0.5]},
    return_timing=True
)
print(f"Prediction: {result['predictions']}")
print(f"GPU ID: {result['gpu_id']}")
print(f"Latency: {result['timing_ms']['total']:.2f}ms")

# Get metrics
metrics = client.metrics(format='json')
print(f"Cache hits: {metrics['cache_hits']}")
print(f"GPU utilization: {metrics['gpu_utilization']}")
```

## Performance

### CPU Benchmark Results (Measured)

Hardware: Intel i7-10700K, 32GB RAM (no GPU)
Model: DistilBERT-base-uncased

| Metric | Measured Value | Notes |
|--------|----------------|-------|
| **Throughput** | 12.3 req/s | CPU-limited (no GPU) |
| **P95 Latency (cached)** | 142ms | Cached inference path |
| **Cold Start Latency** | 2,341ms | Initial model load to CPU |
| **Warm Cache Latency** | 81ms | Model already loaded |
| **Cache Hit Rate** | 94% | Zipf distribution workload |
| **Speedup (cached vs cold)** | 28.9× | 2341ms / 81ms |

> ⚠️ **Note**: These are CPU measurements. See [BENCHMARKS.md](BENCHMARKS.md) for GPU projections and detailed methodology.

### GPU Performance (Projected)

Based on algorithmic analysis + NVIDIA A100 specifications:

| Metric | Projected (2× A100) | Basis |
|--------|---------------------|-------|
| **Throughput** | 200-300 req/s | Algorithm analysis + GPU specs |
| **P95 Latency (cached)** | 40-60ms | Routing (0.3ms) + inference (2-3ms) + network overhead |
| **Cold Start Latency** | 100-150ms | Model load from disk to GPU |
| **Cache Hit Rate** | 90-95% | Expected with Zipf workload |
| **GPU Cost Savings** | 80-85% | 100 models on 15-20 GPUs vs 100 GPUs |

> ⚠️ **Validation Required**: Deploy to cloud GPU instance for actual measurements.

See [benchmarks/](benchmarks/) for reproducible test scripts and [BENCHMARKS.md](BENCHMARKS.md) for complete analysis.

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test class
pytest tests/test_gpu_cache.py::TestGPUModelCache -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run integration tests
pytest tests/test_integration.py -v
```

**Test Coverage**: 143 passing tests
- Phase 1: GPU Detection & Memory Manager (13 tests)
- Phase 2: Scheduler (21 tests)
- Phase 3: Cache & Eviction (24 tests)
- Phase 4: Predictor & Preloader (21 tests)
- Phase 5: Metrics & Benchmarks (30 tests)
- Phase 6: Integration Tests (14 tests)

## Monitoring

### Prometheus Metrics

Access at `http://localhost:9090`

Key metrics:
- `gpu_cache_hits_total` - Total cache hits
- `gpu_cache_misses_total` - Total cache misses
- `gpu_utilization_percent` - GPU memory utilization
- `scheduler_selection_time_ms` - GPU selection latency
- `inference_latency_ms` - Model inference time
- `model_load_time_ms` - Model loading time

### Grafana Dashboards

Access at `http://localhost:3000` (admin/admin)

Pre-built dashboards:
- System Health: CPU, memory, GPU metrics
- Cache Performance: Hit rate, evictions, memory
- Scheduler Analysis: Selection time, GPU distribution
- Prediction Accuracy: Model prediction success rate
- Cost Analysis: GPU hours, estimated savings

## Configuration

### Environment Variables

```bash
# GPU Configuration
GPU_MAX_MEMORY_FRACTION=0.9          # Use 90% of GPU memory
GPU_ALLOWED_IDS=0,1,2,3             # Specific GPUs to use

# Application
CACHE_SIZE_MB=24000                 # 24 GB cache per GPU
SCHEDULER_WORKERS=4                 # Thread pool size
APP_MAX_CONNECTIONS=1000            # Max concurrent connections

# Monitoring
PROMETHEUS_ENABLED=true             # Enable metrics
LOG_LEVEL=INFO                      # Log verbosity
```

### Kubernetes ConfigMap

Edit `kubernetes/configmap.yaml` to customize:
- Cache size
- Scheduler weights (memory, load, affinity)
- Prediction settings
- Monitoring intervals

## Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design, components, data flows
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Setup guide for dev/Docker/K8s, scaling, troubleshooting
- **[API.md](API.md)** - Complete REST API reference with code examples
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development guidelines

## Examples

See `examples/` directory for:
- `basic_inference.py` - Simple prediction example
- `batch_processing.py` - Batch inference with metrics
- `model_management.py` - Loading/pinning/unloading models
- `monitoring_queries.py` - Prometheus query examples
- `notebooks/demo.ipynb` - Interactive Jupyter notebook

## Load Testing

Generate realistic load with k6:

```bash
# Install k6
brew install k6  # macOS
# or https://k6.io/docs/getting-started/installation/

# Run load test (1000 requests, 10 concurrent)
k6 run load_tests/inference_load_test.js

# Run spike test
k6 run load_tests/spike_test.js
```

## Production Checklist

- [ ] Review DEPLOYMENT.md for production setup
- [ ] Configure K8s manifests for your environment
- [ ] Set up monitoring and alerting
- [ ] Enable API authentication
- [ ] Configure GPUs (NVIDIA GPU operator installed)
- [ ] Set resource limits and requests
- [ ] Test failover procedures
- [ ] Set up log aggregation (ELK/Splunk)
- [ ] Enable HTTPS/TLS for API
- [ ] Configure backup strategy for model cache

## Performance Tuning

### Memory Optimization

```bash
# Adjust cache size based on GPU memory
# V100 (24GB):  CACHE_SIZE_MB=22000  (reserve 2GB)
# A100 (40GB):  CACHE_SIZE_MB=38000  (reserve 2GB)
# H100 (48GB):  CACHE_SIZE_MB=46000  (reserve 2GB)
```

### Scheduler Tuning

```python
# In kubernetes/configmap.yaml
scheduler_memory_weight: "0.5"      # 50% - prioritize memory availability
scheduler_load_weight: "0.3"        # 30% - avoid congestion
scheduler_affinity_weight: "0.2"    # 20% - colocate similar models
```

### Prediction Tuning

```bash
PREDICTION_WINDOW_HOURS=24          # Learn from last 24 hours
PREDICTION_MIN_CONFIDENCE=0.60      # Confidence threshold for preloading
```

## Troubleshooting

### Low Cache Hit Rate

```bash
# Check if models are being preloaded
curl http://localhost:8000/stats/predictor

# Increase prediction confidence or history window
# Edit kubernetes/configmap.yaml or set env vars
```

### High Latency

```bash
# Check GPU memory pressure
curl http://localhost:8000/status

# Check scheduler performance
curl http://localhost:8000/stats/scheduler

# Consider increasing cache size or pod replicas
```

### Out of Memory

```bash
# Reduce cache size
CACHE_SIZE_MB=20000

# Enable more aggressive eviction
# Or scale up to more GPUs
```

See [DEPLOYMENT.md](DEPLOYMENT.md#troubleshooting) for more detailed troubleshooting.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:
- Development setup
- Code style
- Testing requirements
- Pull request process
- Reporting bugs

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

## Citation

If you use GPU VRAM Orchestrator in your research or production system, please cite:

```bibtex
@software{gpu_vram_orchestrator_2025,
  title={GPU VRAM Orchestrator: Intelligent Memory Management for Multi-Model Inference},
  author={Sharma, Harshitha},
  year={2025},
  url={https://github.com/HarshithaJ28/gpu-vram-orchestrator}
}
```

## Support

- **Documentation**: [ARCHITECTURE.md](ARCHITECTURE.md), [DEPLOYMENT.md](DEPLOYMENT.md), [API.md](API.md)
- **Issues**: [GitHub Issues](https://github.com/HarshithaJ28/gpu-vram-orchestrator/issues)
- **Discussions**: [GitHub Discussions](https://github.com/HarshithaJ28/gpu-vram-orchestrator/discussions)

## Roadmap

- [ ] Advanced RL-based scheduler using DQN
- [ ] Model quantization and compression
- [ ] Distributed GPU orchestration
- [ ] WebSocket streaming API
- [ ] Model ensemble support
- [ ] Cost prediction and optimization
- [ ] Compliance monitoring (data residency, governance)

---

**Built with ❤️ for efficient GPU resource management**
