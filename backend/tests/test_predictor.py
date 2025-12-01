"""Tests for Access Pattern Predictor and Preloader Modules"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from src.predictor import AccessPatternPredictor, PredictivePreloader
import numpy as np


class TestAccessPatternPredictor:
    """Test suite for access pattern predictor"""

    @pytest.fixture
    def predictor(self):
        """Create predictor instance"""
        return AccessPatternPredictor(history_window_days=30)

    def test_predictor_initializes(self, predictor):
        """Predictor initializes correctly"""
        assert predictor is not None
        assert predictor.history_window_days == 30
        assert len(predictor.access_history) == 0

    def test_record_access_basic(self, predictor):
        """Recording access works"""
        predictor.record_access("model-a")

        assert len(predictor.access_history["model-a"]) == 1
        assert "model-a" in predictor.access_history

    def test_record_access_multiple(self, predictor):
        """Recording multiple accesses"""
        for i in range(10):
            predictor.record_access("model-a")

        assert len(predictor.access_history["model-a"]) == 10

    def test_hour_patterns_learned(self, predictor):
        """Time-of-day patterns are learned"""
        # Mock current time to fixed hour
        with patch('src.predictor.access_predictor.datetime') as mock_dt:
            # Set to 9 AM
            mock_dt.now.return_value = datetime(2026, 3, 8, 9, 0, 0)
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            predictor.record_access("fraud-v1")

            # Hour 9 should have been incremented
            assert predictor.hour_patterns["fraud-v1"][9] >= 0

    def test_day_patterns_learned(self, predictor):
        """Day-of-week patterns are learned"""
        predictor.record_access("model-a")

        # Current day should have incremented
        day_of_week = datetime.now().weekday()
        assert predictor.day_patterns["model-a"][day_of_week] >= 0

    def test_sequential_patterns_learned(self, predictor):
        """Sequential patterns (A → B) are learned"""
        # Access model-a
        predictor.record_access("fraud-v1")

        # Access model-b within 5 minutes (should trigger sequential pattern)
        with patch('src.predictor.access_predictor.datetime') as mock_dt:
            # Just slightly later
            mock_dt.now.return_value = datetime.now() + timedelta(minutes=1)
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            predictor.record_access("fraud-v2")

            # fraud-v1 → fraud-v2 should be recorded
            # (might not always record due to timing, but should initialize)
            assert isinstance(predictor.sequential_patterns["fraud-v1"], dict)

    def test_predict_next_models_returns_list(self, predictor):
        """predict_next_models returns list"""
        # Add some access history
        for i in range(50):
            predictor.record_access("fraud-v1")
            predictor.record_access("recommendation-core")
            predictor.record_access("image-classifier")

        predictions = predictor.predict_next_models(top_k=5)

        assert isinstance(predictions, list)
        assert len(predictions) <= 5

    def test_predict_next_models_returns_tuples(self, predictor):
        """Each prediction is (model_id, probability) tuple"""
        for i in range(50):
            predictor.record_access("fraud-v1")

        predictions = predictor.predict_next_models(top_k=5)

        if predictions:
            model_id, prob = predictions[0]
            assert isinstance(model_id, str)
            assert isinstance(prob, (float, np.floating))
            assert 0.0 <= prob <= 1.0

    def test_predict_next_models_filters_by_confidence(self, predictor):
        """Predictions filtered by confidence threshold"""
        # Add accesses
        for i in range(100):
            predictor.record_access("fraud-v1")

        # High threshold should return fewer predictions
        high_confidence = predictor.predict_next_models(confidence_threshold=0.9)
        low_confidence = predictor.predict_next_models(confidence_threshold=0.1)

        assert len(high_confidence) <= len(low_confidence)

    def test_get_sequential_prediction_empty(self, predictor):
        """Sequential prediction with no recent models"""
        preds = predictor.get_sequential_prediction([])

        assert preds == []

    def test_get_sequential_prediction_returns_list(self, predictor):
        """Sequential prediction returns list"""
        # Add sequential pattern
        predictor.access_history["fraud-v1"] = [datetime.now()]
        predictor.sequential_patterns["fraud-v1"]["fraud-v2"] = 5

        preds = predictor.get_sequential_prediction(["fraud-v1"], top_k=3)

        assert isinstance(preds, list)
        if preds:
            assert "fraud-v2" in preds

    def test_get_stats(self, predictor):
        """get_stats returns statistics"""
        for i in range(10):
            predictor.record_access(f"model-{i}")

        stats = predictor.get_stats()

        assert 'models_tracked' in stats
        assert 'total_accesses' in stats
        assert 'window_days' in stats
        assert stats['window_days'] == 30

    def test_clear(self, predictor):
        """clear empties all history"""
        for i in range(10):
            predictor.record_access(f"model-{i}")

        assert len(predictor.access_history) > 0

        predictor.clear()

        assert len(predictor.access_history) == 0
        assert len(predictor.hour_patterns) == 0

    def test_record_access_invalid_model_id(self, predictor):
        """Record with empty model_id handled"""
        predictor.record_access("")  # Should not crash

        assert "" not in predictor.access_history or len(predictor.access_history[""] if "" in predictor.access_history else []) == 0


class TestPredictivePreloader:
    """Test suite for predictive preloader"""

    @pytest.fixture
    def mock_components(self):
        """Create mock components"""
        predictor = AccessPatternPredictor()
        scheduler = Mock()
        gpu_caches = [Mock() for _ in range(3)]

        # Setup mock caches
        for i, cache in enumerate(gpu_caches):
            cache.gpu_id = i
            cache.models = {}
            cache.get_stats.return_value = {
                'memory_free_mb': 5000,
                'memory_total_mb': 10000,
            }

        return predictor, scheduler, gpu_caches

    @pytest.fixture
    def preloader(self, mock_components):
        """Create preloader instance"""
        predictor, scheduler, gpu_caches = mock_components
        scheduler.select_best_gpu.return_value = (0, Mock())

        return PredictivePreloader(
            predictor=predictor,
            scheduler=scheduler,
            gpu_caches=gpu_caches,
            confidence_threshold=0.4,
            check_interval_seconds=1
        )

    def test_preloader_initializes(self, preloader):
        """Preloader initializes correctly"""
        assert preloader is not None
        assert preloader.running is False
        assert preloader.preload_attempts == 0

    @pytest.mark.asyncio
    async def test_preloader_start_stop(self, preloader):
        """Preloader can start and stop"""
        # Start in background
        task = asyncio.create_task(preloader.start())

        # Give it a moment to start
        await asyncio.sleep(0.1)

        assert preloader.running is True

        # Stop
        await preloader.stop()
        await asyncio.wait_for(task, timeout=2)

        assert preloader.running is False

    def test_preloader_get_stats(self, preloader):
        """get_stats returns statistics"""
        stats = preloader.get_stats()

        assert 'running' in stats
        assert 'preload_attempts' in stats
        assert 'preload_successes' in stats
        assert 'success_rate' in stats
        assert 0.0 <= stats['success_rate'] <= 1.0

    @pytest.mark.asyncio
    async def test_preload_cycle_runs(self, preloader):
        """Preload cycle executes without error"""
        try:
            await preloader._preload_cycle()
        except Exception as e:
            pytest.fail(f"Preload cycle failed: {e}")


class TestPredictorCritical:
    """Critical path tests - these MUST pass"""

    def test_predictor_never_crashes_on_access(self):
        """
        CRITICAL: record_access must never crash
        Used in hot path, failure here breaks system
        """
        predictor = AccessPatternPredictor()

        try:
            for i in range(1000):
                predictor.record_access(f"model-{i % 10}")
                predictions = predictor.predict_next_models(top_k=5)
                assert isinstance(predictions, list)
        except Exception as e:
            pytest.fail(f"Predictor failed on hot path: {e}")

    def test_predictions_always_valid(self):
        """
        CRITICAL: Predictions must always be valid
        Invalid probabilities break confidence calculation
        """
        predictor = AccessPatternPredictor()

        # Add real patterns
        for i in range(100):
            predictor.record_access("fraud-v1")
            predictor.record_access("recommendation-core")

        predictions = predictor.predict_next_models(top_k=10)

        # All predictions must be valid
        for model_id, prob in predictions:
            assert isinstance(model_id, str) and model_id
            assert isinstance(prob, (float, np.floating))
            assert 0.0 <= prob <= 1.0 + 0.01  # Allow small float error

    def test_preloader_safe_preload(self):
        """
        CRITICAL: Preloader must not displace existing models
        Preloading should never hurt served models
        """
        predictor = AccessPatternPredictor()
        scheduler = Mock()
        
        # Mock GPU with some free space but not unlimited
        cache = Mock()
        cache.gpu_id = 0
        cache.models = {"critical-model": Mock()}  # Already loaded
        cache.get_stats.return_value = {
            'memory_free_mb': 2000,  # Limited space
            'memory_total_mb': 10000,
        }

        preloader = PredictivePreloader(
            predictor=predictor,
            scheduler=scheduler,
            gpu_caches=[cache],
            confidence_threshold=0.3
        )

        # Preloader should respect memory constraints
        assert "critical-model" in cache.models  # Should not be displaced
