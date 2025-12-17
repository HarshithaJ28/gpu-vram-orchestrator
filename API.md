# GPU VRAM Orchestrator - API Documentation

## Overview

The GPU VRAM Orchestrator provides a REST API for model inference management, GPU monitoring, and performance metrics collection. All endpoints return JSON responses.

**Base URL**: `http://localhost:8000` (development) or `https://gpu-orchestrator.example.com` (production)

## Authentication

Currently, no authentication required in development. For production:

```bash
# Add API key header
Authorization: Bearer <api-key>
```

All requests should include:
```json
{
  "headers": {
    "Content-Type": "application/json",
    "Authorization": "Bearer your-api-key"
  }
}
```

## Common Response Format

### Success Response (200)
```json
{
  "status": "success",
  "data": { /* response data */ },
  "timestamp": "2025-12-11T14:30:00Z"
}
```

### Error Response
```json
{
  "status": "error",
  "error": "Error message",
  "error_code": "ERROR_CODE",
  "timestamp": "2025-12-11T14:30:00Z"
}
```

## Endpoints

### 1. Health & Status

#### GET /health
**Description**: Liveness probe for health checks

**Response**: 200 OK
```json
{
  "status": "healthy",
  "timestamp": "2025-12-11T14:30:00Z"
}
```

**Use Case**: Kubernetes liveness probe, load balancer health check

---

#### GET /status
**Description**: Complete system status including GPU and cache information

**Response**: 200 OK
```json
{
  "status": "ready",
  "gpus": {
    "count": 4,
    "available": true,
    "details": [
      {
        "gpu_id": 0,
        "name": "NVIDIA A100-PCIE-40GB",
        "memory_mb": {
          "total": 40960,
          "free": 35000,
          "allocated": 5960
        },
        "utilization_pct": 42.5,
        "models_loaded": 3,
        "temperature_c": 45
      },
      // ... more GPUs
    ]
  },
  "cache": {
    "total_size_mb": 24000,
    "used_mb": 18500,
    "hit_rate": 0.82,
    "hit_count": 1050,
    "miss_count": 230,
    "eviction_count": 15
  },
  "scheduler": {
    "pending_requests": 5,
    "avg_selection_time_ms": 0.45
  },
  "predictor": {
    "enabled": true,
    "patterns_learned": 12,
    "accuracy": 0.78
  },
  "timestamp": "2025-12-11T14:30:00Z"
}
```

---

### 2. Model Prediction

#### POST /predict
**Description**: Run inference on a model with intelligent GPU scheduling

**Request**:
```json
{
  "model_id": "fraud-detection-v2",
  "input_data": {
    "feature_1": 0.5,
    "feature_2": 1.2,
    "features": [0.1, 0.2, 0.3, 0.4, 0.5]
  },
  "batch_size": 1,
  "return_timing": true
}
```

**Response**: 200 OK
```json
{
  "model_id": "fraud-detection-v2",
  "predictions": [
    {
      "label": "fraud",
      "probability": 0.92
    }
  ],
  "gpu_id": 0,
  "timing_ms": {
    "scheduler": 0.35,
    "cache_lookup": 0.12,
    "inference": 45.23,
    "total": 45.70
  },
  "cache_hit": true,
  "timestamp": "2025-12-11T14:30:00Z"
}
```

**Status Codes**:
- `200 OK`: Prediction successful
- `404 Not Found`: Model not available
- `503 Service Unavailable`: No GPU memory available
- `504 Gateway Timeout`: Inference timed out

---

#### POST /predict/batch
**Description**: Run batch inference on multiple samples

**Request**:
```json
{
  "model_id": "fraud-detection-v2",
  "samples": [
    {"feature_1": 0.5, "feature_2": 1.2},
    {"feature_1": 0.3, "feature_2": 0.8},
    {"feature_1": 0.9, "feature_2": 1.5}
  ],
  "return_timing": true
}
```

**Response**: 200 OK
```json
{
  "model_id": "fraud-detection-v2",
  "predictions": [
    [{"label": "fraud", "probability": 0.92}],
    [{"label": "legitimate", "probability": 0.78}],
    [{"label": "fraud", "probability": 0.85}]
  ],
  "gpu_id": 0,
  "batch_size": 3,
  "timing_ms": {
    "scheduler": 0.35,
    "batch_inference": 145.23,
    "total": 145.58
  },
  "cache_hit": true,
  "timestamp": "2025-12-11T14:30:00Z"
}
```

---

### 3. Model Management

#### GET /models
**Description**: List all available models and their status

**Query Parameters**:
- `status` (optional): `loaded`, `available`, `unavailable`
- `gpu_id` (optional): Filter by GPU id

