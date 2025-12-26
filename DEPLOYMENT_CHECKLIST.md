# Production Deployment Checklist

Complete this checklist before deploying GPU VRAM Orchestrator to production.

## Pre-Deployment Planning

### Infrastructure Assessment
- [ ] Inventory all available GPUs (model, memory, interconnect)
- [ ] Document GPU topology and NUMA affinity
- [ ] Verify NVIDIA driver version >= 515
- [ ] Test CUDA toolkit compatibility
- [ ] Plan network segmentation (management, data, monitoring)
- [ ] Estimate required storage for models and metrics

### Capacity Planning
- [ ] Calculate total GPU memory available
- [ ] Estimate model sizes (average and max)
- [ ] Plan cache size (typically 80-90% of GPU memory)
- [ ] Estimate QPS (queries per second) target
- [ ] Calculate required replicas/pods

### Security Planning
- [ ] Define authentication/authorization strategy
- [ ] Plan credential rotation
- [ ] Audit API access requirements
- [ ] Document compliance requirements (HIPAA/PCI-DSS if needed)

## Kubernetes Cluster Setup

### Cluster Prerequisites
- [ ] Kubernetes 1.24+ deployed
- [ ] NVIDIA GPU Operator installed (`nvidia/gpu-operator`)
- [ ] GPU driver installed on all nodes
- [ ] Network policy support (Calico/Cilium)
- [ ] Storage support (PV provisioning)
- [ ] Ingress controller deployed (nginx/istio)

### Verify GPU Setup
```bash
# Check GPU operator
kubectl get pods -n nvidia-gpu-operator

# Verify GPU availability on nodes
kubectl get nodes -L nvidia.com/gpu

# Test GPU access
kubectl run gpu-test --image=nvidia/cuda:11.8.0 -- nvidia-smi
```

## Application Deployment

### Namespace and RBAC
- [ ] Create dedicated namespace: `kubectl create ns gpu-orchestrator`
- [ ] Create service account with appropriate RBAC
- [ ] Set resource quotas per namespace
- [ ] Configure network policies

### ConfigMap and Secrets
- [ ] Create ConfigMap with production settings
- [ ] Create Secret for API keys/credentials
- [ ] Document all environment variables
- [ ] Set log level to INFO (not DEBUG)

### Registry Configuration
- [ ] Push image to private registry
- [ ] Configure image pull secrets
- [ ] Enable image scanning/signing
- [ ] Set image pull policy to IfNotPresent

### Deployment Configuration
- [ ] Set appropriate resource requests/limits
  ```yaml
  resources:
    requests:
      memory: "2Gi"
      cpu: "1"
      nvidia.com/gpu: 1
    limits:
      memory: "4Gi"
      cpu: "2"
      nvidia.com/gpu: 1
  ```
- [ ] Configure replicas (minimum 2 for HA)
- [ ] Enable HPA with appropriate targets
- [ ] Set pod disruption budget (minAvailable: 1)
- [ ] Configure node affinity for GPU nodes
- [ ] Set tolerations for GPU node taints

### Health Checks Configuration
- [ ] Liveness probe: `/health` every 30s
- [ ] Readiness probe: `/ready` every 5s
- [ ] Startup probe: Allow 60s for initialization

## Storage Configuration

### PersistentVolume Setup
- [ ] Provision PV for model cache (if using persistent storage)
- [ ] Create PVC with appropriate storage class
- [ ] Test read/write performance (should be > 100MB/s)
- [ ] Set appropriate retention policy

### Model Management
- [ ] Upload initial model set
- [ ] Configure model versioning strategy
- [ ] Set up model update procedure
- [ ] Document model size limits

## Monitoring and Observability

### Prometheus Setup
- [ ] Deploy Prometheus in cluster
- [ ] Configure scrape configs for GPU Orchestrator
- [ ] Load alert rules: `prometheus_alerts.yml`
- [ ] Verify metrics collection: `http://prom:9090/api/v1/targets`
- [ ] Set up metric retention (30 days minimum)

### Grafana Setup
- [ ] Deploy Grafana in cluster
- [ ] Add Prometheus datasource
- [ ] Import dashboard: `grafana_dashboard.json`
- [ ] Create dashboards for:
  - System health overview
  - GPU utilization
  - Cache performance
  - Latency distribution
  - Error rates

### Alerting Configuration
- [ ] Configure AlertManager
- [ ] Set up Slack/PagerDuty webhook
- [ ] Test critical alert routing
- [ ] Create runbook links in alert annotations
- [ ] Verify on-call escalation policy

### Logging Setup
- [ ] Deploy log aggregation (ELK/Splunk/Stackdriver)
- [ ] Configure log shipping from pods
- [ ] Set log retention policy (30-90 days)
- [ ] Create log search dashboards

## API Gateway and Ingress

### Ingress Configuration
- [ ] Configure Ingress for public API endpoint
- [ ] Enable TLS with valid certificate
- [ ] Set up rate limiting
- [ ] Configure VPC peering/firewall rules

### Authentication/Authorization
- [ ] Enable API key authentication
- [ ] Configure OAuth2 (optional)
- [ ] Set up RBAC policies
- [ ] Document API client setup

## Testing and Validation

### Unit and Integration Tests
```bash
# Run full test suite
cd backend
pytest tests/ -v --cov=src

# Validate test coverage >= 80%
pytest tests/ --cov=src --cov-report=html
```

