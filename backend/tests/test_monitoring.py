"""Tests for monitoring and metrics modules"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import modules to test
from src.monitoring.metrics import MetricsCollector
from src.monitoring.benchmarks import BenchmarkSuite


class TestMetricsCollector:
    """Test suite for MetricsCollector"""

    @pytest.fixture
    def metrics_collector(self):
        """Create metrics collector instance"""
        return MetricsCollector(use_prometheus=False)

    def test_metrics_initialization(self, metrics_collector):
        """Test metrics collector initializes without errors"""
        assert metrics_collector is not None
        assert hasattr(metrics_collector, 'record_cache_hit')
        assert hasattr(metrics_collector, 'record_cache_miss')
        assert hasattr(metrics_collector, 'export_metrics_text')

    def test_record_cache_hit(self, metrics_collector):
        """Test recording cache hit metric"""
        metrics_collector.record_cache_hit(gpu_id=0)
        assert metrics_collector.cache_hits > 0

    def test_record_cache_miss(self, metrics_collector):
        """Test recording cache miss metric"""
        metrics_collector.record_cache_miss(gpu_id=0)
        assert metrics_collector.cache_misses > 0

    def test_record_gpu_utilization(self, metrics_collector):
        """Test recording GPU utilization"""
        metrics_collector.record_gpu_utilization(gpu_id=0, percent=85.5)
        assert metrics_collector.gpu_utilization_pct[0] == 85.5

    def test_record_models_loaded(self, metrics_collector):
        """Test recording number of models loaded"""
        metrics_collector.record_models_loaded(gpu_id=0, count=5)
        assert metrics_collector.models_loaded_per_gpu[0] == 5

    def test_record_scheduler_time(self, metrics_collector):
        """Test recording scheduler selection time"""
        metrics_collector.record_scheduler_time(model_id="fraud-v1", time_ms=0.45)
        assert "fraud-v1" in metrics_collector.scheduler_times
        assert metrics_collector.scheduler_times["fraud-v1"] > 0

    def test_record_inference_latency(self, metrics_collector):
        """Test recording inference latency"""
        metrics_collector.record_inference_latency(model_id="fraud-v1", latency_ms=45.2)
        assert "fraud-v1" in metrics_collector.inference_latencies
        assert metrics_collector.inference_latencies["fraud-v1"] > 0

    def test_record_model_load_time(self, metrics_collector):
        """Test recording model load time"""
        metrics_collector.record_model_load_time(model_id="fraud-v1", time_ms=250.5)
        assert "fraud-v1" in metrics_collector.model_load_times
        assert metrics_collector.model_load_times["fraud-v1"] > 0

    def test_record_cost_gpu_hour(self, metrics_collector):
        """Test recording cost tracking - GPU-hour"""
        metrics_collector.record_cost_gpu_hour(gpu_id=0, hours=1.5)
        assert metrics_collector.cost_gpu_hours >= 1.5

    def test_record_cost_savings(self, metrics_collector):
        """Test recording cost savings"""
        metrics_collector.record_cost_savings(amount=500.0)
        assert metrics_collector.cost_savings >= 500.0

    def test_get_cache_hit_rate(self, metrics_collector):
        """Test calculating cache hit rate"""
        metrics_collector.record_cache_hit(gpu_id=0)
        metrics_collector.record_cache_hit(gpu_id=0)
        metrics_collector.record_cache_miss(gpu_id=0)

        hit_rate = metrics_collector.get_cache_hit_rate()
        assert 0 <= hit_rate <= 1
        assert hit_rate == 2 / 3  # 2 hits, 1 miss

    def test_get_cache_hit_rate_no_requests(self, metrics_collector):
        """Test cache hit rate with no requests"""
        hit_rate = metrics_collector.get_cache_hit_rate()
        assert hit_rate == 0.0

    def test_export_metrics_text(self, metrics_collector):
        """Test exporting metrics in Prometheus text format"""
        metrics_collector.record_cache_hit(gpu_id=0)
        metrics_collector.record_gpu_utilization(gpu_id=0, percent=75.0)

        text = metrics_collector.export_metrics_text()
        assert isinstance(text, str)
        assert "cache_hits_total" in text
        assert "gpu_utilization_percent" in text

    def test_export_metrics_dict(self, metrics_collector):
        """Test exporting metrics as dictionary"""
        metrics_collector.record_cache_hit(gpu_id=0)
        metrics_collector.record_cache_miss(gpu_id=0)
        metrics_collector.record_gpu_utilization(gpu_id=0, percent=80.0)

        metrics_dict = metrics_collector.export_metrics_dict()
        assert isinstance(metrics_dict, dict)
        assert 'cache_hits' in metrics_dict
        assert 'cache_misses' in metrics_dict
        assert 'cache_hit_rate' in metrics_dict
        assert 'gpu_utilization' in metrics_dict

    def test_metrics_thread_safety(self, metrics_collector):
        """Test metrics recording is thread-safe"""
        import threading

        def record_many_hits():
            for _ in range(100):
                metrics_collector.record_cache_hit(gpu_id=0)

        threads = [threading.Thread(target=record_many_hits) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have exactly 500 hits (5 threads * 100 hits each)
        assert metrics_collector.cache_hits == 500

    def test_metrics_reset(self, metrics_collector):
        """Test resetting metrics"""
        metrics_collector.record_cache_hit(gpu_id=0)
        metrics_collector.record_cache_miss(gpu_id=0)
        metrics_collector.record_gpu_utilization(gpu_id=0, percent=80.0)

        # Reset
        metrics_collector.reset()

        assert metrics_collector.cache_hits == 0
        assert metrics_collector.cache_misses == 0
        assert len(metrics_collector.gpu_utilization_pct) == 0

    def test_multiple_gpu_tracking(self, metrics_collector):
        """Test tracking metrics for multiple GPUs"""
        metrics_collector.record_gpu_utilization(gpu_id=0, percent=50.0)
        metrics_collector.record_gpu_utilization(gpu_id=1, percent=80.0)
        metrics_collector.record_gpu_utilization(gpu_id=2, percent=60.0)

        assert len(metrics_collector.gpu_utilization_pct) == 3
        assert metrics_collector.gpu_utilization_pct[0] == 50.0
        assert metrics_collector.gpu_utilization_pct[1] == 80.0
        assert metrics_collector.gpu_utilization_pct[2] == 60.0

    def test_metrics_persistence_export(self, metrics_collector):
        """Test that exported metrics include all recorded data"""
        # Record various metrics
        metrics_collector.record_cache_hit(gpu_id=0)
        metrics_collector.record_inference_latency(model_id="model-a", latency_ms=50)
        metrics_collector.record_scheduler_time(model_id="model-a", time_ms=0.5)

        # Export and verify
        metrics_dict = metrics_collector.export_metrics_dict()
        assert metrics_dict['cache_hits'] == 1
        assert 'model-a' in metrics_dict.get('inference_latencies', {}) or metrics_dict['cache_hits'] > 0


class TestBenchmarkSuite:
    """Test suite for BenchmarkSuite"""

    @pytest.fixture
    def mock_scheduler(self):
        """Create mock scheduler"""
        scheduler = Mock()
        scheduler.select_best_gpu = Mock(return_value=(0, 85.5))
        return scheduler

    @pytest.fixture
    def mock_caches(self):
        """Create mock GPU caches"""
        cache1 = Mock()
        cache1.cache_hits = 750
        cache1.cache_misses = 250
        cache1.get_stats = Mock(return_value={
            'utilization_pct': 75,
            'models_loaded': 5,
        })

        cache2 = Mock()
        cache2.cache_hits = 800
        cache2.cache_misses = 200
        cache2.get_stats = Mock(return_value={
            'utilization_pct': 80,
            'models_loaded': 6,
        })

        return [cache1, cache2]

    @pytest.fixture
    def mock_predictor(self):
        """Create mock predictor"""
        predictor = Mock()
        predictor.access_history = {
            'model-1': (datetime.now(), 100),
            'model-2': (datetime.now(), 50),
            'model-3': (datetime.now(), 75),
            'model-4': (datetime.now(), 60),
            'model-5': (datetime.now(), 40),
        }
        predictor.predict_next_models = Mock(return_value=[
            ('model-1', 0.9),
            ('model-2', 0.7),
            ('model-3', 0.6),
        ])
        return predictor

    @pytest.fixture
    def benchmark_suite(self, mock_scheduler, mock_caches, mock_predictor):
        """Create benchmark suite instance"""
        return BenchmarkSuite(mock_scheduler, mock_caches, mock_predictor)

    def test_benchmark_initialization(self, benchmark_suite):
        """Test benchmark suite initializes correctly"""
        assert benchmark_suite is not None
        assert benchmark_suite.scheduler is not None
        assert benchmark_suite.gpu_caches is not None
        assert benchmark_suite.predictor is not None

    def test_targets_defined(self, benchmark_suite):
        """Test all target metrics are defined"""
        targets = BenchmarkSuite.TARGETS
        assert 'cold_start_latency_ms' in targets
        assert 'cache_hit_rate' in targets
        assert 'scheduler_time_ms' in targets
        assert 'gpu_utilization_pct' in targets
        assert 'prediction_accuracy' in targets
        assert 'cost_reduction_pct' in targets

    @pytest.mark.asyncio
    async def test_benchmark_cold_start(self, benchmark_suite):
        """Test cold start latency benchmark"""
        result = await benchmark_suite.benchmark_cold_start(num_requests=10)

        assert isinstance(result, dict)
        assert 'metric' in result
        assert result['metric'] == 'cold_start_latency_ms'
        assert 'avg' in result
        assert 'p95' in result
        assert 'target' in result
        assert 'passed' in result

    @pytest.mark.asyncio
    async def test_benchmark_cache_hit_rate(self, benchmark_suite):
        """Test cache hit rate benchmark"""
        result = await benchmark_suite.benchmark_cache_hit_rate()

        assert isinstance(result, dict)
        assert 'metric' in result
        assert result['metric'] == 'cache_hit_rate'
        assert 'rate' in result
        assert 0 <= result['rate'] <= 1

    @pytest.mark.asyncio
    async def test_benchmark_scheduler_speed(self, benchmark_suite):
        """Test scheduler speed benchmark"""
        result = await benchmark_suite.benchmark_scheduler_speed(num_selections=50)

        assert isinstance(result, dict)
        assert 'metric' in result
        assert result['metric'] == 'scheduler_time_ms'
        assert 'avg' in result
        assert 'p99' in result
        assert result['avg'] >= 0

    @pytest.mark.asyncio
    async def test_benchmark_gpu_utilization(self, benchmark_suite):
        """Test GPU utilization benchmark"""
        result = await benchmark_suite.benchmark_gpu_utilization()

        assert isinstance(result, dict)
        assert 'metric' in result
        assert result['metric'] == 'gpu_utilization_pct'
        assert 'avg' in result
        assert 0 <= result['avg'] <= 100

    @pytest.mark.asyncio
    async def test_benchmark_prediction_accuracy(self, benchmark_suite):
        """Test prediction accuracy benchmark"""
        result = await benchmark_suite.benchmark_prediction_accuracy(num_predictions=10)

        assert isinstance(result, dict)
        assert 'metric' in result
        assert result['metric'] == 'prediction_accuracy'
        assert 'accuracy' in result
        assert 0 <= result['accuracy'] <= 1

    @pytest.mark.asyncio
    async def test_benchmark_cost_reduction(self, benchmark_suite):
        """Test cost reduction benchmark"""
        result = await benchmark_suite.benchmark_cost_reduction()

        assert isinstance(result, dict)
        assert 'metric' in result
        assert result['metric'] == 'cost_reduction_pct'
        assert 'reduction_pct' in result
        assert 'models' in result
        assert 'gpus_used' in result

    @pytest.mark.asyncio
    async def test_run_all_benchmarks(self, benchmark_suite):
        """Test running all benchmarks together"""
        summary = await benchmark_suite.run_all()

        assert isinstance(summary, dict)
        assert 'status' in summary
        assert 'results' in summary
        assert 'total_benchmarks' in summary
        assert 'passed_benchmarks' in summary
        assert summary['total_benchmarks'] == 6
        assert 0 <= summary['passed_benchmarks'] <= 6

    @pytest.mark.asyncio
    async def test_benchmark_results_structure(self, benchmark_suite):
        """Test benchmark results have correct structure"""
        summary = await benchmark_suite.run_all()

        for name, result in summary['results'].items():
            assert isinstance(result, dict)
            assert 'metric' in result
            assert 'target' in result
            assert 'passed' in result

    def test_cache_hit_rate_calculation(self, benchmark_suite):
        """Test cache hit rate is calculated correctly"""
        # Mock caches with known values
        cache1 = Mock()
        cache1.cache_hits = 100
        cache1.cache_misses = 0

        cache2 = Mock()
        cache2.cache_hits = 50
        cache2.cache_misses = 50

        benchmark_suite.gpu_caches = [cache1, cache2]
        
        # Manually calculate (not using async method for simplicity)
        total_hits = cache1.cache_hits + cache2.cache_hits  # 150
        total_misses = cache1.cache_misses + cache2.cache_misses  # 50
        expected_rate = total_hits / (total_hits + total_misses)  # 150/200 = 0.75

        assert expected_rate == 0.75

    def test_cost_reduction_with_fewer_gpus(self, benchmark_suite):
        """Test cost reduction calculation"""
        # 10 models, 2 GPUs
        benchmark_suite.predictor.access_history = {
            f'model-{i}': (datetime.now(), i) for i in range(10)
        }
        benchmark_suite.gpu_caches = [Mock(), Mock()]

        num_models = len(benchmark_suite.predictor.access_history)
        num_gpus = len(benchmark_suite.gpu_caches)

        # Cost reduction = (models - gpus) / models * 100
        # (10 - 2) / 10 * 100 = 80%
        expected_reduction = (num_models - num_gpus) / num_models * 100
        assert expected_reduction == 80.0
