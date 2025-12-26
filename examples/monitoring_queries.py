"""
Monitoring queries example - Prometheus metrics and alerting
"""
import requests
import time
from typing import List, Dict
from src.client.api_client import GPUOrchestratorClient


class PrometheusClient:
    """Simple Prometheus API client"""
    
    def __init__(self, prometheus_url: str = "http://localhost:9090"):
        self.base_url = prometheus_url
    
    def query(self, query: str, time: int = None) -> Dict:
        """Execute a Prometheus query"""
        url = f"{self.base_url}/api/v1/query"
        params = {"query": query}
        if time:
            params["time"] = time
        
        try:
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Query failed: {e}")
            return {}
    
    def query_range(
        self,
        query: str,
        start: int,
        end: int,
        step: str = "15s"
    ) -> Dict:
        """Execute a range query over time"""
        url = f"{self.base_url}/api/v1/query_range"
        params = {
            "query": query,
            "start": start,
            "end": end,
            "step": step
        }
        
        try:
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Range query failed: {e}")
            return {}


def main():
    api_client = GPUOrchestratorClient("http://localhost:8000")
    prometheus = PrometheusClient("http://localhost:9090")
    
    # Example 1: Cache Hit Rate
    print("=" * 70)
    print("1. CACHE HIT RATE")
    print("=" * 70)
    
    try:
        # Prometheus query
        result = prometheus.query("rate(gpu_cache_hits_total[5m])")
        print(f"✓ Cache hits per second: {result}")
        
        # Also get via REST API
        stats = api_client.get_stats(stat_type="cache")
        total_hits = stats.get('hits', 0)
        total_misses = stats.get('misses', 0)
        
        if total_hits + total_misses > 0:
            hit_rate = total_hits / (total_hits + total_misses)
            print(f"  Total hits: {total_hits}")
            print(f"  Total misses: {total_misses}")
            print(f"  Hit rate: {hit_rate:.2%}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Example 2: GPU Utilization
    print("\n" + "=" * 70)
    print("2. GPU UTILIZATION")
    print("=" * 70)
    
    try:
        # Get current utilization
        status = api_client.status()
        print(f"✓ GPU Status:")
        print(f"  Total GPUs: {status['gpus']['count']}")
        print(f"  Total memory: {status['gpus']['total_memory_mb']} MB")
        print(f"  Available: {status['memory']['available_mb']} MB")
        
        # Calculate utilization
        if status['gpus']['total_memory_mb'] > 0:
            utilization = (
                (status['gpus']['total_memory_mb'] - status['memory']['available_mb']) /
                status['gpus']['total_memory_mb'] * 100
            )
            print(f"  Utilization: {utilization:.1f}%")
            
            # Alert thresholds
            if utilization > 90:
                print(f"  ⚠ CRITICAL: GPU utilization >90%")
            elif utilization > 80:
                print(f"  ⚠ WARNING: GPU utilization >80%")
            else:
                print(f"  ✓ GPU utilization is healthy")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Example 3: Scheduler Performance
    print("\n" + "=" * 70)
    print("3. SCHEDULER PERFORMANCE")
    print("=" * 70)
    
    try:
        # Multiple predictions to measure scheduler
        timings = []
        for _ in range(10):
            result = api_client.predict(
                model_id="fraud-detection-v1",
                input_data={"features": [0.1, 0.2, 0.3, 0.4, 0.5]},
                return_timing=True
            )
            scheduler_time = result['timing_ms']['scheduler']
            timings.append(scheduler_time)
        
        avg_time = sum(timings) / len(timings)
        max_time = max(timings)
        
        print(f"✓ Scheduler Performance:")
        print(f"  Avg time: {avg_time:.2f}ms")
        print(f"  Max time: {max_time:.2f}ms")
        print(f"  Threshold (SLA): < 1ms")
        
        if avg_time > 1.0:
            print(f"  ⚠ WARNING: Scheduler exceeding SLA")
        else:
            print(f"  ✓ Scheduler performance is good")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Example 4: Inference Latency Percentiles
    print("\n" + "=" * 70)
    print("4. INFERENCE LATENCY PERCENTILES")
    print("=" * 70)
    
    try:
        # Collect latency samples
        latencies = []
        print("  Collecting 100 samples...")
        
        for _ in range(100):
            result = api_client.predict(
                model_id="fraud-detection-v1",
                input_data={"features": [0.1, 0.2, 0.3, 0.4, 0.5]},
                return_timing=True
            )
            latencies.append(result['timing_ms']['total'])
        
        # Calculate percentiles
        sorted_latencies = sorted(latencies)
        
        print(f"✓ Latency Distribution (ms):")
        print(f"  Min: {sorted_latencies[0]:.2f}")
        print(f"  P10: {sorted_latencies[len(sorted_latencies)//10]:.2f}")
        print(f"  P25: {sorted_latencies[len(sorted_latencies)//4]:.2f}")
        print(f"  P50 (median): {sorted_latencies[len(sorted_latencies)//2]:.2f}")
        print(f"  P75: {sorted_latencies[int(len(sorted_latencies)*0.75)]:.2f}")
        print(f"  P95: {sorted_latencies[int(len(sorted_latencies)*0.95)]:.2f}")
        print(f"  P99: {sorted_latencies[int(len(sorted_latencies)*0.99)]:.2f}")
        print(f"  Max: {sorted_latencies[-1]:.2f}")
        print(f"  Average: {sum(latencies)/len(latencies):.2f}")
        
        # SLA check
        p99 = sorted_latencies[int(len(sorted_latencies)*0.99)]
        if p99 > 200:
            print(f"\n  ⚠ WARNING: P99 latency exceeds 200ms SLA")
        else:
            print(f"\n  ✓ Latency SLA met")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Example 5: Model Hot Spots
    print("\n" + "=" * 70)
    print("5. MODEL POPULARITY")
    print("=" * 70)
    
    try:
        models = api_client.list_models()
        print(f"✓ Model access counts:")
        
        # Sort by access count
        sorted_models = sorted(
            models,
            key=lambda x: x.get('access_count', 0),
            reverse=True
        )
        
        total_accesses = sum(m.get('access_count', 0) for m in sorted_models)
        
        for model in sorted_models[:5]:  # Top 5
            count = model.get('access_count', 0)
            pct = (count / total_accesses * 100) if total_accesses > 0 else 0
            print(f"  {model['name']:<30} {count:<10} ({pct:>5.1f}%)")
        
        print(f"\n  → Strategy: Pin top models to avoid evictions")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Example 6: Memory Pressure
    print("\n" + "=" * 70)
    print("6. MEMORY PRESSURE")
    print("=" * 70)
    
    try:
        status = api_client.status()
        cache_status = status.get('cache', {})
        
        size_mb = cache_status.get('size_mb', 1)
        used_mb = cache_status.get('used_mb', 0)
        available_mb = cache_status.get('available_mb', 0)
        
        if size_mb > 0:
            pressure = (used_mb / size_mb) * 100
            
            print(f"✓ Cache Memory Pressure:")
            print(f"  Total cache: {size_mb} MB")
            print(f"  Used: {used_mb} MB ({pressure:.1f}%)")
            print(f"  Available: {available_mb} MB")
            
            if pressure > 95:
                print(f"  ⚠ CRITICAL: Cache nearly full")
                print(f"    Action: Reduce cache size or add GPUs")
            elif pressure > 85:
                print(f"  ⚠ WARNING: High memory pressure")
                print(f"    Action: Monitor eviction rate")
            else:
                print(f"  ✓ Memory pressure is healthy")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Example 7: Error Rate Monitoring
    print("\n" + "=" * 70)
    print("7. ERROR TRACKING")
    print("=" * 70)
    
    try:
        # Simulate tracking errors by attempting some edge cases
        error_count = 0
        total_requests = 20
        
        for i in range(total_requests):
            try:
                result = api_client.predict(
                    model_id="fraud-detection-v1",
                    input_data={"features": [0.1, 0.2, 0.3, 0.4, 0.5]},
                )
            except Exception as e:
                error_count += 1
        
        error_rate = (error_count / total_requests) * 100
        
        print(f"✓ Error Rate:")
        print(f"  Requests: {total_requests}")
        print(f"  Errors: {error_count}")
        print(f"  Error rate: {error_rate:.2f}%")
        print(f"  SLA threshold: < 1% error rate")
        
        if error_rate > 1:
            print(f"  ⚠ WARNING: Error rate exceeds SLA")
        else:
            print(f"  ✓ Error rate is within SLA")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Example 8: Alert Rules Summary
    print("\n" + "=" * 70)
    print("8. ALERT RULES SUMMARY")
    print("=" * 70)
    
    alert_rules = [
        {
            "name": "HighGPUUtilization",
            "condition": "GPU utilization > 90%",
            "severity": "CRITICAL",
            "action": "Page on-call engineer"
        },
        {
            "name": "LowCacheHitRate",
            "condition": "Cache hit rate < 50% (5m avg)",
            "severity": "WARNING",
            "action": "Tune scheduler weights"
        },
        {
            "name": "HighLatency",
            "condition": "P99 latency > 200ms",
            "severity": "WARNING",
            "action": "Check GPU load, consider scaling"
        },
        {
            "name": "HighErrorRate",
            "condition": "Error rate > 1%",
            "severity": "CRITICAL",
            "action": "Check logs, rollback if needed"
        },
        {
            "name": "SchedulerSlow",
            "condition": "Avg scheduler time > 1ms",
            "severity": "WARNING",
            "action": "Profile scheduler, check CPU load"
        },
        {
            "name": "ModelEvictions",
            "condition": "Evictions > 10/min",
            "severity": "WARNING",
            "action": "Increase cache size or pin models"
        }
    ]
    
    print("✓ Configured Alert Rules:\n")
    for rule in alert_rules:
        print(f"  • {rule['name']}")
        print(f"    Condition: {rule['condition']}")
        print(f"    Severity: {rule['severity']}")
        print(f"    Action: {rule['action']}\n")


if __name__ == "__main__":
    main()