**Response**: 200 OK
```json
{
  "models": [
    {
      "model_id": "fraud-detection-v2",
      "category": "fraud-detection",
      "status": "loaded",
      "gpu_id": 0,
      "size_mb": 2048,
      "load_count": 352,
      "last_accessed": "2025-12-11T14:28:45Z",
      "access_frequency": "high"
    },
    {
      "model_id": "recommendation-v1",
      "category": "recommendation",
      "status": "available",
      "gpu_id": null,
      "size_mb": 8192,
      "load_count": 89,
      "last_accessed": "2025-12-11T14:15:30Z",
      "access_frequency": "medium"
    }
  ],
  "total": 2,
  "timestamp": "2025-12-11T14:30:00Z"
}
```

---

#### POST /models/load
**Description**: Pre-load a model onto a specific GPU

**Request**:
```json
{
  "model_id": "image-classifier-v3",
  "gpu_id": 1,
  "pin": true
}
```

**Response**: 202 Accepted
```json
{
  "model_id": "image-classifier-v3",
  "gpu_id": 1,
  "status": "loading",
  "estimated_time_seconds": 15,
  "task_id": "task-uuid-12345"
}
```

---

#### POST /models/unload
**Description**: Unload a model from GPU

**Request**:
```json
{
  "model_id": "image-classifier-v3",
  "gpu_id": 1
}
```

**Response**: 200 OK
```json
{
  "model_id": "image-classifier-v3",
  "gpu_id": 1,
  "status": "unloaded",
  "freed_memory_mb": 4096,
  "timestamp": "2025-12-11T14:30:00Z"
}
```

---

#### POST /models/pin
**Description**: Pin a model to prevent LRU eviction

**Request**:
```json
{
  "model_id": "fraud-detection-v2",
  "gpu_id": 0
}
```

**Response**: 200 OK
```json
{
  "model_id": "fraud-detection-v2",
  "gpu_id": 0,
  "pinned": true,
  "timestamp": "2025-12-11T14:30:00Z"
}
```

---

#### POST /models/unpin
**Description**: Unpin a model (allow LRU eviction)

**Request**:
```json
{
  "model_id": "fraud-detection-v2",
  "gpu_id": 0
}
```

**Response**: 200 OK
```json
{
  "model_id": "fraud-detection-v2",
  "gpu_id": 0,
  "pinned": false,
  "timestamp": "2025-12-11T14:30:00Z"
}
```

---

### 4. Statistics & Metrics

#### GET /stats
**Description**: Get comprehensive system statistics

**Response**: 200 OK
```json
{
  "cache": {
    "hit_rate": 0.82,
    "hits": 1050,
    "misses": 230,
    "evictions": 15,
    "avg_eviction_time_ms": 145
  },
  "scheduler": {
    "total_selections": 1280,
    "avg_time_ms": 0.45,
    "p95_time_ms": 1.2,
    "p99_time_ms": 2.5,
    "selections_by_gpu": [320, 280, 380, 300]
  },
  "inference": {
    "total_requests": 1280,
    "avg_latency_ms": 50.3,
    "p95_latency_ms": 120.5,
    "p99_latency_ms": 250.8,
    "errors": 2
  },
  "predictor": {
    "patterns_learned": 12,
    "accuracy": 0.78,
    "preloads_triggered": 245,
    "preload_success_rate": 0.87
  },
  "system": {
    "uptime_seconds": 86400,
    "memory_overhead_mb": 512,
    "thread_count": 32
  },
  "timestamp": "2025-12-11T14:30:00Z"
}
```

---

#### GET /stats/gpu/{gpu_id}
**Description**: Get statistics for a specific GPU

**Response**: 200 OK
```json
{
  "gpu_id": 0,
  "name": "NVIDIA A100-PCIE-40GB",
  "memory": {
    "total_mb": 40960,
    "free_mb": 35000,
    "allocated_mb": 5960,
    "utilized_mb": 1200
  },
  "utilization_pct": 42.5,
  "models_loaded": 3,
  "models": [
    {
      "model_id": "fraud-detection-v2",
      "size_mb": 2048,
      "last_accessed": "2025-12-11T14:29:00Z",
      "pinned": true
    },
    {
      "model_id": "recommendation-v1",
      "size_mb": 3072,
      "last_accessed": "2025-12-11T14:28:30Z",
      "pinned": false
    }
  ],
  "temperature_c": 45,
  "power_usage_w": 210,
  "timestamp": "2025-12-11T14:30:00Z"
}
```

---

#### GET /metrics
**Description**: Get Prometheus metrics (plain text format)

**Response**: 200 OK (Content-Type: text/plain)
```
# HELP gpu_cache_hits_total Total cache hits
# TYPE gpu_cache_hits_total counter
gpu_cache_hits_total 1050

# HELP gpu_cache_misses_total Total cache misses
# TYPE gpu_cache_misses_total counter
gpu_cache_misses_total 230

# HELP gpu_utilization_percent GPU utilization (%)
# TYPE gpu_utilization_percent gauge
gpu_utilization_percent{gpu_id="0"} 42.5
gpu_utilization_percent{gpu_id="1"} 38.2
...
```

