"""
Locust load testing script for GPU VRAM Orchestrator
Run with: locust -f load_tests/locustfile.py --host=http://localhost:8000
"""
import random
import json
from locust import HttpUser, task, between, TaskSet, events
from statistics import mean, median, stdev

class MetricsCollector:
    def __init__(self):
        self.latencies = []
        self.errors = 0
        self.successes = 0
        self.predictions = 0

    def record_success(self, latency_ms):
        self.latencies.append(latency_ms)
        self.successes += 1
        self.predictions += 1

    def record_error(self):
        self.errors += 1

    def get_summary(self):
        if not self.latencies:
            return {
                'successes': 0,
                'errors': 0,
            }
        
        sorted_latencies = sorted(self.latencies)
        return {
            'total_predictions': self.predictions,
            'successes': self.successes,
            'errors': self.errors,
            'success_rate': self.successes / self.predictions if self.predictions > 0 else 0,
            'min_latency_ms': min(self.latencies),
            'max_latency_ms': max(self.latencies),
            'avg_latency_ms': mean(self.latencies),
            'median_latency_ms': median(self.latencies),
            'p95_latency_ms': sorted_latencies[int(len(sorted_latencies) * 0.95)],
            'p99_latency_ms': sorted_latencies[int(len(sorted_latencies) * 0.99)],
            'stdev_latency_ms': stdev(self.latencies) if len(self.latencies) > 1 else 0,
        }

metrics = MetricsCollector()

class OrchestratorBehavior(TaskSet):
    def on_start(self):
        """Initialize per-user data"""
        self.models = [
            'fraud-detection-v1',
            'sentiment-analysis-v2',
            'recommendation-engine-v1',
        ]

    def get_random_model(self):
        return random.choice(self.models)

    def generate_input_data(self):
        return {
            'features': [
                random.random(),
                random.random(),
                random.random(),
                random.random(),
                random.random(),
            ],
            'customer_id': f'cust_{random.randint(1000, 99999)}',
        }

    @task(80)  # 80% of tasks
    def predict(self):
        """Prediction - primary load"""
        model = self.get_random_model()
        input_data = self.generate_input_data()

        try:
            response = self.client.post(
                '/predict',
                json={
                    'model_id': model,
                    'input_data': input_data,
                    'return_timing': True,
                },
                catch_response=True
            )

            if response.status_code == 200:
                data = response.json()
                latency_ms = data.get('timing_ms', {}).get('total', 0)
                metrics.record_success(latency_ms)
                response.success()
            else:
                metrics.record_error()
                response.failure(f'Failed with status {response.status_code}')

        except Exception as e:
            metrics.record_error()
            self.client.logger.error(f'Request failed: {e}')

    @task(10)  # 10% of tasks
    def get_status(self):
        """Check system status"""
        try:
            response = self.client.get('/status', catch_response=True)
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f'Failed with status {response.status_code}')
        except Exception as e:
            self.client.logger.error(f'Status check failed: {e}')

    @task(5)  # 5% of tasks
    def list_models(self):
        """List available models"""
        try:
            response = self.client.get('/models', catch_response=True)
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f'Failed with status {response.status_code}')
        except Exception as e:
            self.client.logger.error(f'List models failed: {e}')

    @task(5)  # 5% of tasks
    def get_metrics(self):
        """Get Prometheus metrics"""
        try:
            response = self.client.get('/metrics', catch_response=True)
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f'Failed with status {response.status_code}')
        except Exception as e:
            self.client.logger.error(f'Get metrics failed: {e}')


class OrchestratorUser(HttpUser):
    """Main load testing user"""
    tasks = [OrchestratorBehavior]
    wait_time = between(0.01, 0.1)  # Wait 10-100ms between requests


class BurstUser(HttpUser):
    """High-frequency burst user"""
    tasks = [OrchestratorBehavior]
    wait_time = between(0.001, 0.01)  # Very short wait for burst traffic
    weight = 1  # Lower weight than normal users (1:4 ratio)


# Event handlers for summary reporting
@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """Print metrics summary on exit"""
    summary = metrics.get_summary()
    
    print("\n" + "=" * 70)
    print("LOAD TEST SUMMARY")
    print("=" * 70)
    print(f"Total predictions: {summary['total_predictions']}")
    print(f"Successes: {summary['successes']}")
    print(f"Errors: {summary['errors']}")
    print(f"Success rate: {summary['success_rate']:.2%}")
    print(f"\nLatency (ms):")
    print(f"  Min: {summary['min_latency_ms']:.2f}")
    print(f"  Avg: {summary['avg_latency_ms']:.2f}")
    print(f"  Median: {summary['median_latency_ms']:.2f}")
    print(f"  P95: {summary['p95_latency_ms']:.2f}")
    print(f"  P99: {summary['p99_latency_ms']:.2f}")
    print(f"  Max: {summary['max_latency_ms']:.2f}")
    print(f"  StdDev: {summary['stdev_latency_ms']:.2f}")
    print("=" * 70 + "\n")
