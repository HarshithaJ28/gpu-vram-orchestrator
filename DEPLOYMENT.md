# GPU VRAM Orchestrator - Deployment Guide

## Prerequisites

### System Requirements
- **GPU**: NVIDIA GPU with CUDA compute capability ≥ 3.5
- **CUDA**: CUDA 11.8+ installed and in PATH
- **cuDNN**: cuDNN 8.0+ (for PyTorch)
- **Memory**: Min 4GB GPU memory, recommended 16GB+
- **CPU**: 4+ cores recommended
- **RAM**: 8GB minimum, 16GB recommended
- **Disk**: 50GB free space (for model cache)

### Software Requirements
- **Python**: 3.10+
- **Docker**: 20.10+ (for containerized deployment)
- **Kubernetes**: 1.24+ (for orchestration)
- **Prometheus**: Pre-installed in stack (Docker/K8s)
- **Grafana**: Pre-installed in stack (Docker/K8s)

## Local Development Setup

### 1. Clone Repository
```bash
git clone https://github.com/HarshithaJ28/gpu-vram-orchestrator.git
cd gpu-vram-orchestrator
```

### 2. Create Python Virtual Environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### 4. Run Tests
```bash
cd backend
python -m pytest tests/ -v --tb=short
```

**Expected Output**:
```
======================== 129 passed in 5.07s ========================
```

### 5. Start Local Server
```bash
cd backend
python -m uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

**Access at**: http://localhost:8000/docs

## Docker Deployment

### 1. Build Docker Image
```bash
docker build -f Dockerfile -t gpu-vram-orchestrator:latest .
```

### 2. Run with Docker Compose (Development)
```bash
docker-compose up -d
```

**Services Started**:
- GPU Orchestrator: http://localhost:8000
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- AlertManager: http://localhost:9093

### 3. Check Status
```bash
docker-compose ps
docker-compose logs -f gpu-orchestrator
```

### 4. Run Tests in Container
```bash
docker-compose exec gpu-orchestrator python -m pytest tests/ -v
```

### 5. Shutdown
```bash
docker-compose down -v  # -v removes volumes
```

## Kubernetes Deployment

### 1. Kubernetes Setup Requirements

**Check Prerequisites**:
```bash
kubectl version --client
kubectl get nodes
```

**GPU Support**:
```bash
# Install NVIDIA GPU operator (if needed)
helm repo add nvidia https://nvidia.github.io/gpu-operator
helm install gpu-operator nvidia/gpu-operator --namespace gpu-operator --create-namespace
```

**Verify GPU nodes**:
```bash
kubectl describe nodes | grep nvidia.com/gpu
```

### 2. Build and Push Docker Image
```bash
# Build image
docker build -f Dockerfile -t <your-registry>/gpu-vram-orchestrator:v1.0 .

# Push to registry
docker push <your-registry>/gpu-vram-orchestrator:v1.0
```

### 3. Update Kubernetes Manifests
Edit `kubernetes/deployment.yaml`:
```yaml
image: <your-registry>/gpu-vram-orchestrator:v1.0  # Update image
imagePullPolicy: Always
```

### 4. Create Namespace
```bash
kubectl create namespace gpu-orchestrator
```

### 5. Apply ConfigMaps
```bash
kubectl apply -f kubernetes/configmap.yaml
```

### 6. Deploy Application
```bash
# Deploy orchestrator
kubectl apply -f kubernetes/deployment.yaml
kubectl apply -f kubernetes/service.yaml

# Verify deployment
kubectl get deployments -n default
kubectl get pods -n default
kubectl logs -f deployment/gpu-vram-orchestrator -n default
```

### 7. Verify Service
```bash
# Get service IP
kubectl get svc gpu-vram-orchestrator

# Port forward for testing
kubectl port-forward svc/gpu-vram-orchestrator 8000:80

# Test API
curl http://localhost:8000/health
```

### 8. Setup Prometheus Monitoring
```bash
# Deploy Prometheus (already in docker-compose)
# For K8s, use Prometheus Operator or manual setup

# Verify scraping
kubectl port-forward svc/prometheus 9090:9090
# Visit http://localhost:9090/targets
```

### 9. Setup Grafana Dashboards
```bash
# Port forward Grafana
kubectl port-forward svc/grafana 3000:3000

# Access at http://localhost:3000
# Login: admin/admin
# Add Prometheus datasource: http://prometheus:9090
# Import GPU orchestrator dashboard
```

## Production Configuration

### Environment Variables
```bash
# GPU Configuration
GPU_MAX_MEMORY_FRACTION=0.9          # Use 90% of GPU memory
GPU_ALLOWED_IDS=0,1,2,3             # Specific GPUs to use

# Application
CACHE_SIZE_MB=24000                 # 24 GB cache per GPU
SCHEDULER_WORKERS=4                 # Thread pool size
APP_MAX_CONNECTIONS=1000            # Max concurrent connections
APP_REQUEST_TIMEOUT_SECONDS=300     # Request timeout

# Monitoring
PROMETHEUS_ENABLED=true             # Enable metrics
METRICS_EXPORT_INTERVAL_SECONDS=60  # Export frequency
LOG_LEVEL=INFO                      # Log verbosity

