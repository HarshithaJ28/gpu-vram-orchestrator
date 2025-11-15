"""Tests for GPU Scheduler Module"""

import pytest
from unittest.mock import MagicMock, Mock
from src.scheduler import GPUScheduler, SchedulingScore


# Mock GPU Cache for testing
class MockGPUCache:
    """Mock GPU cache for scheduler testing"""
    def __init__(self, gpu_id: int, total_memory_mb: int = 10000, used_mb: int = 0):
        self.gpu_id = gpu_id
        self.total_memory_mb = total_memory_mb
        self.used_memory_mb = used_mb
        self.models = {}  # model_id -> mock model

    def get_stats(self):
        """Return mock stats"""
        return {
            'gpu_id': self.gpu_id,
            'memory_free_mb': self.total_memory_mb - self.used_memory_mb,
            'memory_total_mb': self.total_memory_mb,
            'memory_used_mb': self.used_memory_mb,
            'models_loaded': len(self.models),
            'utilization_pct': (self.used_memory_mb / self.total_memory_mb) * 100
        }


class TestScheduler:
    """Test suite for GPU scheduler"""

    @pytest.fixture
    def scheduler_3_gpus(self):
        """Create scheduler with 3 mock GPUs"""
        caches = [
            MockGPUCache(gpu_id=0, total_memory_mb=10000, used_mb=2000),
            MockGPUCache(gpu_id=1, total_memory_mb=10000, used_mb=5000),
            MockGPUCache(gpu_id=2, total_memory_mb=10000, used_mb=8000),
        ]
        return GPUScheduler(caches)

    def test_scheduler_initializes(self):
        """Scheduler initializes correctly"""
        caches = [MockGPUCache(i, 10000) for i in range(3)]
        scheduler = GPUScheduler(caches)

        assert scheduler is not None
        assert len(scheduler.gpu_caches) == 3

    def test_scheduler_weights_sum_to_one(self):
        """Scheduler weights sum to 1.0"""
        caches = [MockGPUCache(0, 10000)]
        scheduler = GPUScheduler(caches)

        total_weight = sum(scheduler.WEIGHTS.values())
        assert abs(total_weight - 1.0) < 0.01

    def test_memory_scoring_high_free_space(self):
        """Memory scoring with high free space"""
        scheduler = GPUScheduler([MockGPUCache(0, 10000, used_mb=1000)])

        # 90% free = high score
        score = scheduler._score_memory({
            'memory_free_mb': 9000,
            'memory_total_mb': 10000
        })
        assert score > 0.9

    def test_memory_scoring_medium_free_space(self):
        """Memory scoring with medium free space (20%)"""
        scheduler = GPUScheduler([])

        # 20% free = medium score (between 0.0 and 0.5)
        score = scheduler._score_memory({
            'memory_free_mb': 2000,
            'memory_total_mb': 10000
        })
        assert 0.0 < score < 0.5

    def test_memory_scoring_low_free_space(self):
        """Memory scoring with low free space"""
        scheduler = GPUScheduler([])

        # 5% free = very low score
        score = scheduler._score_memory({
            'memory_free_mb': 500,
            'memory_total_mb': 10000
        })
        assert score == 0.0

    def test_load_scoring_no_pending(self):
        """Load scoring with no pending requests"""
        scheduler = GPUScheduler([MockGPUCache(0, 10000)])

        # No pending = high score
        score = scheduler._score_load(0)
        assert score > 0.99

    def test_load_scoring_with_pending(self):
        """Load scoring with pending requests"""
        scheduler = GPUScheduler([MockGPUCache(0, 10000)])

        # 1 pending request
        scheduler.pending_requests[0] = 1
        score = scheduler._score_load(0)
        assert score == 0.5

        # 10 pending requests
        scheduler.pending_requests[0] = 10
        score = scheduler._score_load(0)
        assert score < 0.1

    def test_affinity_scoring_no_similar_models(self):
        """Affinity scoring with no similar models"""
        scheduler = GPUScheduler([MockGPUCache(0, 10000)])

        # No models on GPU = 0 affinity
        score = scheduler._score_affinity("fraud-v1", 0)
        assert score == 0.0

    def test_affinity_scoring_with_similar_models(self, scheduler_3_gpus):
        """Affinity scoring with similar models present"""
        # Add a mock model to GPU 0
        mock_model = Mock()
        mock_model.model_id = "fraud-v1"
        scheduler_3_gpus.gpu_caches[0].models["fraud-v1"] = mock_model

        # scoring fraud-v2 should have affinity to fraud-v1
        score = scheduler_3_gpus._score_affinity("fraud-v2", 0)
        assert score > 0.0

    def test_extract_category_removes_version(self):
        """Category extraction removes version suffix"""
        scheduler = GPUScheduler([])

        assert scheduler._extract_category("fraud-detection-v1") == "fraud-detection"
        assert scheduler._extract_category("recommendation-v3") == "recommendation"
        assert scheduler._extract_category("image-classifier") == "image-classifier"
        assert scheduler._extract_category("model-a-b-v2") == "model-a-b"

    def test_score_gpu_returns_scheduling_score(self, scheduler_3_gpus):
        """score_gpu returns valid SchedulingScore"""
        score = scheduler_3_gpus.score_gpu("model-test", 0)

        assert isinstance(score, SchedulingScore)
        assert score.gpu_id == 0
        assert 0.0 <= score.memory_score <= 1.0
        assert 0.0 <= score.load_score <= 1.0
        assert 0.0 <= score.affinity_score <= 1.0
        assert 0.0 <= score.total_score <= 1.0

    def test_select_best_gpu_picks_least_used(self, scheduler_3_gpus):
        """select_best_gpu prefers GPU with most free memory"""
        # GPU 0 has 8000 free, GPU 1 has 5000 free, GPU 2 has 2000 free
        gpu_id, score = scheduler_3_gpus.select_best_gpu("model-test")

        # Should pick GPU 0 (most free memory)
        assert gpu_id == 0

    def test_select_best_gpu_considers_load(self):
        """select_best_gpu considers pending requests"""
        caches = [
            MockGPUCache(gpu_id=0, total_memory_mb=10000, used_mb=5000),
            MockGPUCache(gpu_id=1, total_memory_mb=10000, used_mb=5000),
        ]
        scheduler = GPUScheduler(caches)

        # GPU 0 is overwhelmed with pending requests
        scheduler.pending_requests[0] = 10

        gpu_id, score = scheduler.select_best_gpu("model-test")

        # Should prefer GPU 1 (less loaded)
        assert gpu_id == 1

    def test_select_best_gpu_with_no_gpus_raises(self):
        """select_best_gpu raises ValueError with no GPUs"""
        scheduler = GPUScheduler([])

        with pytest.raises(ValueError):
            scheduler.select_best_gpu("model-test")

    def test_record_and_clear_requests(self):
        """record_request and clear_request work"""
        scheduler = GPUScheduler([MockGPUCache(0, 10000)])

        assert scheduler.pending_requests.get(0, 0) == 0

        scheduler.record_request(0)
        assert scheduler.pending_requests[0] == 1

        scheduler.record_request(0)
        assert scheduler.pending_requests[0] == 2

        scheduler.clear_request(0)
        assert scheduler.pending_requests[0] == 1

    def test_record_access_history(self):
        """record_access tracks model access"""
        scheduler = GPUScheduler([MockGPUCache(0, 10000)])

        scheduler.record_access("fraud-v1", 0)
        scheduler.record_access("fraud-v1", 1)
        scheduler.record_access("fraud-v2", 0)

        assert len(scheduler.model_access_history["fraud-v1"]) == 2
        assert scheduler.model_access_history["fraud-v1"] == [0, 1]

    def test_get_stats(self, scheduler_3_gpus):
        """get_stats returns scheduler statistics"""
        scheduler_3_gpus.pending_requests[0] = 3

        stats = scheduler_3_gpus.get_stats()

        assert stats['num_gpus'] == 3
        assert stats['pending_requests'][0] == 3
        assert 'weights' in stats

    def test_scheduling_score_dataclass(self):
        """SchedulingScore dataclass works"""
        score = SchedulingScore(
            gpu_id=0,
            memory_score=0.8,
            load_score=0.6,
            affinity_score=0.4,
            total_score=0.68,
            reasoning="Test"
        )

        assert score.gpu_id == 0
        assert score.memory_score == 0.8