### Performance Testing
```bash
# Load test with k6
k6 run load_tests/inference_load_test.js \
  --vus=50 --duration=5m

# Expected results:
# - P99 latency < 200ms
# - Cache hit rate > 75%
# - Error rate < 0.1%
```

### Failover Testing
- [ ] Test pod restart (kill pod, verify recovery)
- [ ] Test node failure (cordon node, verify migration)
- [ ] Test application crash (kill deployment, verify auto-restart)
- [ ] Verify metrics continuity after failover

### Backward Compatibility
- [ ] Test with previous model versions
- [ ] Verify API compatibility with clients
- [ ] Test upgrade path
- [ ] Document deprecation timeline

## Operational Readiness

### Documentation
- [ ] Runbooks for all critical alerts
- [ ] Troubleshooting guide completed
- [ ] API documentation published
- [ ] Architecture diagrams updated
- [ ] Capacity planning results documented

### Access and Permissions
- [ ] On-call rotation established
- [ ] Team trained on operations
- [ ] Escalation paths documented
- [ ] Access levels configured (read/write/admin)

### Backup Strategy
- [ ] Automated model backup every 24 hours
- [ ] Test restore procedure
- [ ] Document recovery RTO/RPO
- [ ] Store backups in separate region

### Compliance and Audit
- [ ] Security audit completed
- [ ] Data encryption enabled (in transit and at rest)
- [ ] Audit logging configured
- [ ] Compliance scan passed

## Deployment Command Checklist

```bash
# 1. Create namespace
kubectl create namespace gpu-orchestrator

# 2. Create secrets (update with actual values)
kubectl create secret generic gpu-orchestrator-secrets \
  --from-literal=slack-webhook=${SLACK_WEBHOOK_URL} \
  --from-literal=pagerduty-key=${PAGERDUTY_KEY} \
  -n gpu-orchestrator

# 3. Deploy Prometheus
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack \
  -n gpu-orchestrator \
  -f monitoring/prometheus-values.yaml

# 4. Deploy Grafana
helm repo add grafana https://grafana.github.io/helm-charts
helm install grafana grafana/grafana \
  -n gpu-orchestrator \
  --set adminPassword=admin

# 5. Deploy GPU Orchestrator
helm install gpu-orchestrator ./helm/gpu-vram-orchestrator \
  -n gpu-orchestrator \
  --set replicas=2 \
  --set image.tag=v1.0.0

# 6. Verify deployment
kubectl get pods -n gpu-orchestrator
kubectl logs -f deployment/gpu-vram-orchestrator -n gpu-orchestrator

# 7. Check metrics
kubectl port-forward -n gpu-orchestrator svc/prometheus 9090:9090

# 8. Access Grafana
kubectl port-forward -n gpu-orchestrator svc/grafana 3000:3000
# Visit http://localhost:3000 (admin/admin)
```

## Post-Deployment Verification

### Immediate (First Hour)
- [ ] Pods running and healthy (`kubectl get pods`)
- [ ] Metrics flowing (`http://prometheus:9090/api/v1/targets`)
- [ ] API responding (`curl http://api:8000/health`)
- [ ] No critical alerts firing

### Short-term (First Day)
- [ ] Process 100+ predictions successfully
- [ ] Cache hit rate stabilizes above 50%
- [ ] Latency P99 below 200ms
- [ ] Zero critical incidents

### Medium-term (First Week)
- [ ] Achieve 75%+ cache hit rate
- [ ] GPU utilization stable at target level
- [ ] All predictions logged and queryable
- [ ] Monitoring dashboards fully functional

### Long-term (First Month)
- [ ] No resource issues identified
- [ ] Cost metrics aligned with projections
- [ ] Disaster recovery tested
- [ ] Knowledge transfer complete

## Rollback Procedures

### Quick Rollback
```bash
# If deployment is problematic
kubectl rollout undo deployment/gpu-vram-orchestrator -n gpu-orchestrator

# Verify rollback
kubectl rollout status deployment/gpu-vram-orchestrator -n gpu-orchestrator
```

### Model Rollback
```bash
# Revert to previous model version
kubectl delete configmap model-config -n gpu-orchestrator
kubectl create configmap model-config --from-literal=version=v1.0.0 \
  -n gpu-orchestrator
kubectl rollout restart deployment/gpu-vram-orchestrator -n gpu-orchestrator
```

## Success Metrics

Define what "successful production deployment" means:

| Metric | SLA | Measurement |
|--------|-----|-------------|
| Availability | 99.9% | Monthly uptime |
| P99 Latency | < 200ms | Via Prometheus |
| Cache Hit Rate | > 75% | Via metrics |
| Error Rate | < 0.1% | Via metrics |
| GPU Utilization | 70-85% | Via nvidia-smi |
| MTTR | < 15min | Incident logs |
| RTO | < 5min | Failover test |
| RPO | < 1hour | Backup test |

---

## Support

For questions or issues during deployment:
1. Check [TROUBLESHOOTING.md](../TROUBLESHOOTING.md)
2. Review [DEPLOYMENT.md](../DEPLOYMENT.md)
3. Open GitHub issue with logs attached
4. Contact on-call engineer for critical issues

---

**Deployment Date**: _______________  
**Deployed By**: _______________  
**Reviewed By**: _______________  
**Approved By**: _______________  
