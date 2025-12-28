# 🧪 WEEK 1 TESTING GUIDE - VALIDATE ALL FIXES

This guide walks through testing all Week 1 implementations to verify they work correctly.

---

## 📋 PRE-TESTING CHECKLIST

Before running tests:
- [ ] Python 3.10+ installed
- [ ] NVIDIA GPU with CUDA support (optional - GPU_ENABLED can be false)
- [ ] pip dependencies installed

### Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### Check Installation
```bash
python -c "import torch; print(torch.cuda.is_available())"
python -c "import fastapi; import pydantic; print('FastAPI OK')"
```

---

## ✅ TEST SUITE 1: UNIT TESTS

### Run All Tests
```bash
cd backend
pytest tests/ -v --tb=short
```

### Expected Output
```
test_gpu_cache.py::TestGPUCache::test_initialization PASSED
test_gpu_cache.py::TestGPUCache::test_load_model PASSED
test_gpu_cache.py::TestGPUCache::test_lru_eviction PASSED
...
test_inference_engine.py::TestInferenceEngine::test_initialization PASSED
test_inference_engine.py::TestInferenceEngine::test_predict_sync PASSED
test_inference_engine.py::TestInferenceEngine::test_predict_batch PASSED
...
test_model_registry.py::TestModelRegistry::test_initialization PASSED
test_model_registry.py::TestModelRegistry::test_register_model PASSED
...

===== 50+ passed in 5.32s =====
```

### Run Specific Test Module
```bash
# Inference engine tests
pytest tests/test_inference_engine.py -v

# Model registry tests
pytest tests/test_model_registry.py -v

# GPU cache tests
pytest tests/test_gpu_cache.py -v

# Scheduler tests
pytest tests/test_scheduler.py -v
```

### Run with Coverage
```bash
pytest tests/ --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

---

## 🚀 TEST SUITE 2: INTEGRATION TEST

### Start the Server
```bash
cd backend
python -m uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```

### In another terminal, test endpoints

#### 2.1 Health Check
```bash
curl http://localhost:8000/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "service": "ModelMesh",
  "num_gpus": 2,
  "total_models_loaded": 0,
  "avg_gpu_utilization_pct": 0,
  "cache_hit_rate": 0
}
```

---

#### 2.2 System Info
```bash
curl http://localhost:8000/info
```

**Expected Response:**
```json
{
  "service": "ModelMesh GPU VRAM Orchestrator",
  "version": "1.0.0",
  "status": "operational",
  "gpus": [
    {
      "gpu_id": 0,
      "name": "NVIDIA RTX A100 (or CPU)",
      "compute_capability": [8, 0],
      "total_memory_mb": 40960
    }
  ]
}
```

---

#### 2.3 GPU Statistics
```bash
curl http://localhost:8000/stats/gpu
```

**Expected Response:**
```json
[
  {
    "gpu_id": 0,
    "models_loaded": 0,
    "memory_used_mb": 0,
    "memory_free_mb": 22000,
    "memory_total_mb": 22000,
    "utilization_pct": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "hit_rate": 0,
    "evictions": 0,
    "failed_loads": 0,
    "models": []
  }
]
```

---

#### 2.4 Scheduler Statistics
```bash
curl http://localhost:8000/stats/scheduler
```

**Expected Response:**
```json
{
  "num_gpus": 2,
  "pending_requests": {},
  "model_access_history_size": 0,
  "weights": {
    "memory": 0.5,
    "load": 0.3,
    "affinity": 0.2
  }
}
```

---

#### 2.5 Make Prediction (Will Fail - No Models)
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "test-model",
    "data": {"input": [1, 2, 3]}
  }'
```

**Expected Response (Error):**
```json
{
  "detail": "Model test-model not found"
}
```

**This is correct!** We don't have models registered yet.

---

## 🏋️ TEST SUITE 3: MANUAL INTEGRATION TEST

