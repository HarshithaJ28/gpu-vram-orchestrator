"""
Basic inference example - Simple prediction with GPU orchestrator
"""
import json
from src.client.api_client import GPUOrchestratorClient


def main():
    # Initialize client
    client = GPUOrchestratorClient("http://localhost:8000")

    # Example 1: Check system status
    print("=" * 60)
    print("1. SYSTEM STATUS")
    print("=" * 60)
    
    try:
        status = client.status()
        print(f"✓ System is healthy")
        print(f"  GPUs: {status['gpus']['count']}")
        print(f"  Total Memory: {status['gpus']['total_memory_mb']} MB")
        print(f"  Available Memory: {status['memory']['available_mb']} MB")
        print(f"  Cache Size: {status['cache']['size_mb']} MB")
        print(f"  Cache Hit Rate: {status['cache']['hit_rate']:.2%}")
    except Exception as e:
        print(f"✗ Error fetching status: {e}")
        return

    # Example 2: Run a simple prediction
    print("\n" + "=" * 60)
    print("2. SIMPLE PREDICTION")
    print("=" * 60)
    
    try:
        result = client.predict(
            model_id="fraud-detection-v1",
            input_data={
                "features": [0.5, 0.2, 0.8, 0.1, 0.3],
                "transaction_amount": 150.00
            },
            return_timing=True
        )
        
        print(f"✓ Prediction successful")
        print(f"  Model: fraud-detection-v1")
        print(f"  GPU ID: {result['gpu_id']}")
        print(f"  Prediction: {result['predictions']}")
        print(f"  Confidence: {result['confidence']:.2%}" if 'confidence' in result else "")
        print(f"\n  Timing breakdown:")
        print(f"    Scheduler: {result['timing_ms']['scheduler']:.2f}ms")
        print(f"    Load: {result['timing_ms']['load']:.2f}ms")
        print(f"    Inference: {result['timing_ms']['inference']:.2f}ms")
        print(f"    Total: {result['timing_ms']['total']:.2f}ms")
        
    except Exception as e:
        print(f"✗ Prediction failed: {e}")

    # Example 3: Multiple predictions to see caching in action
    print("\n" + "=" * 60)
    print("3. CACHING IN ACTION")
    print("=" * 60)
    
    timings = []
    for i in range(5):
        try:
            result = client.predict(
                model_id="fraud-detection-v1",
                input_data={"features": [0.1, 0.2, 0.3, 0.4, 0.5]},
                return_timing=True
            )
            timing = result['timing_ms']['total']
            timings.append(timing)
            print(f"  Request {i+1}: {timing:.2f}ms")
        except Exception as e:
            print(f"✗ Request {i+1} failed: {e}")
    
    if timings:
        print(f"\n  Average: {sum(timings)/len(timings):.2f}ms")
        print(f"  First call (no cache): {timings[0]:.2f}ms")
        print(f"  Later calls (cached):  {sum(timings[1:])/len(timings[1:]):.2f}ms")
        print(f"  Speed improvement: {timings[0]/sum(timings[1:])*len(timings[1:]):.1f}x")

    # Example 4: Get cache statistics
    print("\n" + "=" * 60)
    print("4. CACHE STATISTICS")
    print("=" * 60)
    
    try:
        stats = client.get_stats(stat_type="cache")
        print(f"✓ Cache stats retrieved")
        print(f"  Total hits: {stats.get('hits', 0)}")
        print(f"  Total misses: {stats.get('misses', 0)}")
        print(f"  Evictions: {stats.get('evictions', 0)}")
        ratio = stats.get('hits', 0) / (stats.get('hits', 0) + stats.get('misses', 1))
        print(f"  Hit rate: {ratio:.2%}")
    except Exception as e:
        print(f"✗ Error fetching cache stats: {e}")

    # Example 5: Get metrics in Prometheus format
    print("\n" + "=" * 60)
    print("5. PROMETHEUS METRICS")
    print("=" * 60)
    
    try:
        metrics = client.metrics(format='json')
        print(f"✓ Metrics retrieved:")
        print(f"  Cache hits: {metrics.get('cache_hits', 0)}")
        print(f"  Cache misses: {metrics.get('cache_misses', 0)}")
        print(f"  Models loaded: {metrics.get('models_loaded', 0)}")
        print(f"  GPU utilization: {metrics.get('gpu_utilization', 0):.1f}%")
        print(f"  Avg latency: {metrics.get('avg_latency_ms', 0):.2f}ms")
    except Exception as e:
        print(f"✗ Error fetching metrics: {e}")


if __name__ == "__main__":
    main()
