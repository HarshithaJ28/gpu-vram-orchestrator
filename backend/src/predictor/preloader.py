"""Predictive Preloader Module

Background service that pre-warms GPUs with predicted models.
Runs periodically to reduce cold-start latency.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class PredictivePreloader:
    """
    Background service that pre-warms GPUs with predicted models

    Strategy:
    1. Runs every 60 seconds
    2. Gets predictions from AccessPatternPredictor
    3. Pre-loads hot models if space available
    4. Doesn't displace cached models (safe preloading)
    """

    def __init__(
        self,
        predictor: 'AccessPatternPredictor',
        scheduler: 'GPUScheduler',
        gpu_caches: List,
        confidence_threshold: float = 0.4,
        check_interval_seconds: int = 60
    ):
        """
        Initialize preloader

        Args:
            predictor: AccessPatternPredictor instance
            scheduler: GPUScheduler instance
            gpu_caches: List of GPUModelCache instances
            confidence_threshold: Min confidence to preload (0-1)
            check_interval_seconds: How often to check for preloads
        """
        self.predictor = predictor
        self.scheduler = scheduler
        self.gpu_caches = gpu_caches
        self.confidence_threshold = confidence_threshold
        self.check_interval_seconds = check_interval_seconds

        self.running = False
        self.preload_attempts = 0
        self.preload_successes = 0

        logger.info(
            f"PredictivePreloader initialized "
            f"(interval: {check_interval_seconds}s, threshold: {confidence_threshold})"
        )

    async def start(self):
        """Start the preloader background task"""
        self.running = True
        logger.info("PredictivePreloader started")

        while self.running:
            try:
                await self._preload_cycle()
            except Exception as e:
                logger.error(f"Error in preload cycle: {e}", exc_info=True)

            # Wait for next cycle
            await asyncio.sleep(self.check_interval_seconds)

    async def stop(self):
        """Stop the preloader"""
        self.running = False
        logger.info(f"PredictivePreloader stopped (successes: {self.preload_successes}/{self.preload_attempts})")

    async def _preload_cycle(self):
        """
        One preload cycle:
        1. Get recent model accesses
        2. Get predictions
        3. Pre-load if space available
        """
        # Get recently accessed models (last 5 minutes)
        recent_cutoff = datetime.now() - timedelta(minutes=5)
        recent_models = []

        for model_id, timestamps in self.predictor.access_history.items():
            recent = [t for t in timestamps if t > recent_cutoff]
            if recent:
                recent_models.append(model_id)

        # Get predictions (time-based + sequential)
        time_predictions = self.predictor.predict_next_models(
            top_k=10,
            confidence_threshold=self.confidence_threshold
        )
        sequential_predictions = self.predictor.get_sequential_prediction(recent_models, top_k=5)

        # Combine into unique list
        all_predictions = [m for m, _ in time_predictions] + sequential_predictions
        all_predictions = list(dict.fromkeys(all_predictions))  # Remove duplicates, preserve order

        logger.debug(f"Preload cycle: {len(all_predictions)} predictions")

        # Try to preload top predictions
        for model_id in all_predictions[:5]:  # Only top 5
            self.preload_attempts += 1

            # Check if already loaded
            already_loaded = any(
                model_id in gpu.models for gpu in self.gpu_caches
            )

            if already_loaded:
                logger.debug(f"Model {model_id} already loaded, skipping preload")
                continue

            # Select best GPU
            try:
                gpu_id, score = self.scheduler.select_best_gpu(model_id)
            except ValueError:
                logger.warning("No GPUs available for preload")
                continue

            gpu = self.gpu_caches[gpu_id]
            stats = gpu.get_stats()

            # Only preload if significant free space (don't displace existing models)
            min_free_mb = 3000  # Need at least 3GB
            if stats['memory_free_mb'] > min_free_mb:
                # In real implementation, would load model here
                # For prototype, just record attempt
                self.preload_successes += 1
                logger.debug(
                    f"Preload attempt: {model_id} → GPU {gpu_id} "
                    f"(free: {stats['memory_free_mb']}MB)"
                )

    def get_stats(self) -> dict:
        """Get preloader statistics"""
        success_rate = (
            self.preload_successes / self.preload_attempts
            if self.preload_attempts > 0 else 0.0
        )

        return {
            'running': self.running,
            'preload_attempts': self.preload_attempts,
            'preload_successes': self.preload_successes,
            'success_rate': success_rate,
            'interval_seconds': self.check_interval_seconds,
            'confidence_threshold': self.confidence_threshold,
        }