### Step 1: Create Dummy Model
```python
# test_setup.py
import torch
import os

# Create simple model
model = torch.nn.Sequential(
    torch.nn.Linear(10, 5),
    torch.nn.ReLU(),
    torch.nn.Linear(5, 1)
)

# Save it
os.makedirs("./models/models", exist_ok=True)
torch.save(model, "./models/models/test-model-1.0.0.pth")
print("✓ Saved test model")
```

Run it:
```bash
cd backend
python test_setup.py
```

### Step 2: Register Model
```bash
# Note: Need to implement registration endpoint or use Python
python -c "
from src.registry import ModelRegistry
registry = ModelRegistry('./models')
registry.register_model(
    model_id='test-model',
    model_path='./models/models/test-model-1.0.0.pth',
    framework='pytorch',
    version='1.0.0',
    description='Test model'
)
print('✓ Model registered')
"
```

### Step 3: Check Registry
```bash
curl http://localhost:8000/registry/models
```

**Expected Response:**
```json
{
  "test-model": [
    {
      "version": "1.0.0",
      "size_mb": 0.05,
      "registered_at": "2025-03-08T...",
      "tags": [],
      "description": "Test model"
    }
  ]
}
```

---

### Step 4: Make Prediction (COLD START)
```bash
time curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "test-model",
    "data": {"input": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]}
  }'
```

**Expected Response (First time ~100ms):**
```json
{
  "model_id": "test-model",
  "prediction": [-0.123],
  "latency_ms": 98.5,
  "gpu_id": 0,
  "cached": false,
  "batch_size": 1
}
```

✅ **Success!** Model loaded and inference ran (cached: false)

---

### Step 5: Make Prediction Again (HOT - CACHED)
```bash
time curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "test-model",
    "data": {"input": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]}
  }'
```

**Expected Response (Second time ~8ms):**
```json
{
  "model_id": "test-model",
  "prediction": [-0.123],
  "latency_ms": 7.8,
  "gpu_id": 0,
  "cached": true,
  "batch_size": 1
}
```

✅ **Success!** Model was cached (cached: true, much faster!)

---

### Step 6: Check CPU GPU Stats After Prediction
```bash
curl http://localhost:8000/stats/gpu | python -m json.tool
```

**Expected Changes:**
```json
[
  {
    "gpu_id": 0,
    "models_loaded": 1,  # ← Now 1 model loaded
    "memory_used_mb": 0.05,  # ← Memory used
    "cache_hits": 1,  # ← 1 cache hit
    "cache_misses": 1,  # ← 1 cache miss (first request)
    "hit_rate": 0.5,  # ← 50% hit rate
  }
]
```

---

### Step 7: Batch Prediction
```bash
curl -X POST http://localhost:8000/predict/batch \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "test-model",
    "batch_data": [
      {"input": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]},
      {"input": [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]},
      {"input": [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]}
    ],
    "batch_size": 32
  }'
```

**Expected Response:**
```json
{
  "model_id": "test-model",
  "predictions": [[-0.123], [-0.456], [-0.789]],
  "latency_ms": 15.2,
  "gpu_id": 0,
  "cached": true,
  "batch_size": 3
}
```

✅ **Success!** Batch inference works (3 predictions in ~15ms)

---

### Step 8: Model Eviction Test
```bash
# Try to evict model
curl -X POST http://localhost:8000/models/test-model/evict
```

**Expected Response:**
```json
{
  "model_id": "test-model",
  "evicted_from": [0],
  "success": true
}
```

Then check stats:
```bash
curl http://localhost:8000/stats/gpu | python -m json.tool
```

**Expected:**
```json
[
  {
    "models_loaded": 0,  # ← Model evicted!
    "memory_used_mb": 0,  # ← Memory freed!
    "evictions": 1  # ← Eviction counted
  }
]
```

---

### Step 9: Model Pinning Test
```bash
# Predict again to load model
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"model_id": "test-model", "data": {"input": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]}}'

# Pin the model
curl -X POST "http://localhost:8000/models/test-model/pin?gpu_id=0"
```

**Expected Response:**
```json
{
  "model_id": "test-model",
  "gpu_id": 0,
  "pinned": true
}
```

---

## 🔥 TEST SUITE 4: PERFORMANCE TEST