# Security
API_KEY_REQUIRED=true
API_KEYS="key1,key2,key3"           # Comma-separated keys
```

### Performance Tuning

#### Memory Optimization
```bash
# Set cache size based on GPU memory
# For 24GB V100: CACHE_SIZE_MB=22000 (reserve 2GB for overhead)
# For 40GB A100: CACHE_SIZE_MB=38000
# For 48GB H100: CACHE_SIZE_MB=45000
```

#### Scheduler Tuning
```bash
# Adjust weights in scheduler/gpu_scheduler.py
SCHEDULER_MEMORY_WEIGHT=0.5         # 50% importance to memory
SCHEDULER_LOAD_WEIGHT=0.3           # 30% importance to GPU load
SCHEDULER_AFFINITY_WEIGHT=0.2       # 20% importance to model colocation
```

#### Prediction Configuration
```bash
PREDICTION_ENABLED=true
PREDICTION_WINDOW_HOURS=24          # Learn from last 24 hours
PREDICTION_MIN_CONFIDENCE=0.60      # Minimum confidence score
```

## Scaling Strategies

### Horizontal Scaling (Multiple Pods)
```yaml
# In deployment.yaml
spec:
  replicas: 10  # Number of pods
  
  # HPA automatically scales between 2-10
  minReplicas: 2
  maxReplicas: 10
```

**When to scale**:
- CPU utilization > 70%
- Memory utilization > 80%
- Request latency > SLO

### Vertical Scaling (Larger GPUs)
- V100 → A100 → H100
- Larger cache size per GPU
- Increased concurrent models

### Resource Management
```yaml
resources:
  requests:
    gpu: 1
    memory: 2Gi
    cpu: 2
  limits:
    gpu: 1
    memory: 4Gi
    cpu: 4
```

## Monitoring & Alerting

### Key Metrics to Monitor
- **Cache Hit Rate**: Target > 75%
- **GPU Utilization**: Target > 70%
- **Inference Latency P95**: Target < 500ms
- **Scheduler Time**: Target < 1ms
- **Model Load Time**: Baseline + 10% variance acceptable

### Alert Rules
```yaml
# Configure in alertmanager.yml
- alert: LowCacheHitRate
  expr: gpu_cache_hit_rate < 0.60
  for: 5m
  
- alert: HighGPUUtilization
  expr: gpu_utilization_percent > 95
  for: 2m
  
- alert: SlowScheduler
  expr: scheduler_selection_time_ms > 10
  for: 1m
```

### Grafana Dashboards
Available dashboards:
1. **System Health**: CPU, memory, GPU utilization
2. **Cache Performance**: Hit rate, evictions, memory
3. **Scheduler Analysis**: Selection time, scores, distribution
4. **Prediction Accuracy**: Hit rate, model predictions
5. **Cost Analysis**: GPU hours, estimated savings

## Troubleshooting

### Pod not starting
```bash
kubectl describe pod <pod-name>
kubectl logs <pod-name>

# Common issues:
# - GPU not available: Check node labels
# - Image not found: Verify image name in deployment
# - Memory limits: Reduce CACHE_SIZE_MB
```

### Low cache hit rate
```bash
# Check predictor accuracy
curl http://localhost:8000/stats/predictor

# Increase prediction confidence:
PREDICTION_MIN_CONFIDENCE=0.40  # Lower threshold

# Analyze access patterns
curl http://localhost:8000/stats/patterns
```

### High latency
```bash
# Check scheduler performance
curl http://localhost:8000/stats/scheduler

# Monitor GPU memory
curl http://localhost:8000/status

# Consider increasing cache size
CACHE_SIZE_MB=26000
```

### Out of memory errors
```bash
# Reduce cache size
CACHE_SIZE_MB=20000

# Enable more aggressive eviction
# (modify cache.py threshold)

# Monitor LRU evictions
curl http://localhost:8000/metrics | grep evictions
```

## Backup & Recovery

### Model Cache Backup
```bash
# Local backup
docker cp gpu-orchestrator:/var/cache/models ./backup/

# Kubernetes backup
kubectl exec -it <pod> -- tar czf - /var/cache/models | gzip > backup.tar.gz
```

### State Recovery
- Orchestrator is stateless (can restart anytime)
- Cache rebuilt on-demand as models requested
- Metrics reset on restart (persisted to Prometheus)
- Access patterns reset (re-learned from request stream)

## Security

### Network Security
```bash
# Restrict API access
kubectl network-policies add-policy gpu-orchestrator

# Use service mesh (Istio)
# - mTLS between services
# - Rate limiting
# - Request authentication
```

### Data Security
```bash
# Encrypt model cache at rest
# Use encrypted PersistentVolumes in K8s

# API authentication
API_KEY_REQUIRED=true
# Use strong API keys (generate with: openssl rand -hex 32)
```

### RBAC
```yaml
# Service account with minimal permissions
serviceAccountName: gpu-orchestrator

# Only read ConfigMaps and Pods
- apiGroups: [""]
  resources: ["configmaps", "pods"]
  verbs: ["get", "list"]
```

## Maintenance

###  Log Rotation
```bash
# Configure in logging.conf (created automatically)
# Keep last 10 files, 10MB each
handler_file = handlers.RotatingFileHandler
args = ('/var/log/gpu-orchestrator.log', 'a', 10485760, 10)
```

### Regular Tasks
- Monitor disk space for model cache
- Rotate logs monthly
- Review and tune performance metrics quarterly
- Test failover procedures
- Update dependencies monthly

## Support & Issues

- **Documentation**: See [ARCHITECTURE.md](ARCHITECTURE.md) and [API.md](API.md)
- **Issues**: https://github.com/HarshithaJ28/gpu-vram-orchestrator/issues
- **Performance Tuning**: Review [ARCHITECTURE.md#optimization-opportunities](ARCHITECTURE.md#optimization-opportunities)
