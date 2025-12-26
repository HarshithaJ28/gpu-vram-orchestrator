"""
Model management example - Loading, pinning, and unloading models
"""
from src.client.api_client import GPUOrchestratorClient


def main():
    client = GPUOrchestratorClient("http://localhost:8000")
    
    # Example 1: Check available models
    print("=" * 70)
    print("1. LIST AVAILABLE MODELS")
    print("=" * 70)
    
    try:
        models = client.list_models()
        print(f"✓ Available models: {len(models)} found")
        for model in models:
            print(f"  • {model['name']}")
            print(f"    Size: {model.get('size_mb', 'unknown')} MB")
            print(f"    GPU: {model.get('gpu_id', 'not loaded')}")
            print(f"    Pinned: {model.get('pinned', False)}")
    except Exception as e:
        print(f"✗ Error listing models: {e}")
    
    # Example 2: Load a model
    print("\n" + "=" * 70)
    print("2. LOAD MODEL")
    print("=" * 70)
    
    try:
        result = client.load_model(
            model_id="fraud-detection-v1",
            gpu_id=0,  # Optional: specify GPU
            return_timing=True
        )
        print(f"✓ Model loaded successfully")
        print(f"  Model: fraud-detection-v1")
        print(f"  GPU ID: {result['gpu_id']}")
        print(f"  Load time: {result['timing_ms']['load']:.2f}ms")
        print(f"  Memory used: {result.get('memory_mb', 'unknown')} MB")
    except Exception as e:
        print(f"✗ Error loading model: {e}")
    
    # Example 3: Pin a model (prevent eviction)
    print("\n" + "=" * 70)
    print("3. PIN MODEL (PREVENT EVICTION)")
    print("=" * 70)
    
    try:
        result = client.pin_model(model_id="fraud-detection-v1")
        print(f"✓ Model pinned successfully")
        print(f"  Model: fraud-detection-v1")
        print(f"  Status: Pinned (will not be evicted)")
    except Exception as e:
        print(f"✗ Error pinning model: {e}")
    
    # Example 4: Get model status
    print("\n" + "=" * 70)
    print("4. GET MODEL STATUS")
    print("=" * 70)
    
    try:
        status = client.get_model_status(model_id="fraud-detection-v1")
        print(f"✓ Model status retrieved")
        print(f"  Model: fraud-detection-v1")
        print(f"  Loaded: {status.get('loaded', False)}")
        print(f"  GPU ID: {status.get('gpu_id', 'N/A')}")
        print(f"  Memory (MB): {status.get('memory_mb', 'N/A')}")
        print(f"  Pinned: {status.get('pinned', False)}")
        print(f"  Access count: {status.get('access_count', 0)}")
        print(f"  Last accessed: {status.get('last_accessed', 'never')}")
    except Exception as e:
        print(f"✗ Error getting model status: {e}")
    
    # Example 5: Preload multiple critical models
    print("\n" + "=" * 70)
    print("5. PRELOAD CRITICAL MODELS")
    print("=" * 70)
    
    critical_models = [
        "fraud-detection-v1",
        "sentiment-analysis-v2",
        "recommendation-engine-v1"
    ]
    
    print(f"Preloading {len(critical_models)} critical models...")
    
    for model_id in critical_models:
        try:
            result = client.load_model(model_id=model_id)
            gpu_id = result.get('gpu_id')
            
            # Pin the model
            client.pin_model(model_id=model_id)
            
            print(f"  ✓ {model_id}: loaded on GPU {gpu_id} and pinned")
        except Exception as e:
            print(f"  ✗ {model_id}: {e}")
    
    # Example 6: Monitor model memory usage
    print("\n" + "=" * 70)
    print("6. MONITOR MEMORY USAGE")
    print("=" * 70)
    
    try:
        models = client.list_models()
        total_memory = 0
        pinned_memory = 0
        
        print(f"{'Model':<30} {'Size (MB)':<12} {'GPU':<5} {'Pinned':<8}")
        print("-" * 60)
        
        for model in models:
            size = model.get('size_mb', 0)
            gpu = model.get('gpu_id', 'N/A')
            pinned = model.get('pinned', False)
            
            print(f"{model['name']:<30} {size:<12} {gpu:<5} {str(pinned):<8}")
            
            total_memory += size
            if pinned:
                pinned_memory += size
        
        print("-" * 60)
        print(f"Total memory: {total_memory} MB")
        print(f"Pinned memory: {pinned_memory} MB")
        print(f"Evictable: {total_memory - pinned_memory} MB")
        
    except Exception as e:
        print(f"✗ Error monitoring memory: {e}")
    
    # Example 7: Unpin and unload models
    print("\n" + "=" * 70)
    print("7. UNPIN AND UNLOAD MODELS")
    print("=" * 70)
    
    model_to_unload = "sentiment-analysis-v2"
    
    try:
        # Unpin first
        print(f"Unpinning {model_to_unload}...")
        client.unpin_model(model_id=model_to_unload)
        print(f"  ✓ Model unpinned")
        
        # Then unload
        print(f"Unloading {model_to_unload}...")
        result = client.unload_model(model_id=model_to_unload)
        print(f"  ✓ Model unloaded")
        print(f"  Freed memory: {result.get('freed_memory_mb', 'unknown')} MB")
        
    except Exception as e:
        print(f"✗ Error unloading model: {e}")
    
    # Example 8: Model affinity (prefer certain GPUs)
    print("\n" + "=" * 70)
    print("8. SET MODEL AFFINITY")
    print("=" * 70)
    
    try:
        # Set affinity for high-priority model
        result = client.set_model_affinity(
            model_id="fraud-detection-v1",
            preferred_gpus=[0, 1],  # Prefer GPUs 0 and 1
            strict=False  # Allow fallback to other GPUs if needed
        )
        print(f"✓ Model affinity set")
        print(f"  Model: fraud-detection-v1")
        print(f"  Preferred GPUs: [0, 1]")
        print(f"  Strict mode: False (will fallback if needed)")
    except Exception as e:
        print(f"✗ Error setting affinity: {e}")
    
    # Example 9: Cache optimization
    print("\n" + "=" * 70)
    print("9. CACHE OPTIMIZATION")
    print("=" * 70)
    
    try:
        # Get cache stats
        stats = client.get_stats(stat_type="cache")
        print(f"✓ Cache stats retrieved")
        print(f"  Total hits: {stats.get('hits', 0)}")
        print(f"  Total misses: {stats.get('misses', 0)}")
        total = stats.get('hits', 0) + stats.get('misses', 0)
        if total > 0:
            hit_rate = stats.get('hits', 0) / total
            print(f"  Hit rate: {hit_rate:.2%}")
            
            # Recommendations
            if hit_rate < 0.5:
                print(f"\n  ⚠ Low cache hit rate!")
                print(f"    Recommendations:")
                print(f"    • Increase cache size")
                print(f"    • Preload more models")
                print(f"    • Improve prediction accuracy")
            else:
                print(f"\n  ✓ Cache efficiency is good")
    except Exception as e:
        print(f"✗ Error getting cache stats: {e}")
    
    # Example 10: Model performance profiling
    print("\n" + "=" * 70)
    print("10. MODEL PERFORMANCE PROFILING")
    print("=" * 70)
    
    try:
        # Get profiling stats for a model
        prof_stats = client.get_stats(stat_type="model", model_id="fraud-detection-v1")
        print(f"✓ Profiling stats for fraud-detection-v1:")
        print(f"  Total predictions: {prof_stats.get('predictions', 0)}")
        print(f"  Avg latency (ms): {prof_stats.get('avg_latency_ms', 0):.2f}")
        print(f"  P95 latency (ms): {prof_stats.get('p95_latency_ms', 0):.2f}")
        print(f"  P99 latency (ms): {prof_stats.get('p99_latency_ms', 0):.2f}")
        print(f"  Cache hit rate: {prof_stats.get('cache_hit_rate', 0):.2%}")
    except Exception as e:
        print(f"✗ Error profiling model: {e}")


if __name__ == "__main__":
    main()
