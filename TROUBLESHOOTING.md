# Troubleshooting Guide

Comprehensive troubleshooting and common issues for GPU VRAM Orchestrator.

## Quick Diagnostics

### 1. Check System Health

```bash
# Application health
curl http://localhost:8000/health

# Full status
curl http://localhost:8000/status | jq

# GPU status
nvidia-smi

# Docker status (if containerized)
docker ps | grep gpu-vram
```

### 2. View Logs

```bash
# Local development
tail -f backend/logs/app.log

# Docker
docker logs gpu-vram-orchestrator -f

# Kubernetes
kubectl logs deployment/gpu-vram-orchestrator -f
kubectl logs deployment/gpu-vram-orchestrator --previous  # Previous pod
```

### 3. Common Commands

```bash
# Port forward Kubernetes service
kubectl port-forward svc/gpu-vram-orchestrator 8000:80

# Check Prometheus metrics
curl http://localhost:9090/api/v1/targets

# Test API endpoint
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"model_id":"fraud-detection-v1","input_data":{"features":[0.1,0.2,0.3,0.4,0.5]}}'
```

---

## Issue Categories

### A. GPU & CUDA Issues

#### Issue: No CUDA devices detected

**Symptoms:**
```
RuntimeError: No CUDA devices detected
CUDA device count: 0
```

**Diagnosis:**
```bash
# Check NVIDIA driver
nvidia-smi

# Check CUDA availability
python -c "import torch; print(torch.cuda.is_available())"

# Check device count
python -c "import torch; print(torch.cuda.device_count())"
```

**Solutions:**

1. **Install/Update NVIDIA Driver**
   ```bash
   # Ubuntu 22.04
   sudo apt-get update
   sudo apt-get install nvidia-driver-535
   sudo reboot

   # CentOS/RHEL
   sudo yum install nvidia-driver-cuda-12
   sudo reboot
   ```

2. **Verify CUDA Installation**
   ```bash
   # Check CUDA toolkit
   nvcc --version
   
   # If not installed:
   # https://developer.nvidia.com/cuda-toolkit/
   ```

3. **Update PyTorch**
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
   ```

4. **Check Power/BIOS Settings**
   - Ensure GPUs are enabled in BIOS
   - Check device power supply
   - Verify no thermal throttling

---

#### Issue: Out of Memory (OOM) errors

**Symptoms:**
```
RuntimeError: CUDA out of memory. Tried to allocate 2.5 GiB
torch.cuda.OutOfMemoryError
```

**Diagnosis:**
```bash
# Check GPU memory
nvidia-smi

# Monitor memory in real-time
watch -n 1 nvidia-smi

# Check cache memory
curl http://localhost:8000/status | jq '.cache'

# Check which models are loaded
curl http://localhost:8000/models | jq '.[] | {name, size_mb, gpu_id}'
```

**Solutions:**

1. **Reduce Cache Size**
   ```bash
   # Edit environment variable
   export CACHE_SIZE_MB=20000  # Lower from 24000
   
   # Or in Kubernetes
   kubectl set env deployment/gpu-vram-orchestrator \
     CACHE_SIZE_MB=20000 --record
   ```

2. **Increase GPU Memory Reservation**
   ```bash
   # Reserve less system memory
   export RESERVED_MEMORY_MB=1000  # Lower from 2000
   ```

3. **Pin and Optimize Models**
   ```bash
   # Pin critical models only
   curl -X POST http://localhost:8000/models/fraud-detection-v1/pin
   
   # Unload unused models
   curl -X DELETE http://localhost:8000/models/unused-model
   ```

4. **Add More GPUs**
   - Verify GPU passthrough in Kubernetes: `kubectl describe node`
   - Check NVIDIA GPU Operator: `kubectl get pods -A | grep nvidia`

5. **Use Model Quantization** (planned feature)
   ```python
   # Future: Quantize models to reduce memory
   quantized_model = quantize(model, bits=8)
   ```

---

#### Issue: GPU underutilized

**Symptoms:**
```
GPU Utilization: 15%
GPU Memory: 20%
```

**Diagnosis:**
```bash
# Check GPU utilization
nvidia-smi dmon -s pucvmet -i 0  # Live monitoring

# Check API throughput
curl http://localhost:8000/stats/scheduler | jq