**Use Case**: Scraped by Prometheus every 15 seconds

---

#### GET /metrics/json
**Description**: Get metrics in JSON format

**Response**: 200 OK
```json
{
  "cache_hits": 1050,
  "cache_misses": 230,
  "cache_hit_rate": 0.82,
  "gpu_utilization": {
    "0": 42.5,
    "1": 38.2,
    "2": 55.3,
    "3": 31.8
  },
  "models_loaded": {
    "0": 3,
    "1": 2,
    "2": 4,
    "3": 1
  },
  "scheduler_times": {
    "fraud-detection-v2": 0.45,
    "recommendation-v1": 0.38,
    "image-classifier-v3": 0.52
  },
  "inference_latencies": {
    "fraud-detection-v2": 45.23,
    "recommendation-v1": 120.56,
    "image-classifier-v3": 78.34
  },
  "cost_gpu_hours": 48.5,
  "cost_savings": 12500,
  "timestamp": "2025-12-11T14:30:00Z"
}
```

---

### 5. Configuration

#### GET /config
**Description**: Get current configuration

**Response**: 200 OK
```json
{
  "cache": {
    "size_mb": 24000,
    "eviction_policy": "lru"
  },
  "scheduler": {
    "memory_weight": 0.5,
    "load_weight": 0.3,
    "affinity_weight": 0.2
  },
  "predictor": {
    "enabled": true,
    "window_hours": 24,
    "min_confidence": 0.6
  },
  "monitoring": {
    "prometheus_enabled": true,
    "export_interval_seconds": 60
  },
  "timestamp": "2025-12-11T14:30:00Z"
}
```

---

#### POST /config/update
**Description**: Update configuration (admin only)

**Request**:
```json
{
  "cache": {
    "size_mb": 28000
  },
  "scheduler": {
    "memory_weight": 0.6
  }
}
```

**Response**: 200 OK
```json
{
  "status": "updated",
  "changes": {
    "cache.size_mb": "24000 → 28000",
    "scheduler.memory_weight": "0.5 → 0.6"
  },
  "timestamp": "2025-12-11T14:30:00Z"
}
```

---

## Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 400 | Bad Request | Check request format |
| 404 | Not Found | Model or GPU doesn't exist |
| 409 | Conflict | Model already loaded/pinned |
| 500 | Internal Error | Check logs, retry later |
| 503 | Unavailable | No GPU memory, scale up |
| 504 | Timeout | Model load took too long |

---

## Rate Limiting

- **Inference**: 1000 requests/minute per API key
- **Management**: 50 requests/minute per API key
- **Metrics**: Unlimited (internal scraping)

Response includes headers:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 987
X-RateLimit-Reset: 1670778600
```

---

## Code Examples

### Python Client
```python
import requests
import json

BASE_URL = "http://localhost:8000"
API_KEY = "your-api-key"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

# Check health
response = requests.get(f"{BASE_URL}/health", headers=headers)
print(response.json())

# Run prediction
prediction_request = {
    "model_id": "fraud-detection-v2",
    "input_data": {
        "features": [0.1, 0.2, 0.3, 0.4, 0.5]
    }
}
response = requests.post(
    f"{BASE_URL}/predict",
    json=prediction_request,
    headers=headers
)
print(response.json())
```

### cURL
```bash
# Check status
curl -X GET http://localhost:8000/status

# Run prediction
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "fraud-detection-v2",
    "input_data": {"features": [0.1, 0.2, 0.3]}
  }'

# Get metrics
curl http://localhost:8000/metrics
```

### JavaScript/TypeScript
```typescript
async function predict(modelId: string, inputData: any) {
  const response = await fetch('http://localhost:8000/predict', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${API_KEY}`
    },
    body: JSON.stringify({
      model_id: modelId,
      input_data: inputData
    })
  });
  return response.json();
}
```

---

## WebSocket API (Streaming)

For streaming predictions (large batches):

```javascript
const ws = new WebSocket('ws://localhost:8000/predict/stream');

ws.onopen = () => {
  ws.send(JSON.stringify({
    model_id: 'fraud-detection-v2',
    mode: 'stream'
  }));
};

ws.onmessage = (event) => {
  const result = JSON.parse(event.data);
  console.log(result.predictions);
};
```

---

## API Versioning

Current version: **v1** (implicit)

Future versions:
- **v2**: Add async inference
- **v3**: Add model ensemble support

---

## Support

- **Issues**: https://github.com/HarshithaJ28/gpu-vram-orchestrator/issues
- **Questions**: Open GitHub discussions
- **Performance**: See [DEPLOYMENT.md](DEPLOYMENT.md)