class TestSchedulerCritical:
    """Critical path tests - these MUST pass"""

    def test_scoring_never_crashes(self):
        """
        CRITICAL: Scheduler scoring must never crash
        Crashing here breaks request routing
        """
        caches = [MockGPUCache(i, 10000) for i in range(3)]
        scheduler = GPUScheduler(caches)

        try:
            for i in range(len(caches)):
                score = scheduler.score_gpu("test-model", i)
                assert isinstance(score, SchedulingScore)
        except Exception as e:
            pytest.fail(f"Scheduler scoring crashed: {e}")

    def test_selection_always_returns_valid_gpu(self):
        """
        CRITICAL: select_best_gpu must return a valid GPU ID
        Invalid GPU ID causes catastrophic failures
        """
        caches = [MockGPUCache(i, 10000) for i in range(3)]
        scheduler = GPUScheduler(caches)

        gpu_id, score = scheduler.select_best_gpu("test-model")

        assert isinstance(gpu_id, int)
        assert 0 <= gpu_id < len(caches)

    def test_weights_never_exceed_one(self):
        """
        CRITICAL: Total weighted score must not exceed 1.0
        This would indicate incorrect weighting
        """
        caches = [MockGPUCache(0, 10000)]
        scheduler = GPUScheduler(caches)

        score = scheduler.score_gpu("test", 0)

        # Total score should never exceed 1.0
        assert score.total_score <= 1.0 + 0.01  # Allow small fp error