### Load Test with Apache Bench
```bash
# Install ab (Apache Bench)
# On Ubuntu: sudo apt-get install apache2-utils
# On macOS: brew install httpd

# 100 requests, 10 concurrency
ab -n 100 -c 10 -T "application/json" \
  -p payload.json \
  http://localhost:8000/predict
```

Where `payload.json` is:
```json
{
  "model_id": "test-model",
  "data": {"input": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]}
}
```

**Expected Output:**
```
Requests per second:    50.00 [#/sec] (mean)  # Should be fast for cached model
Time per request:       20.00 [ms] (mean)
Successful requests:    100
Failed requests:        0
```

---

### Load Test with wrk (Better)
```bash
# Install wrk: https://github.com/wg/wrk
wrk -t 4 -c 100 -d 30s \
  -s script.lua \
  http://localhost:8000/predict
```

Where `script.lua`:
```lua
wrk.method = "POST"
wrk.body = '{"model_id": "test-model", "data": {"input": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]}}'
wrk.headers["Content-Type"] = "application/json"
```

---

## 🐛 TROUBLESHOOTING

### Issue: "CUDA not available"
```
Solution: This is OK - system will fall back to CPU.
GPU_ENABLED will be true but models load to CPU.
This still tests all the logic!
```

### Issue: ImportError: No module named 'torch'
```
Solution: pip install -r requirements.txt
```

### Issue: Port 8000 already in use
```
Solution: Kill existing process or use different port:
python -m uvicorn src.app:app --port 8001
```

### Issue: Model registry not finding model
```
Solution: Ensure model file exists in ./models/models/ directory
ls -la ./models/models/
```

### Issue: Tests hanging
```
Solution: Check if server is running in background.
Kill it: killall python
Then try tests again: pytest tests/ -v
```

---

## ✅ FINAL VALIDATION CHECKLIST

Run this checklist to confirm everything works:

```bash
# 1. Unit tests pass
pytest tests/ -q
# ✅ Expected: All pass

# 2. Server starts
python -m uvicorn src.app:app > /tmp/server.log 2>&1 &
sleep 2

# 3. Health endpoint works
curl http://localhost:8000/health
# ✅ Expected: JSON response with status

# 4. System info endpoint works
curl http://localhost:8000/info
# ✅ Expected: Service info JSON

# 5. Can register model (setup step)
python -c "from src.registry import ModelRegistry; ..."
# ✅ Expected: No errors

# 6. Can make prediction
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" -d '{"model_id":"test-model","data":{"input":[1,2,3,4,5,6,7,8,9,10]}}'
# ✅ Expected: Prediction JSON

# 7. Cache works (latency ~8ms second time)
# ✅ Expected: cached: true in response

# 8. Stats update
curl http://localhost:8000/stats/gpu
# ✅ Expected: models_loaded > 0

# All good!
echo "✅ ALL VALIDATION TESTS PASSED!"
```

---

## 📈 EXPECTED METRICS AFTER TESTING

After running through these tests, you should see:

```
GPU Stats:
├─ Models Loaded: 1 (test-model)
├─ Memory Used: ~10MB (depends on model size)
├─ Cache Hits: 3+ (from repeated requests)
├─ Cache Misses: 1 (first request)
├─ Hit Rate: ~75%+
└─ Evictions: 1+ (from eviction test)

Latencies:
├─ Cold Start (first request): ~100ms
├─ Hot (cached): ~5-10ms
├─ Batch (3 items): ~15ms
└─ Performance: ✅ GOOD
```

---

## 🎉 SUCCESS CRITERIA

You know Week 1 is successful if:
- ✅ 50+ tests pass
- ✅ Server starts without errors
- ✅ Predictions work (cold & hot)
- ✅ Batch inference works
- ✅ Hot requests are ~10x faster than cold
- ✅ Memory is freed on eviction
- ✅ Stats are accurate
- ✅ No crashes during testing

---

**If all these tests pass → WEEK 1 IS WORKING! 🚀**

Next: Run Week 2 enhancements (predictive loading, monitoring)
