"""Background Model Preloader

Continuously predicts which models will be needed soon and pre-loads them
to reduce cold start latency.
"""

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .model_access_predictor import ModelAccessPredictor
    from ..scheduler.gpu_scheduler import GPUScheduler
    from ..registry import ModelRegistry

logger = logging.getLogger(__name__)


class ModelPreloader:
    """
    Background task for predictive model loading.
    
    Continuously runs a cycle that:
    1. Predicts which models will be needed soon (using ML patterns)
    2. Pre-loads them to GPU caches
    3. Measures success rate and adjusts confidence threshold
    
    Configuration:
    - interval_seconds: How often to run prediction cycle (default: 60s)
    - confidence_threshold: Minimum confidence to preload (default: 0.5)
    - max_preloads_per_cycle: Max models to preload per cycle (default: 3)
    
    Statistics:
    - Tracks preload attempts, successes, failures, skips
    - Calculates success rate and efficiency
    """
    
    def __init__(
        self,
        predictor: "ModelAccessPredictor",
        scheduler: "GPUScheduler",
        registry: "ModelRegistry",
        interval_seconds: int = 60,
        confidence_threshold: float = 0.5,
        max_preloads_per_cycle: int = 3
    ):
        """
        Initialize preloader.
        
        Args:
            predictor: ModelAccessPredictor instance
            scheduler: GPUScheduler instance
            registry: ModelRegistry instance
            interval_seconds: Cycle interval in seconds
            confidence_threshold: Min confidence to preload (0.0-1.0)
            max_preloads_per_cycle: Max preloads per cycle
        """
        self.predictor = predictor
        self.scheduler = scheduler
        self.registry = registry
        self.interval_seconds = interval_seconds
        self.confidence_threshold = confidence_threshold
        self.max_preloads_per_cycle = max_preloads_per_cycle
        
        self.running = False
        self.task: Optional[asyncio.Task] = None
        
        # Statistics
        self.preload_attempts = 0
        self.preload_successes = 0
        self.preload_failures = 0
        self.preload_skips = 0  # Already loaded
        self.total_cycles = 0
        
        logger.info(
            f"Initialized ModelPreloader: "
            f"interval={interval_seconds}s, "
            f"confidence={confidence_threshold}, "
            f"max_preloads={max_preloads_per_cycle}"
        )
    
    async def start(self):
        """Start background preloading task"""
        if self.running:
            logger.warning("Preloader already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._run_loop())
        logger.info("Preloader started")
    
    async def stop(self):
        """Stop background preloading task"""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("Preloader stopped")
    
    async def _run_loop(self):
        """Main preloading loop"""
        logger.info("Preloader loop started")
        
        while self.running:
            try:
                await self._preload_cycle()
            except asyncio.CancelledError:
                logger.info("Preloader loop cancelled")
                break
            except Exception as e:
                logger.error(f"Preload cycle failed: {e}", exc_info=True)
            
            # Wait until next cycle
            await asyncio.sleep(self.interval_seconds)
    
    async def _preload_cycle(self):
        """
        Single preload cycle.
        
        1. Get predictions from ML predictor
        2. Filter already-loaded models
        3. Load top candidates to GPU
        """
        self.total_cycles += 1
        
        # Get predictions
        predictions = self.predictor.predict_next_models(
            top_k=self.max_preloads_per_cycle * 2,  # Get extras in case some are loaded
            min_probability=self.confidence_threshold
        )
        
        if not predictions:
            logger.debug("No predictions above threshold")
            return
        
        logger.info(
            f"[Cycle #{self.total_cycles}] "
            f"{len(predictions)} candidates, "
            f"top={predictions[0][0]} @ {predictions[0][1]:.1%}"
        )
        
        # Try to preload
        preloaded = 0
        for model_id, probability in predictions:
            if preloaded >= self.max_preloads_per_cycle:
                break
            
            # Check if already loaded
            already_loaded = any(
                gpu_cache.get_model(model_id) is not None
                for gpu_cache in self.scheduler.gpu_caches
            )
            
            if already_loaded:
                logger.debug(f"  Skip {model_id} (already loaded)")
                self.preload_skips += 1
                continue
            
            # Preload it
            success = await self._preload_model(model_id, probability)
            
            if success:
                preloaded += 1
                self.preload_successes += 1
                logger.info(
                    f"  Pre-loaded {model_id} "
                    f"(confidence={probability:.1%})"
                )
            else:
                self.preload_failures += 1
                logger.warning(f"  Failed to preload {model_id}")
    
    async def _preload_model(self, model_id: str, probability: float) -> bool:
        """
        Pre-load a single model to GPU.
        
        Args:
            model_id: Model to preload
            probability: Prediction confidence
        
        Returns:
            True if successful, False otherwise
        """
        self.preload_attempts += 1
        
        try:
            # Get model path from registry
            model_path = self.registry.get_model_path(model_id)
            if not model_path:
                logger.warning(f"Model {model_id} not in registry")
                return False
            
            # Pick optimal GPU using scheduler
            gpu_id, _ = self.scheduler.route_request(model_id)
            gpu_cache = self.scheduler.gpu_caches[gpu_id]
            
            # Load to GPU
            success = gpu_cache.load_model(model_id, model_path)
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to preload {model_id}: {e}")
            return False
    
    def get_stats(self) -> dict:
        """
        Get preloader statistics.
        
        Returns:
            Dict with preload metrics
        """
        total = self.preload_attempts
        success_rate = self.preload_successes / total if total > 0 else 0
        
        return {
            'running': self.running,
            'interval_seconds': self.interval_seconds,
            'confidence_threshold': self.confidence_threshold,
            'max_preloads_per_cycle': self.max_preloads_per_cycle,
            'total_cycles': self.total_cycles,
            'preload_attempts': self.preload_attempts,
            'preload_successes': self.preload_successes,
            'preload_failures': self.preload_failures,
            'preload_skips': self.preload_skips,
            'success_rate': float(success_rate)
        }
    
    def reset_stats(self):
        """Reset all statistics"""
        self.preload_attempts = 0
        self.preload_successes = 0
        self.preload_failures = 0
        self.preload_skips = 0
        self.total_cycles = 0
        logger.info("Preloader statistics reset")
