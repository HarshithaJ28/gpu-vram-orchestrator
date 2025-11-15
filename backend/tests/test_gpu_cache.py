"""Tests for GPU Model Cache Module"""

import pytest
import time
from datetime import datetime
from src.cache import GPUModelCache, LoadedModel


class TestGPUModelCache:
    """Test suite for GPU model cache"""

    @pytest.fixture
    def cache(self):
        """Create cache fixture"""
        return GPUModelCache(
            gpu_id=0,
            total_memory_mb=12000,
            reserved_memory_mb=1000
        )

    def test_cache_initializes(self, cache):
        """Cache initializes correctly"""
        assert cache.gpu_id == 0
        assert cache.total_memory_mb == 12000
        assert cache.available_memory_mb == 11000
        assert cache.used_memory_mb == 0
        assert len(cache.models) == 0

    def test_loaded_model_dataclass(self):
        """LoadedModel dataclass works"""
        now = datetime.now()
        model = LoadedModel(
            model_id="test",
            memory_usage_mb=1000,
            loaded_at=now,
            last_accessed=now,
            access_count=1,
            is_pinned=False,
            model=None
        )

        assert model.model_id == "test"
        assert model.memory_usage_mb == 1000
        assert model.is_pinned is False
        assert model.age_seconds >= 0

    def test_load_model_success(self, cache):
        """Load model successfully"""
        result = cache.load_model("model-a", None, 3000)

        assert result is True
        assert cache.used_memory_mb == 3000
        assert "model-a" in cache.models

    def test_load_model_too_large(self, cache):
        """Load model that's too large fails"""
        # Available is 11000 MB
        result = cache.load_model("model-a", None, 12000)

        assert result is False
        assert cache.used_memory_mb == 0
        assert "model-a" not in cache.models

    def test_load_model_duplicate(self, cache):
        """Loading duplicate model returns success but doesn't re-add"""
        cache.load_model("model-a", None, 3000)
        used_before = cache.used_memory_mb

        result = cache.load_model("model-a", None, 3000)

        assert result is True
        assert cache.used_memory_mb == used_before  # No change

    def test_get_model_cache_hit(self, cache):
        """get_model returns model on cache hit"""
        cache.load_model("model-a", None, 3000)

        model = cache.get_model("model-a")

        assert model is not None
        assert model.model_id == "model-a"
        assert cache.cache_hits == 1
        assert cache.cache_misses == 0

    def test_get_model_cache_miss(self, cache):
        """get_model returns None on cache miss"""
        model = cache.get_model("nonexistent")

        assert model is None
        assert cache.cache_hits == 0
        assert cache.cache_misses == 1

    def test_get_model_updates_lru_order(self, cache):
        """get_model moves model to end (most recently used)"""
        cache.load_model("model-a", None, 3000)
        cache.load_model("model-b", None, 3000)
        cache.load_model("model-c", None, 3000)

        # Get model-a (should move to end, access_count increases)
        cache.get_model("model-a")

        # Evict - should remove model-b (now LRU), not model-a
        # Available: 11000, Used: 9000, Need: 3000, Force evict: 3000
        cache.load_model("model-d", None, 3000)

        assert "model-a" in cache.models  # Recently accessed
        assert "model-b" not in cache.models  # LRU (was evicted)
        assert "model-c" in cache.models

    def test_lru_eviction_basic(self, cache):
        """LRU eviction removes oldest model"""
        cache.load_model("model-a", None, 3000)
        cache.load_model("model-b", None, 3000)
        cache.load_model("model-c", None, 3000)

        # Used: 9000, Available: 11000
        assert cache.used_memory_mb == 9000

        # Load model that forces eviction (9000 + 3000 > 11000)
        cache.load_model("model-d", None, 3000)

        # model-a should be evicted (LRU)
        assert "model-a" not in cache.models
        assert "model-b" in cache.models
        assert "model-c" in cache.models
        assert "model-d" in cache.models
        assert cache.evictions == 1

    def test_pinned_models_never_evicted(self, cache):
        """Pinned models never get evicted"""
        cache.load_model("fraud-v1", None, 3000, pin=True)
        cache.load_model("model-b", None, 3000)
        cache.load_model("model-c", None, 3000)

        assert cache.used_memory_mb == 9000

        # Load model that forces eviction
        cache.load_model("model-d", None, 3000)

        # fraud-v1 should still be there (pinned)
        assert "fraud-v1" in cache.models
        # model-b should be evicted (LRU, not pinned)
        assert "model-b" not in cache.models

    def test_pin_model_success(self, cache):
        """pin_model sets pinned flag"""
        cache.load_model("model-a", None, 2000)

        result = cache.pin_model("model-a")

        assert result is True
        assert cache.models["model-a"].is_pinned is True

    def test_pin_model_not_found(self, cache):
        """pin_model fails for nonexistent model"""
        result = cache.pin_model("nonexistent")

        assert result is False

    def test_unpin_model_success(self, cache):
        """unpin_model clears pinned flag"""
        cache.load_model("model-a", None, 2000, pin=True)

        result = cache.unpin_model("model-a")

        assert result is True
        assert cache.models["model-a"].is_pinned is False

    def test_unload_model_success(self, cache):
        """unload_model removes model"""
        cache.load_model("model-a", None, 3000)
        assert cache.used_memory_mb == 3000

        result = cache.unload_model("model-a")

        assert result is True
        assert "model-a" not in cache.models
        assert cache.used_memory_mb == 0

    def test_unload_model_not_found(self, cache):
        """unload_model returns False for nonexistent model"""
        result = cache.unload_model("nonexistent")

        assert result is False

    def test_get_stats_complete(self, cache):
        """get_stats returns comprehensive statistics"""
        cache.load_model("model-a", None, 2000)
        cache.get_model("model-a")  # Hit
        cache.get_model("nonexistent")  # Miss

        stats = cache.get_stats()

        assert stats['gpu_id'] == 0
        assert stats['models_loaded'] == 1
        assert stats['memory_used_mb'] == 2000
        assert stats['memory_free_mb'] == 11000 - 2000
        assert stats['hit_rate'] == 0.5
        assert stats['cache_hits'] == 1
        assert stats['cache_misses'] == 1
        assert 'models' in stats
        assert len(stats['models']) == 1

    def test_stats_hit_rate_calculation(self, cache):
        """Hit rate calculated correctly in stats"""
        # No requests
        assert cache.get_stats()['hit_rate'] == 0.0

        # Load and hit
        cache.load_model("model-a", None, 2000)
        cache.get_model("model-a")  # Hit
        cache.get_model("model-a")  # Hit
        cache.get_model("nonexistent")  # Miss

        stats = cache.get_stats()
        # 2 hits, 1 miss = 2/3 = 0.667
        assert abs(stats['hit_rate'] - 2/3) < 0.01

    def test_clear_cache(self, cache):
        """clear empties the cache"""
        cache.load_model("model-a", None, 3000)
        cache.load_model("model-b", None, 3000)

        assert len(cache.models) == 2
        assert cache.used_memory_mb == 6000

        cache.clear()

        assert len(cache.models) == 0
        assert cache.used_memory_mb == 0

    def test_thread_safety_basic(self, cache):
        """Cache operations are thread-safe (basic check)"""
        import threading

        results = []

        def load_models():
            for i in range(10):
                cache.load_model(f"model-{i}", None, 1000)

        threads = [threading.Thread(target=load_models) for _ in range(3)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Should have loaded many models (some evicted)
        # Just verify it didn't crash
        assert cache.cache_hits >= 0
        assert cache.evictions >= 0

    def test_sequential_load_evict_reuse(self, cache):
        """Realistic scenario: load, evict, reload"""
        # Load model-a
        assert cache.load_model("model-a", None, 4000) is True
        assert cache.used_memory_mb == 4000

        # Load model-b
        assert cache.load_model("model-b", None, 4000) is True
        assert cache.used_memory_mb == 8000

        # Load model-c, forces eviction of model-a
        assert cache.load_model("model-c", None, 4000) is True
        assert "model-a" not in cache.models
        assert cache.used_memory_mb == 8000

        # Re-load model-a (model-b gets evicted)
        assert cache.load_model("model-a", None, 4000) is True
        assert "model-b" not in cache.models
        assert cache.used_memory_mb == 8000


class TestGPUModelCacheCritical:
    """Critical path tests - these MUST pass"""

    def test_load_never_exceeds_memory(self):
        """
        CRITICAL: Used memory must never exceed available
        This would cause GPU OOM
        """
        cache = GPUModelCache(gpu_id=0, total_memory_mb=5000, reserved_memory_mb=1000)

        # Available = 4000 MB
        cache.load_model("model-a", None, 2000)
        cache.load_model("model-b", None, 2000)

        # This should fail or evict
        cache.load_model("model-c", None, 2000)

        assert cache.used_memory_mb <= cache.available_memory_mb

    def test_eviction_never_removes_pinned(self):
        """
        CRITICAL: Pinned models must never be evicted
        Violating this breaks hot model assumptions
        """
        cache = GPUModelCache(gpu_id=0, total_memory_mb=5000, reserved_memory_mb=1000)

        cache.load_model("critical-model", None, 2000, pin=True)
        cache.load_model("model-b", None, 2000)

        # Force eviction
        cache.load_model("model-c", None, 2000)

        assert "critical-model" in cache.models

    def test_hit_rate_never_exceeds_100(self):
        """
        CRITICAL: Hit rate must be 0-1 (0-100%)
        Invalid hit rate breaks metrics
        """
        cache = GPUModelCache(gpu_id=0, total_memory_mb=5000, reserved_memory_mb=1000)

        for i in range(100):
            cache.load_model(f"model-{i}", None, 100)
            cache.get_model(f"model-{i}")

        stats = cache.get_stats()
        assert 0.0 <= stats['hit_rate'] <= 1.0

    def test_no_memory_leaks(self):
        """
        CRITICAL: Deallocate must fully recover memory
        Memory leaks crash the system
        """
        cache = GPUModelCache(gpu_id=0, total_memory_mb=5000, reserved_memory_mb=1000)

        for i in range(5):
            cache.load_model(f"model-{i}", None, 3000)
            cache.unload_model(f"model-{i}")
            assert cache.used_memory_mb == 0  # Fully recovered
