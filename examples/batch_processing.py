"""
Batch processing example - Efficient batch inference with metrics
"""
import time
import json
from typing import List, Dict
from src.client.api_client import GPUOrchestratorClient


class BatchProcessor:
    def __init__(self, api_url: str = "http://localhost:8000"):
        self.client = GPUOrchestratorClient(api_url)
        self.results = []
        
    def process_batch(
        self,
        model_id: str,
        batch_data: List[Dict],
        batch_size: int = 32,
        collect_timing: bool = True
    ) -> Dict:
        """
        Process a batch of inputs through the GPU orchestrator.
        
        Args:
            model_id: ID of the model to use
            batch_data: List of input dictionaries
            batch_size: Number of items per batch
            collect_timing: Whether to collect timing metrics
            
        Returns:
            Dictionary with results and statistics
        """
        print(f"Processing {len(batch_data)} items with model {model_id}")
        print(f"Batch size: {batch_size}")
        
        all_results = []
        timings = []
        gpu_distribution = {}
        cache_stats = {"hits": 0, "misses": 0}
        
        start_time = time.time()
        
        # Process in batches
        for i in range(0, len(batch_data), batch_size):
            batch = batch_data[i:i+batch_size]
            batch_num = i // batch_size + 1
            
            print(f"\n  Batch {batch_num}: Processing {len(batch)} items...")
            batch_start = time.time()
            
            for item_idx, item in enumerate(batch):
                try:
                    result = self.client.predict(
                        model_id=model_id,
                        input_data=item,
                        return_timing=collect_timing
                    )
                    
                    all_results.append({
                        "index": i + item_idx,
                        "input": item,
                        "prediction": result.get("predictions"),
                        "gpu_id": result.get("gpu_id"),
                        "latency_ms": result.get("timing_ms", {}).get("total")
                    })
                    
                    # Collect metrics
                    if collect_timing:
                        timings.append(result.get("timing_ms", {}).get("total", 0))
                    
                    gpu_id = result.get("gpu_id")
                    gpu_distribution[gpu_id] = gpu_distribution.get(gpu_id, 0) + 1
                    
                except Exception as e:
                    print(f"    ✗ Error processing item {item_idx}: {e}")
                    all_results.append({
                        "index": i + item_idx,
                        "error": str(e)
                    })
            
            batch_time = time.time() - batch_start
            batch_throughput = len(batch) / batch_time
            print(f"    ✓ Batch {batch_num} completed in {batch_time:.2f}s ({batch_throughput:.1f} items/s)")
        
        total_time = time.time() - start_time
        
        # Collect final statistics
        try:
            stats = self.client.get_stats(stat_type="cache")
            cache_stats = {
                "hits": stats.get("hits", 0),
                "misses": stats.get("misses", 0)
            }
        except:
            pass
        
        # Compile results
        successful = len([r for r in all_results if "prediction" in r])
        failed = len([r for r in all_results if "error" in r])
        
        summary = {
            "model_id": model_id,
            "total_items": len(batch_data),
            "successful": successful,
            "failed": failed,
            "success_rate": successful / len(batch_data) if batch_data else 0,
            "total_time_s": total_time,
            "throughput_items_per_s": len(batch_data) / total_time if total_time > 0 else 0,
            "timings": {
                "min_ms": min(timings) if timings else 0,
                "max_ms": max(timings) if timings else 0,
                "avg_ms": sum(timings) / len(timings) if timings else 0,
                "p50_ms": sorted(timings)[len(timings)//2] if timings else 0,
                "p95_ms": sorted(timings)[int(len(timings)*0.95)] if timings else 0,
                "p99_ms": sorted(timings)[int(len(timings)*0.99)] if timings else 0,
            },
            "gpu_distribution": gpu_distribution,
            "cache_stats": cache_stats
        }
        
        self.results = all_results
        return summary


def main():
    processor = BatchProcessor()
    
    # Example 1: Simple batch processing
    print("=" * 70)
    print("EXAMPLE 1: SIMPLE BATCH PROCESSING")
    print("=" * 70)
    
    # Generate sample data (100 items)
    sample_data = [
        {
            "features": [
                0.1 * (i % 10),
                0.2 * ((i+1) % 10),
                0.3 * ((i+2) % 10),
                0.4 * ((i+3) % 10),
                0.5 * ((i+4) % 10)
            ],
            "customer_id": f"cust_{i:05d}"
        }
        for i in range(100)
    ]
    
    summary = processor.process_batch(
        model_id="fraud-detection-v1",
        batch_data=sample_data,
        batch_size=32
    )
    
    # Print summary
    print("\n" + "=" * 70)
    print("BATCH PROCESSING SUMMARY")
    print("=" * 70)
    print(f"✓ Model: {summary['model_id']}")
    print(f"  Total items: {summary['total_items']}")
    print(f"  Successful: {summary['successful']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Success rate: {summary['success_rate']:.2%}")
    print(f"\n  Performance:")
    print(f"    Total time: {summary['total_time_s']:.2f}s")
    print(f"    Throughput: {summary['throughput_items_per_s']:.1f} items/s")
    print(f"\n  Latency (ms):")
    print(f"    Min: {summary['timings']['min_ms']:.2f}")
    print(f"    Avg: {summary['timings']['avg_ms']:.2f}")
    print(f"    P50: {summary['timings']['p50_ms']:.2f}")
    print(f"    P95: {summary['timings']['p95_ms']:.2f}")
    print(f"    P99: {summary['timings']['p99_ms']:.2f}")
    print(f"    Max: {summary['timings']['max_ms']:.2f}")
    print(f"\n  GPU Distribution:")
    for gpu_id, count in summary['gpu_distribution'].items():
        pct = count / summary['successful'] * 100 if summary['successful'] > 0 else 0
        print(f"    GPU {gpu_id}: {count} items ({pct:.1f}%)")
    print(f"\n  Cache Performance:")
    print(f"    Hits: {summary['cache_stats']['hits']}")
    print(f"    Misses: {summary['cache_stats']['misses']}")
    hit_rate = (summary['cache_stats']['hits'] / 
                (summary['cache_stats']['hits'] + summary['cache_stats']['misses']))
    print(f"    Hit rate: {hit_rate:.2%}")
    
    # Example 2: Different models (demonstrating scheduler)
    print("\n" + "=" * 70)
    print("EXAMPLE 2: MULTIPLE MODELS")
    print("=" * 70)
    
    models_to_test = [
        "fraud-detection-v1",
        "sentiment-analysis-v2",
        "recommendation-engine-v1"
    ]
    
    results_by_model = {}
    for model in models_to_test:
        print(f"\nTesting model: {model}")
        sample_data = [
            {"features": [0.1 * (i % 10) for _ in range(5)]}
            for i in range(50)
        ]
        
        summary = processor.process_batch(
            model_id=model,
            batch_data=sample_data,
            batch_size=25
        )
        
        results_by_model[model] = summary
        print(f"  Throughput: {summary['throughput_items_per_s']:.1f} items/s")
        print(f"  Avg latency: {summary['timings']['avg_ms']:.2f}ms")
    
    # Compare models
    print("\n" + "=" * 70)
    print("MODEL COMPARISON")
    print("=" * 70)
    print(f"{'Model':<30} {'Throughput':<15} {'Avg Latency':<15}")
    print("-" * 60)
    for model, summary in results_by_model.items():
        print(f"{model:<30} {summary['throughput_items_per_s']:<15.1f} {summary['timings']['avg_ms']:<15.2f}ms")


if __name__ == "__main__":
    main()
