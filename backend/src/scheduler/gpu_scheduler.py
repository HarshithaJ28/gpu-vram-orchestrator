"""GPU Scheduler Module

Intelligent multi-factor scheduler for GPU selection.
Uses weighted combination of memory availability, current load,
and model affinity.
"""

from dataclasses import dataclass
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class SchedulingScore:
    """Score for a GPU scheduling decision"""

    gpu_id: int
    memory_score: float  # 0-1
    load_score: float  # 0-1
    affinity_score: float  # 0-1
    total_score: float  # Weighted sum
    reasoning: str


class GPUScheduler:
    """
    Intelligent multi-factor GPU scheduler

    Scheduling factors:
    1. Available Memory (50% weight) - Essential
    2. Current Load (30% weight) - Spread load evenly
    3. Model Affinity (20% weight) - Cache/performance
    """

    WEIGHTS = {"memory": 0.50, "load": 0.30, "affinity": 0.20}

    def __init__(self, gpu_caches: List = None):
        """
        Initialize scheduler

        Args:
            gpu_caches: List of GPUModelCache instances
                (can be empty for testing)
        """
        self.gpu_caches = gpu_caches or []
        self.pending_requests = {}  # gpu_id -> count of pending requests
        self.model_access_history = {}  # model_id -> [gpu_id, gpu_id, ...]

        # Validate weights
        total = sum(self.WEIGHTS.values())
        if abs(total - 1.0) > 0.01:  # Allow small fp error
            logger.warning(
                f"Scheduler weights don't sum to 1.0: {total}. " f"Please fix WEIGHTS dict."
            )

        logger.info(
            f"GPUScheduler initialized with {len(self.gpu_caches)} "
            f"GPUs Weights: Memory={self.WEIGHTS['memory']}, "
            f"Load={self.WEIGHTS['load']}, "
            f"Affinity={self.WEIGHTS['affinity']}"
        )

    def score_gpu(self, model_id: str, gpu_id: int) -> SchedulingScore:
        """
        Score a GPU for this model (0.0 = bad, 1.0 = perfect)

        Args:
            model_id: Model identifier
            gpu_id: GPU device ID

        Returns:
            SchedulingScore with detailed breakdown
        """
        if gpu_id >= len(self.gpu_caches):
            logger.warning(f"Invalid GPU ID: {gpu_id}")
            return SchedulingScore(
                gpu_id=gpu_id,
                memory_score=0.0,
                load_score=0.0,
                affinity_score=0.0,
                total_score=0.0,
                reasoning="Invalid GPU ID",
            )

        gpu = self.gpu_caches[gpu_id]
        stats = gpu.get_stats()

        # Factor 1: Memory availability
        memory_score = self._score_memory(stats)

        # Factor 2: Current load
        load_score = self._score_load(gpu_id)

        # Factor 3: Affinity (keep similar models together)
        affinity_score = self._score_affinity(model_id, gpu_id)

        # Weighted sum
        total_score = (
            self.WEIGHTS["memory"] * memory_score
            + self.WEIGHTS["load"] * load_score
            + self.WEIGHTS["affinity"] * affinity_score
        )

        return SchedulingScore(
            gpu_id=gpu_id,
            memory_score=memory_score,
            load_score=load_score,
            affinity_score=affinity_score,
            total_score=total_score,
            reasoning=(
                f"Mem:{memory_score:.2f} Load:{load_score:.2f} "
                f"Aff:{affinity_score:.2f} = {total_score:.2f}"
            ),
        )

    def _score_memory(self, stats: dict) -> float:
        """
        Score available memory (more available = higher score)

        Scoring curve:
        - 0-10% free: score = 0.0 (no room, risky)
        - 10-30% free: score = 0.0-0.5 (limited room)
        - 30-100% free: score = 0.5-1.0 (plenty of room)

        Args:
            stats: GPU stats dict with 'memory_free_mb' and 'memory_total_mb'

        Returns:
            Score 0.0-1.0
        """
        if stats.get("memory_total_mb", 0) <= 0:
            logger.warning("Invalid memory stats")
            return 0.0

        free_pct = stats["memory_free_mb"] / stats["memory_total_mb"]

        if free_pct < 0.10:
            return 0.0
        elif free_pct < 0.30:
            # Linear interpolation: 0.1 → 0.0, 0.3 → 0.5
            return 0.5 * (free_pct - 0.10) / 0.20
        else:
            # Linear interpolation: 0.3 → 0.5, 1.0 → 1.0
            return 0.5 + 0.5 * (free_pct - 0.30) / 0.70

    def _score_load(self, gpu_id: int) -> float:
        """
        Score load (fewer pending requests = higher score)

        Uses inverse sigmoid: 1 / (1 + pending_requests)
        This penalizes busy GPUs while still allowing them to receive requests.

        Args:
            gpu_id: GPU device ID

        Returns:
            Score 0.0-1.0 (1.0 = no pending requests)
        """
        pending = self.pending_requests.get(gpu_id, 0)
        # Sigmoid-like curve: starts at 1.0, decreases as pending increases
        return 1.0 / (1.0 + pending)

    def _score_affinity(self, model_id: str, gpu_id: int) -> float:
        """
        Score affinity (how many similar models already on this GPU?)

        Example:
        - fraud-detection-v1 and fraud-detection-v2 on same GPU = high affinity
        - recommendation-v1 and image-classifier on same GPU = low affinity

        Args:
            model_id: Model to schedule
            gpu_id: GPU device ID

        Returns:
            Score 0.0-1.0 (1.0 = many similar models already present)
        """
        # Extract category (everything before version)
        target_category = self._extract_category(model_id)

        # Count how many models in same category on this GPU
        same_category_count = 0
        if gpu_id < len(self.gpu_caches):
            for loaded_model in self.gpu_caches[gpu_id].models.values():
                model_cat = self._extract_category(loaded_model.model_id)
                if model_cat == target_category:
                    same_category_count += 1

        # Normalize: max 5 models per category = 1.0 score
        # This allows multiple versions of same category but doesn't
        # overweight it
        affinity = min(same_category_count / 5.0, 1.0)

        return affinity

    def _extract_category(self, model_id: str) -> str:
        """
        Extract model category from ID

        Examples:
        - fraud-detection-v1 → fraud-detection
        - recommendation-core-v2 → recommendation-core
        - image-classifier → image-classifier

        Args:
            model_id: Model ID string

        Returns:
            Category name
        """
        if not model_id:
            return ""

        parts = model_id.split("-")

        # Remove version suffix (starts with 'v' and is all digits)
        if len(parts) > 0:
            last_part = parts[-1]
            if last_part.startswith("v") and last_part[1:].isdigit():
                return "-".join(parts[:-1])

        return model_id

    def route_request(self, model_id: str) -> Tuple[int, bool]:
        """
        CRITICAL METHOD: Route to optimal GPU

        HOT PATH (cache hit): Model already loaded
        COLD PATH (cache miss): Pick optimal GPU

        This method implements the core advantage:
        - 1st request: ~100ms (cold, needs load)
        - 2nd+ requests: ~5ms (hot, already loaded)

        Args:
            model_id: Model to run prediction on

        Returns:
            (gpu_id, was_cached) - GPU to use and cached status
        """
        # HOT PATH: Check if model already loaded
        for gpu_id, gpu_cache in enumerate(self.gpu_caches):
            if model_id in gpu_cache.models:
                # Cache hit!
                self.record_access(model_id, gpu_id)
                logger.debug(f"HOT: {model_id} found on GPU {gpu_id}")
                return (gpu_id, True)  # ← FAST PATH

        # COLD PATH: Pick best GPU for loading
        best_gpu_id, score = self.select_best_gpu(model_id)
        self.record_request(best_gpu_id)
        self.record_access(model_id, best_gpu_id)

        logger.debug(f"COLD: {model_id} → GPU {best_gpu_id} ({score.reasoning})")
        return (best_gpu_id, False)  # ← Will need to load model

    def release_request(self, gpu_id: int):
        """Clean up after request completes"""
        self.clear_request(gpu_id)

    def select_best_gpu(self, model_id: str) -> Tuple[int, "SchedulingScore"]:
        """
        Select the best GPU for this model

        Args:
            model_id: Model to schedule

        Returns:
            (best_gpu_id, score) - GPU ID and detailed scoring

        Raises:
            ValueError: If no GPUs available
        """
        if not self.gpu_caches:
            raise ValueError("No GPUs available")

        scores = []
        for gpu_id in range(len(self.gpu_caches)):
            score = self.score_gpu(model_id, gpu_id)
            scores.append(score)

        # Return GPU with highest total score
        best = max(scores, key=lambda s: s.total_score)

        logger.debug(f"Selected GPU {best.gpu_id} for {model_id}: {best.reasoning}")

        return best.gpu_id, best

    def record_request(self, gpu_id: int):
        """
        Record pending request on GPU

        Args:
            gpu_id: GPU device ID
        """
        self.pending_requests[gpu_id] = self.pending_requests.get(gpu_id, 0) + 1

    def clear_request(self, gpu_id: int):
        """
        Clear completed request

        Args:
            gpu_id: GPU device ID
        """
        if gpu_id in self.pending_requests and self.pending_requests[gpu_id] > 0:
            self.pending_requests[gpu_id] -= 1

    def record_access(self, model_id: str, gpu_id: int):
        """
        Record model access on GPU (for affinity tracking)

        Args:
            model_id: Model ID
            gpu_id: GPU device ID
        """
        if model_id not in self.model_access_history:
            self.model_access_history[model_id] = []
        self.model_access_history[model_id].append(gpu_id)

    def get_stats(self) -> dict:
        """
        Get scheduler statistics

        Returns:
            Dictionary with scheduler stats
        """
        return {
            "num_gpus": len(self.gpu_caches),
            "pending_requests": dict(self.pending_requests),
            "model_access_history_size": len(self.model_access_history),
            "weights": self.WEIGHTS,
        }
