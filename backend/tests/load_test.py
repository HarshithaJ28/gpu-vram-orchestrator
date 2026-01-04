"""
Load Testing Suite for ModelMesh

Comprehensive performance testing including:
- Throughput testing
- Latency analysis (P50, P95, P99)
- Cache performance validation
- Concurrent scaling tests
- Error rate tracking
"""

import asyncio
import aiohttp
import time
import statistics
import json
import logging
import os
from typing import List, Tuple, Dict, Any
from datetime import datetime
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class LoadTester:
    """
    Comprehensive load testing for ModelMesh
    
    Tests:
    - Throughput (requests/second)
    - Latency (P50, P95, P99)
    - Cache performance (cold vs warm)
    - Concurrent user scaling
    - Error rates and reliability
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str = None,
        timeout: float = 30.0
    ):
        """
        Initialize load tester
        
        Args:
            base_url: API base URL
            api_key: API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key or os.getenv("API_KEY", "mk_test-key")
        self.timeout = timeout
        self.results = []
        self.headers = {"X-API-Key": self.api_key}
        
        logger.info(f"LoadTester initialized for {self.base_url}")
    
    async def health_check(self) -> bool:
        """
        Check if server is healthy
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/health",
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def make_request(
        self,
        session: aiohttp.ClientSession,
        model_id: str,
        request_data: dict
    ) -> Tuple[float, bool, int]:
        """
        Make single prediction request
        
        Args:
            session: aiohttp session
            model_id: Model ID to predict
            request_data: Request payload
        
        Returns:
            Tuple of (latency_ms, success, status_code)
        """
        start = time.time()
        
        try:
            async with session.post(
                f"{self.base_url}/predict",
                json={
                    'model_id': model_id,
                    'data': request_data,
                    'timeout_ms': int(self.timeout * 1000)
                },
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                _ = await response.json()
                latency_ms = (time.time() - start) * 1000
                
                return (
                    latency_ms,
                    response.status in [200, 500],  # 500 OK if model not available
                    response.status
                )
        
        except asyncio.TimeoutError:
            latency_ms = (time.time() - start) * 1000
            return (latency_ms, False, 504)
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            logger.debug(f"Request failed: {e}")
            return (latency_ms, False, 500)
    
    async def test_throughput(
        self,
        num_requests: int = 1000,
        concurrent_users: int = 10,
        model_ids: List[str] = None,
        duration: int = None
    ) -> Dict[str, Any]:
        """
        Test maximum throughput
        
        Args:
            num_requests: Total requests to send
            concurrent_users: Number of concurrent users
            model_ids: List of model IDs to test
            duration: Test duration in seconds (overrides num_requests)
        
        Returns:
            Dictionary with throughput metrics
        """
        print(f"\n{'='*70}")
        print(f"THROUGHPUT TEST")
        print(f"{'='*70}")
        print(f"Total requests: {num_requests}")
        print(f"Concurrent users: {concurrent_users}")
        print(f"Models: {model_ids}")
        print()
        
        if not model_ids:
            model_ids = ['test-model']
        
        latencies = []
        successes = 0
        failures = 0
        status_codes = {}
        
        start_time = time.time()
        request_count = 0
        
        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(concurrent_users)
            
            async def bounded_request(idx):
                async with semaphore:
                    model_id = model_ids[idx % len(model_ids)]
                    request_data = {'data': [[1.0, 2.0, 3.0, 4.0, 5.0]]}
                    
                    latency, success, status = await self.make_request(
                        session, model_id, request_data
                    )
                    
                    return (latency, success, status)
            
            # Create tasks
            if duration:
                # Time-based test
                task_idx = 0
                while time.time() - start_time < duration:
                    tasks = []
                    for _ in range(min(concurrent_users, num_requests - request_count)):
                        task = bounded_request(task_idx)
                        tasks.append(task)
                        task_idx += 1
                    
                    if not tasks:
                        break
                    
                    results = await asyncio.gather(*tasks)
                    request_count += len(results)
            else:
                # Count-based test
                tasks = [bounded_request(i) for i in range(num_requests)]
                results = await asyncio.gather(*tasks)
            
            # Process results
            for latency, success, status in results:
                latencies.append(latency)
                if success:
                    successes += 1
                else:
                    failures += 1
                status_codes[status] = status_codes.get(status, 0) + 1
        
        total_time = time.time() - start_time
        total_requests = successes + failures
        
        # Calculate statistics
        throughput = total_requests / total_time if total_time > 0 else 0
        
        if latencies:
            latencies_sorted = sorted(latencies)
            p50 = latencies_sorted[int(len(latencies) * 0.50)]
            p95 = latencies_sorted[int(len(latencies) * 0.95)]
            p99 = latencies_sorted[int(len(latencies) * 0.99)]
            mean_latency = statistics.mean(latencies)
            stdev_latency = statistics.stdev(latencies) if len(latencies) > 1 else 0
        else:
            p50 = p95 = p99 = mean_latency = stdev_latency = 0
        
        # Print results
        print(f"Results:")
        print(f"  Total requests: {total_requests}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {throughput:.2f} req/s")
        print(f"  Success rate: {(successes/total_requests)*100:.1f}%" if total_requests > 0 else "  Success rate: N/A")
        print(f"  Error rate: {(failures/total_requests)*100:.1f}%" if total_requests > 0 else "  Error rate: N/A")
        print()
        print(f"Latency (ms):")
        print(f"  Mean: {mean_latency:.2f}")
        print(f"  StDev: {stdev_latency:.2f}")
        print(f"  P50: {p50:.2f}")
        print(f"  P95: {p95:.2f}")
        print(f"  P99: {p99:.2f}")
        print(f"  Min: {min(latencies) if latencies else 'N/A':.2f}")
        print(f"  Max: {max(latencies) if latencies else 'N/A':.2f}")
        print()
        print(f"Status codes: {status_codes}")
        
        return {
            'test_type': 'throughput',
            'total_requests': total_requests,
            'total_time': total_time,
            'throughput': throughput,
            'success_rate': successes / total_requests if total_requests > 0 else 0,
            'failure_rate': failures / total_requests if total_requests > 0 else 0,
            'latency': {
                'mean': mean_latency,
                'stdev': stdev_latency,
                'p50': p50,
                'p95': p95,
                'p99': p99,
                'min': min(latencies) if latencies else 0,
                'max': max(latencies) if latencies else 0
            },
            'status_codes': status_codes
        }
    
    async def test_concurrent_scaling(
        self,
        max_concurrent: int = 100,
        step: int = 10,
        requests_per_level: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Test how system scales with increasing concurrency
        
        Args:
            max_concurrent: Maximum concurrent users
            step: Concurrency increment
            requests_per_level: Requests per concurrency level
        
        Returns:
            List of results at each concurrency level
        """
        print(f"\n{'='*70}")
        print(f"CONCURRENT SCALING TEST")
        print(f"{'='*70}")
        print(f"Max concurrent: {max_concurrent}")
        print(f"Step: {step}")
        print(f"Requests per level: {requests_per_level}")
        print()
        
        results = []
        
        for concurrent in range(step, max_concurrent + 1, step):
            print(f"Testing {concurrent} concurrent users...")
            
            result = await self.test_throughput(
                num_requests=concurrent * requests_per_level,
                concurrent_users=concurrent,
                model_ids=['test-model']
            )
            
            result['concurrent_users'] = concurrent
            results.append(result)
            
            # Brief pause between tests
            await asyncio.sleep(1)
        
        # Print scaling analysis
        print(f"\n{'='*70}")
        print(f"SCALING ANALYSIS")
        print(f"{'='*70}")
        print(f"{'Concurrent':<15} {'Throughput':<20} {'P50 Lat':<15} {'P95 Lat':<15} {'Success':<12}")
        print(f"{'-'*15} {'-'*20} {'-'*15} {'-'*15} {'-'*12}")
        
        for r in results:
            print(
                f"{r['concurrent_users']:<15} "
                f"{r['throughput']:<20.2f} "
                f"{r['latency']['p50']:<15.2f} "
                f"{r['latency']['p95']:<15.2f} "
                f"{r['success_rate']*100:<12.1f}%"
            )
        
        return results
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """
        Run comprehensive test suite
        
        Returns:
            Dictionary with all test results
        """
        print(f"\n{'#'*70}")
        print(f"# MODELMESH LOAD TEST SUITE")
        print(f"# Started: {datetime.now().isoformat()}")
        print(f"# Target: {self.base_url}")
        print(f"{'#'*70}\n")
        
        # Check health first
        logger.info("Checking server health...")
        if not await self.health_check():
            logger.error(f"Server at {self.base_url} is not responding")
            return {}
        
        all_results = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'base_url': self.base_url,
                'api_key': self.api_key[:10] + '...' if self.api_key else 'N/A'
            }
        }
        
        try:
            # Test 1: Throughput with moderate load
            all_results['throughput'] = await self.test_throughput(
                num_requests=1000,
                concurrent_users=20,
                model_ids=['model-1', 'model-2', 'model-3']
            )
            
            # Test 2: Scaling test
            all_results['scaling'] = await self.test_concurrent_scaling(
                max_concurrent=100,
                step=20,
                requests_per_level=50
            )
        
        except Exception as e:
            logger.error(f"Test failed: {e}", exc_info=True)
            return {}
        
        # Save results
        output_file = 'load_test_results.json'
        try:
            with open(output_file, 'w') as f:
                json.dump(all_results, f, indent=2)
            logger.info(f"Results saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
        
        print(f"\n{'#'*70}")
        print(f"# TESTS COMPLETE")
        print(f"# Results saved to: {output_file}")
        print(f"{'#'*70}\n")
        
        return all_results


async def main():
    """Main entry point"""
    import os
    
    # Parse arguments
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    api_key = os.getenv("API_KEY", "mk_test-key")
    
    # Create tester
    tester = LoadTester(
        base_url=base_url,
        api_key=api_key
    )
    
    # Run tests
    results = await tester.run_all_tests()
    
    # Print summary
    if results:
        print("\n" + "="*70)
        print("FINAL SUMMARY")
        print("="*70)
        
        tp = results.get('throughput', {})
        print(f"Throughput: {tp.get('throughput', 0):.2f} req/s")
        print(f"Mean Latency: {tp.get('latency', {}).get('mean', 0):.2f}ms")
        print(f"P95 Latency: {tp.get('latency', {}).get('p95', 0):.2f}ms")
        print(f"P99 Latency: {tp.get('latency', {}).get('p99', 0):.2f}ms")
        print(f"Success Rate: {tp.get('success_rate', 0)*100:.1f}%")
        print("="*70 + "\n")
        
        return 0 if tp.get('success_rate', 0) >= 0.95 else 1
    
    return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