# Check cache hit rate
curl http://localhost:8000/status | jq '.cache.hit_rate'
```

**Solutions:**

1. **Increase Batch Size**
   ```python
   # In your inference code
   results = client.batch_predict(
       model_id="model",
       batch_size=64  # Increase from 32
   )
   ```

2. **Optimize Scheduler Weights**
   ```bash
   # Reduce memory weight, increase load weight
   export SCHEDULER_MEMORY_WEIGHT=0.3
   export SCHEDULER_LOAD_WEIGHT=0.5
   ```

3. **Preload Models Aggressively**
   ```python
   # Pin frequently used models
   for model in ['fraud-detection-v1', 'recommendation-v2']:
       client.load_model(model)
       client.pin_model(model)
   ```

4. **Enable Prediction Preloading**
   ```bash
   export PREDICTION_ENABLED=true
   export PREDICTION_MIN_CONFIDENCE=0.5
   ```

---

### B. Performance Issues

#### Issue: High latency (> 200ms)

**Symptoms:**
```
P99 latency: 450ms
Average latency: 280ms
Cache hit rate: 45%
```

**Diagnosis:**
```bash
# Profile latency breakdown
curl http://localhost:8000/predict \
  -d '{"model_id":"fraud-detection-v1","input_data":{"features":[0.1,0.2,0.3,0.4,0.5]},"return_timing":true}' \
  | jq '.timing_ms'

# Output:
# {
#   "scheduler": 0.45,
#   "load": 125.20,
#   "inference": 98.10,
#   "total": 223.75
# }
```

**Solutions:**

1. **Model Load Time High (load > 100ms)**
   ```bash
   # Pre-load and pin models
   curl -X POST http://localhost:8000/models/fraud-detection-v1/load?gpu_id=0
   curl -X POST http://localhost:8000/models/fraud-detection-v1/pin
   
   # Increase model cache size
   export CACHE_SIZE_MB=26000
   ```

2. **Scheduler Time High (scheduler > 1ms)**
   ```bash
   # Increase scheduler workers
   export SCHEDULER_WORKERS=8
   
   # Reduce affinity weight (less computation)
   export SCHEDULER_AFFINITY_WEIGHT=0.1
   ```

3. **Inference Time High (inference > 150ms)**
   ```bash
   # Model computation issue - check if model is too large
   # Consider model quantization or faster model variant
   
   # Scale to more GPUs
   kubectl scale deployment gpu-vram-orchestrator --replicas=4
   ```

4. **Network Latency Issue**
   ```bash
   # If using remote API
   # Check network: mtr -c 100 api.example.com
   # Consider local caching
   ```

---

#### Issue: High cache miss rate (< 60%)

**Symptoms:**
```
Cache hit rate: 35%
Models kept evicting
Load time per prediction: 150ms
```

**Diagnosis:**
```bash
# Get cache statistics
curl http://localhost:8000/stats/cache | jq

# Check model access patterns
curl http://localhost:8000/stats/predictor | jq '.top_models'

# Monitor evictions
curl http://localhost:8000/status | jq '.cache.evictions'
```

**Solutions:**

1. **Increase Cache Size**
   ```bash
   export CACHE_SIZE_MB=28000  # 28GB (keep 2GB reserve)
   # Restart deployment
   kubectl rollout restart deployment/gpu-vram-orchestrator
   ```

2. **Pin Critical Models**
   ```bash
   # Identify top models
   models = ['fraud-detection-v1', 'sentiment-analysis-v2']
   for model in models:
       client.pin_model(model)  # Won't be evicted
   ```

3. **Improve Prediction Accuracy**
   ```bash
   # Increase history window
   export PREDICTION_WINDOW_HOURS=48  # Learn from 2 days
   
   # Lower confidence threshold
   export PREDICTION_MIN_CONFIDENCE=0.50  # More preloading
   ```

4. **Tune Eviction Policy**
   ```bash
   # Current: LRU (Least Recently Used)
   # Planned: LFU (Least Frequently Used)
   # Planned: ARC (Adaptive Replacement Cache)
   ```

---

### C. Memory Management Issues

#### Issue: Memory fragmentation

**Symptoms:**
```
Total memory: 24000 MB
Used: 18000 MB
Allocatable: 2000 MB (fragmented in 5 chunks of 400 MB each)
Model load fails: Needs 3000 MB contiguous
```

**Solutions:**

1. **Clear Cache (Emergency)**
   ```bash
   curl -X DELETE http://localhost:8000/cache/clear
   
   # In code
   client.cache.clear()
   ```

2. **Graceful Restart**
   ```bash
   # Kubernetes - triggers pod replacement
   kubectl rollout restart deployment/gpu-vram-orchestrator
   
   # Docker
   docker restart gpu-vram-orchestrator
   ```

3. **Reduce Model Sizes**
   ```python
   # Use quantized models
   model = load_model('fraud-detection-v1-quantized')  # 50% smaller
   ```

---

#### Issue: Memory leaks

**Symptoms:**
```
Memory usage gradually increases
After 24 hours: 95% utilization
Models aren't being released
```

**Diagnosis:**
```bash
# Monitor memory over time
python -c "
import subprocess
import time
import matplotlib.pyplot as plt

