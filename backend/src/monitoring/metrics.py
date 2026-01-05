"""Prometheus Metrics Module

Exports metrics for monitoring GPU orchestrator performance.
Includes cache, GPU, scheduler, and latency metrics.
"""

from typing import Dict, List, Optional
import logging
from threading import RLock

logger = logging.getLogger(__name__)

# Try to import prometheus_client, but make it optional
try:
    from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest, REGISTRY
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed, metrics disabled")


# Global metrics registry for testing
_metrics_instances = {}


class MetricsCollector:
    """
    Collect and export metrics for GPU orchestrator

    Metrics tracked:
    - Cache: hits, misses, hit rate, evictions
    - GPU: utilization, memory usage, models loaded
    - Scheduler: selection time, weight scores
    - Latency: inference, model loading, scheduling
    - Cost: estimated GPU hours and cost savings
    """

    def __init__(self, use_prometheus: bool = True):
        """
        Initialize metrics collector

        Args:
            use_prometheus: Whether to use Prometheus (can be disabled for testing)
        """
        self.lock = RLock()
        self.use_prometheus = use_prometheus and PROMETHEUS_AVAILABLE
        self.instance_id = id(self)

        # In-memory counters (always maintained as fallback)
        self.cache_hits = 0
        self.cache_misses = 0
        self.gpu_utilization_pct = {}
        self.models_loaded_per_gpu = {}
        self.scheduler_times = {}
        self.inference_latencies = {}
        self.model_load_times = {}
        self.cost_gpu_hours = 0.0
        self.cost_savings = 0.0
        self.gpu_temperature = {}
        self.gpu_power = {}
        self.gpu_memory = {}

        if self.use_prometheus:
            self._init_prometheus_metrics()

        logger.info(f"MetricsCollector initialized (prometheus: {self.use_prometheus})")

    def _init_prometheus_metrics(self):
        """Initialize Prometheus metrics"""
        # Use instance-specific metric names to avoid conflicts in testing
        try:
            # Cache metrics
            self.prom_cache_hits = Counter(
                f'gpu_cache_hits_total_{self.instance_id}',
                'Total cache hits'
            )
            self.prom_cache_misses = Counter(
                f'gpu_cache_misses_total_{self.instance_id}',
                'Total cache misses'
            )
            self.prom_evictions = Counter(
                f'cache_evictions_total_{self.instance_id}',
                'Total cache evictions'
            )

            # GPU metrics
            self.prom_gpu_utilization = Gauge(
                f'gpu_utilization_percent_{self.instance_id}',
                'GPU utilization (%)',
                ['gpu_id']
            )
            self.prom_models_loaded = Gauge(
                f'gpu_models_loaded_{self.instance_id}',
                'Number of models loaded on GPU',
                ['gpu_id']
            )

            # Scheduler metrics
            self.prom_scheduler_time = Histogram(
                f'scheduler_selection_time_ms_{self.instance_id}',
                'Time to select best GPU (ms)',
                buckets=[0.1, 0.5, 1, 5, 10, 50]
            )

            # Latency metrics
            self.prom_inference_latency = Histogram(
                f'inference_latency_ms_{self.instance_id}',
                'Inference latency (ms)',
                ['model_id'],
                buckets=[10, 50, 100, 250, 500, 1000, 2000, 5000]
            )
            self.prom_model_load_time = Histogram(
                f'model_load_time_ms_{self.instance_id}',
                'Model load time (ms)',
                ['model_id'],
                buckets=[100, 500, 1000, 2000, 5000, 10000]
            )

            # Cost
            self.prom_gpu_hours = Counter(
                f'gpu_hours_total_{self.instance_id}',
                'Total GPU hours'
            )
            self.prom_cost_savings = Gauge(
                f'cost_savings_dollars_{self.instance_id}',
                'Cost savings'
            )

            # GPU Hardware Monitoring
            self.prom_gpu_temp = Gauge(
                f'gpu_temperature_celsius_{self.instance_id}',
                'GPU temperature in Celsius',
                ['gpu_id']
            )
            self.prom_gpu_power = Gauge(
                f'gpu_power_watts_{self.instance_id}',
                'GPU power consumption in watts',
                ['gpu_id']
            )
            self.prom_gpu_memory_mb = Gauge(
                f'gpu_memory_used_mb_{self.instance_id}',
                'GPU memory used in MB',
                ['gpu_id']
            )
        except ValueError as e:
            # Metric already registered, fallback to memory mode
            logger.warning(f"Prometheus metric conflict: {e}, using memory metrics only")
            self.use_prometheus = False

    def record_cache_hit(self, gpu_id: int):
        """Record cache hit"""
        with self.lock:
            self.cache_hits += 1
            if self.use_prometheus:
                try:
                    self.prom_cache_hits.inc()
                except Exception as e:
                    logger.warning(f"Failed to record Prometheus metric: {e}")

    def record_cache_miss(self, gpu_id: int):
        """Record cache miss"""
        with self.lock:
            self.cache_misses += 1
            if self.use_prometheus:
                try:
                    self.prom_cache_misses.inc()
                except Exception as e:
                    logger.warning(f"Failed to record Prometheus metric: {e}")

    def record_gpu_utilization(self, gpu_id: int, percent: float):
        """Record GPU utilization"""
        with self.lock:
            self.gpu_utilization_pct[gpu_id] = percent
            if self.use_prometheus:
                try:
                    self.prom_gpu_utilization.labels(gpu_id=gpu_id).set(percent)
                except Exception as e:
                    logger.warning(f"Failed to record Prometheus metric: {e}")

    def record_models_loaded(self, gpu_id: int, count: int):
        """Record number of models loaded"""
        with self.lock:
            self.models_loaded_per_gpu[gpu_id] = count
            if self.use_prometheus:
                try:
                    self.prom_models_loaded.labels(gpu_id=gpu_id).set(count)
                except Exception as e:
                    logger.warning(f"Failed to record Prometheus metric: {e}")

    def record_scheduler_time(self, model_id: str, time_ms: float):
        """Record scheduler selection time"""
        with self.lock:
            self.scheduler_times[model_id] = time_ms
            if self.use_prometheus:
                try:
                    self.prom_scheduler_time.observe(time_ms)
                except Exception as e:
                    logger.warning(f"Failed to record Prometheus metric: {e}")

    def record_inference_latency(self, model_id: str, latency_ms: float):
        """Record inference latency"""
        with self.lock:
            self.inference_latencies[model_id] = latency_ms
            if self.use_prometheus:
                try:
                    self.prom_inference_latency.labels(model_id=model_id).observe(latency_ms)
                except Exception as e:
                    logger.warning(f"Failed to record Prometheus metric: {e}")

    def record_model_load_time(self, model_id: str, time_ms: float):
        """Record model load time"""
        with self.lock:
            self.model_load_times[model_id] = time_ms
            if self.use_prometheus:
                try:
                    self.prom_model_load_time.labels(model_id=model_id).observe(time_ms)
                except Exception as e:
                    logger.warning(f"Failed to record Prometheus metric: {e}")

    def record_cost_gpu_hour(self, gpu_id: int, hours: float):
        """Record GPU hours used"""
        with self.lock:
            self.cost_gpu_hours += hours
            if self.use_prometheus:
                try:
                    self.prom_gpu_hours.inc(hours)
                except Exception as e:
                    logger.warning(f"Failed to record Prometheus metric: {e}")

    def record_cost_savings(self, amount: float):
        """Record cost savings"""
        with self.lock:
            self.cost_savings += amount
            if self.use_prometheus:
                try:
                    self.prom_cost_savings.set(self.cost_savings)
                except Exception as e:
                    logger.warning(f"Failed to record Prometheus metric: {e}")

    def record_gpu_temperature(self, gpu_id: int, temp_celsius: float):
        """Record GPU temperature in Celsius"""
        with self.lock:
            self.gpu_temperature[gpu_id] = temp_celsius
            if self.use_prometheus:
                try:
                    self.prom_gpu_temp.labels(gpu_id=gpu_id).set(temp_celsius)
                except Exception as e:
                    logger.warning(f"Failed to record GPU temperature: {e}")

    def record_gpu_power(self, gpu_id: int, power_watts: float):
        """Record GPU power consumption in watts"""
        with self.lock:
            self.gpu_power[gpu_id] = power_watts
            if self.use_prometheus:
                try:
                    self.prom_gpu_power.labels(gpu_id=gpu_id).set(power_watts)
                except Exception as e:
                    logger.warning(f"Failed to record GPU power: {e}")

    def record_gpu_memory(self, gpu_id: int, memory_mb: float):
        """Record GPU memory usage in MB"""
        with self.lock:
            self.gpu_memory[gpu_id] = memory_mb
            if self.use_prometheus:
                try:
                    self.prom_gpu_memory_mb.labels(gpu_id=gpu_id).set(memory_mb)
                except Exception as e:
                    logger.warning(f"Failed to record GPU memory: {e}")

    def get_cache_hit_rate(self) -> float:
        """Get cache hit rate (0-1)"""
        with self.lock:
            total = self.cache_hits + self.cache_misses
            if total == 0:
                return 0.0
            return self.cache_hits / total

    def reset(self):
        """Reset all metrics"""
        with self.lock:
            self.cache_hits = 0
            self.cache_misses = 0
            self.gpu_utilization_pct.clear()
            self.models_loaded_per_gpu.clear()
            self.scheduler_times.clear()
            self.inference_latencies.clear()
            self.model_load_times.clear()
            self.cost_gpu_hours = 0.0
            self.cost_savings = 0.0
            self.gpu_temperature.clear()
            self.gpu_power.clear()
            self.gpu_memory.clear()

    def export_metrics_text(self) -> str:
        """
        Export metrics in Prometheus text format

        Returns:
            String in Prometheus exposition format
        """
        with self.lock:
            if self.use_prometheus:
                try:
                    return generate_latest().decode('utf-8')
                except Exception:
                    pass
            
            # Fallback: return simple text summary
            lines = ["# GPU VRAM Orchestrator Metrics (In-Memory)\n"]
            lines.append(f"cache_hits_total {self.cache_hits}\n")
            lines.append(f"cache_misses_total {self.cache_misses}\n")
            for gpu_id, util in self.gpu_utilization_pct.items():
                lines.append(f"gpu_utilization_percent{{gpu_id=\"{gpu_id}\"}} {util}\n")
            return "".join(lines)

    def export_metrics_dict(self) -> Dict:
        """Get metrics as dictionary"""
        with self.lock:
            return {
                'cache_hits': self.cache_hits,
                'cache_misses': self.cache_misses,
                'cache_hit_rate': self.get_cache_hit_rate(),
                'gpu_utilization': self.gpu_utilization_pct.copy(),
                'models_loaded': self.models_loaded_per_gpu.copy(),
                'scheduler_times': self.scheduler_times.copy(),
                'inference_latencies': self.inference_latencies.copy(),
                'model_load_times': self.model_load_times.copy(),
                'cost_gpu_hours': self.cost_gpu_hours,
                'cost_savings': self.cost_savings,
                'gpu_temperature': self.gpu_temperature.copy(),
                'gpu_power': self.gpu_power.copy(),
                'gpu_memory': self.gpu_memory.copy(),
            }