times, mems = [], []
for i in range(60):  # 60 minutes
    result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used',
                            '--format=csv,noheader,nounits'], 
                          capture_output=True, text=True)
    mem = float(result.stdout.strip())
    mems.append(mem)
    times.append(i)
    time.sleep(60)

plt.plot(times, mems)
plt.xlabel('Time (minutes)')
plt.ylabel('GPU Memory (MB)')
plt.savefig('memory_trend.png')
"
```

**Solutions:**

1. **Set Memory Limits**
   ```bash
   # In Kubernetes
   resources:
     limits:
       memory: 4Gi
   ```

2. **Disable Model Caching in Tests**
   ```python
   # Only cache in production
   cache = GPUModelCache(use_prometheus=False)  # Avoid metric leaks
   ```

3. **Restart Pod Periodically**
   ```bash
   # Kubernetes CronJob for weekly restart
   kubectl create cronjob restart-gpu-orchestrator \
     --image=bitnami/kubectl \
     --schedule="0 2 * * 0" \
     -- kubectl rollout restart deployment/gpu-vram-orchestrator
   ```

---

### D. API Issues

#### Issue: API timeouts

**Symptoms:**
```
Reading from host timed out
Connect timeout
Max retries exceeded
```

**Solutions:**

1. **Increase Timeout**
   ```python
   from src.client.api_client import GPUOrchestratorClient
   
   client = GPUOrchestratorClient(
       "http://localhost:8000",
       timeout=30  # Increase from default
   )
   ```

2. **Check Server Response**
   ```bash
   # Test endpoint
   time curl http://localhost:8000/health
   
   # Check server load
   curl http://localhost:8000/status | jq '.server'
   ```

3. **Scale Up**
   ```bash
   # Add more replicas
   kubectl scale deployment gpu-vram-orchestrator --replicas=5
   ```

---

#### Issue: 503 Service Unavailable

**Symptoms:**
```
HTTP 503 Service Temporarily Unavailable
readinessProbe failed
```

**Diagnosis:**
```bash
# Check pod readiness
kubectl describe pod <pod-name>
kubectl logs <pod-name> | tail -50

# Check metrics endpoint
curl http://localhost:8001/metrics
```

**Solutions:**

1. **Increase Startup Time**
   ```yaml
   # In K8s deployment
   readinessProbe:
     initialDelaySeconds: 30  # Increase from 10
     periodSeconds: 5
   ```

2. **Check Prometheus Connection**
   ```bash
   # If Prometheus unavailable, app may fail
   # Test Prometheus
   curl http://localhost:9090/-/healthy
   ```

3. **Restart Pod**
   ```bash
   kubectl delete pod <pod-name>  # Auto-restart via deployment
   ```

---

### E. Deployment Issues

#### Issue: Docker build fails

**Symptoms:**
```
ERROR: failed to solve with frontend dockerfile.v0
torch installation fails
CUDA compatibility error
```

**Solutions:**

1. **Check CUDA/PyTorch Compatibility**
   ```bash
   # Verify in Docker
   docker build --build-arg CUDA_VERSION=11.8 -t gpu-vram:latest .
   ```

2. **Update Base Image**
   ```dockerfile
   # In Dockerfile
   FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04  # Update to newer CUDA
   RUN pip install torch==2.1.0 --index-url https://download.pytorch.org/whl/cu121
   ```

---

#### Issue: Kubernetes pod won't start

**Symptoms:**
```
imagePullBackOff
CrashLoopBackOff
Pending state
```

**Diagnosis:**
```bash
# Describe pod for events
kubectl describe pod gpu-vram-orchestrator-xxx

# Check node resources
kubectl describe nodes
kubectl top nodes

# Check image
kubectl get pods -o json | jq '.items[0].status.containerStatuses'
```

**Solutions:**

1. **Fix Image Pull**
   ```bash
   # Wrong registry
   kubectl set image deployment/gpu-vram-orchestrator \
     gpu-vram=your-registry/gpu-vram:latest

   # Add image pull secret
   kubectl create secret docker-registry regcred \
     --docker-server=<registry> \
     --docker-username=user \
     --docker-password=pass
   ```

2. **Insufficient Resources**
   ```bash
   # Check GPU availability
   kubectl get nodes -L nvidia.com/gpu
   
   # Reduce GPU requirement
   kubectl set resources deployment/gpu-vram-orchestrator \
     --limits=nvidia.com/gpu=1
   ```

3. **Fix Startup Command**
   ```yaml
   # In values.yaml
   command: ["python", "-m", "uvicorn", "src.app:app"]
   args: ["--host", "0.0.0.0", "--port", "8000"]
   ```

---

### F. Monitoring Issues

#### Issue: Prometheus metrics not updating

**Symptoms:**
```
/metrics endpoint empty
Grafana dashboard shows no data
Last scrape: 5 minutes ago
```

**Diagnosis:**
```bash
# Check metrics endpoint
curl http://localhost:8001/metrics | head -20

# Check Prometheus job
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[]'

# Check scrape logs
curl http://localhost:9090/api/v1/query?query=up
```

**Solutions:**

1. **Enable Prometheus**
   ```bash
   export PROMETHEUS_ENABLED=true
   export PROMETHEUS_PORT=8001
   ```

2. **Fix Prometheus Config**
   ```yaml
   # In prometheus.yml
   scrape_configs:
     - job_name: 'gpu-orchestrator'
       static_configs:
         - targets: ['localhost:8001']
   ```

3. **Restart Prometheus**
   ```bash
   docker restart prometheus
   # or
   kubectl rollout restart deployment prometheus
   ```

---

#### Issue: High Prometheus cardinality

**Symptoms:**
```
Prometheus slow
Out of memory
Query timeout
```

**Solutions:**

```yaml
# Add metric relabeling in prometheus.yml
scrape_configs:
  - job_name: 'gpu-orchestrator'
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: 'expensive_metric'
        action: drop
```

---

### G. Integration Issues

#### Issue: K8s to Prometheus communication

**Symptoms:**
```
Grafana: No data source
Prometheus: Target DOWN
scrape error: connection refused
```

**Solutions:**

```bash
# Verify network policy
kubectl get networkpolicies

# Test connectivity from pod
kubectl run -it debug --image=curlimages/curl -- sh
curl http://prometheus:9090

# Fix DNS
kubectl get services -A | grep prometheus
kubectl exec -it deployment/gpu-vram-orchestrator -- \
  curl http://prometheus.monitoring.svc.cluster.local:9090
```

---

### H. Recovery Procedures

#### Clean restart after crash

```bash
# 1. Stop all pods
kubectl delete deployment gpu-vram-orchestrator
kubectl delete pvc gpu-vram-orchestrator-cache  # If using PVC

# 2. Clear state
redis-cli FLUSHDB  # If using Redis for distributed cache

# 3. Restart
kubectl apply -f kubernetes/
```

#### Emergency cache clear

```bash
# Last resort - lose all cached models
curl -X DELETE http://localhost:8000/cache/clear

# Or via Python
from src.cache import GPUModelCache
cache = GPUModelCache()
cache.clear_all()
```

---

## Performance Tuning Checklist

- [ ] GPU drivers updated to latest
- [ ] CUDA version matches PyTorch
- [ ] Cache size fits available GPU memory
- [ ] Scheduler weights tuned for your workload
- [ ] Critical models pinned
- [ ] Prediction confidence threshold appropriate
- [ ] Prometheus scrape interval optimized (15s-60s)
- [ ] Log level set to INFO (not DEBUG)
- [ ] Resource limits configured in K8s
- [ ] Monitoring alerts set up

---

## Getting Help

1. **Check logs**: `kubectl logs -f deployment/gpu-vram-orchestrator`
2. **Review status**: `curl http://localhost:8000/status | jq`
3. **GitHub Issues**: https://github.com/HarshithaJ28/gpu-vram-orchestrator/issues
4. **Discussions**: https://github.com/HarshithaJ28/gpu-vram-orchestrator/discussions

---

### Emergency Contact

For production issues in critical environments, ensure:
- [ ] Production monitoring configured
- [ ] Alerting rules active
- [ ] Runbooks documented
- [ ] Escalation path defined
- [ ] Backup strategy in place
