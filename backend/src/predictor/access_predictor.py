"""Access Pattern Predictor Module

Learns and predicts model access patterns using:
- Time-of-day patterns (24 hours)
- Day-of-week patterns (7 days)
- Sequential patterns (A→B correlations)
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Tuple, Dict
import numpy as np
import logging

logger = logging.getLogger(__name__)


class AccessPatternPredictor:
    """
    Learn and predict model access patterns

    Patterns tracked:
    - Time of day (which models peak at which hours)
    - Day of week (which models are accessed on which days)
    - Sequential patterns (model A → model B occurrences)
    """

    def __init__(self, history_window_days: int = 30):
        """
        Initialize predictor

        Args:
            history_window_days: How far back to track patterns
                (default 30 days)
        """
        self.history_window_days = history_window_days
        self.cutoff = datetime.now() - timedelta(days=history_window_days)

        # Access history: model_id -> [timestamps...]
        self.access_history: Dict[str, List[datetime]] = defaultdict(list)

        # Time-based patterns: model_id -> [count per hour 0-23]
        self.hour_patterns: Dict[str, np.ndarray] = defaultdict(lambda: np.zeros(24, dtype=int))

        # Day-based patterns: model_id -> [count per day 0-6, Monday-Sunday]
        self.day_patterns: Dict[str, np.ndarray] = defaultdict(lambda: np.zeros(7, dtype=int))

        # Sequential patterns: model_a -> {model_b: count, model_c: count}
        self.sequential_patterns: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        logger.info(f"AccessPatternPredictor initialized (window: {history_window_days} days)")

    def record_access(self, model_id: str):
        """
        Record that a model was accessed

        Args:
            model_id: Model being accessed
        """
        now = datetime.now()

        # Skip old data outside window
        if now < self.cutoff:
            logger.warning("Access outside history window")
            return

        if not model_id:
            logger.warning("Empty model_id")
            return

        # Record raw access
        self.access_history[model_id].append(now)

        hour = now.hour
        day = now.weekday()  # 0=Monday, 6=Sunday

        # Update time patterns
        self.hour_patterns[model_id][hour] += 1
        self.day_patterns[model_id][day] += 1

        # Update sequential patterns
        # Look for models accessed in last 5 minutes
        recent_cutoff = now - timedelta(minutes=5)

        for other_model, timestamps in self.access_history.items():
            if other_model == model_id:
                continue

            # Did other_model get accessed recently?
            recent_accesses = [t for t in timestamps if recent_cutoff < t < now]
            if recent_accesses:
                # Record: other_model → model_id
                self.sequential_patterns[other_model][model_id] += 1

        logger.debug(f"Recorded access: {model_id}")

    def predict_next_models(
        self, top_k: int = 5, confidence_threshold: float = 0.3
    ) -> List[Tuple[str, float]]:
        """
        Predict top K models likely to be accessed soon

        Weights:
        - 40%: Time-of-day pattern (peak hours)
        - 30%: Day-of-week pattern (peak days)
        - 20%: Overall frequency (popular models)
        - 10%: Recency (recently accessed models)

        Args:
            top_k: Number of predictions to return
            confidence_threshold: Minimum confidence score (0-1)

        Returns:
            List of (model_id, probability) tuples, sorted by probability descending
        """
        now = datetime.now()
        hour = now.hour
        day = now.weekday()

        scores: Dict[str, float] = {}

        for model_id in self.access_history:
            score = 0.0

            # Factor 1: Time-of-day pattern (40%)
            total_hour_accesses = np.sum(self.hour_patterns[model_id])
            if total_hour_accesses > 0:
                hour_prob = self.hour_patterns[model_id][hour] / total_hour_accesses
                score += 0.40 * hour_prob

            # Factor 2: Day-of-week pattern (30%)
            total_day_accesses = np.sum(self.day_patterns[model_id])
            if total_day_accesses > 0:
                day_prob = self.day_patterns[model_id][day] / total_day_accesses
                score += 0.30 * day_prob

            # Factor 3: Overall frequency (20%)
            total_accesses = len(self.access_history[model_id])
            if total_accesses > 20:  # Need minimum samples
                freq_score = min(total_accesses / 1000, 1.0)
                score += 0.20 * freq_score

            # Factor 4: Recency (10%)
            if self.access_history[model_id]:
                last_access = self.access_history[model_id][-1]
                recency_minutes = (now - last_access).total_seconds() / 60
                if recency_minutes < 60:  # Accessed in last hour
                    score += 0.10 * (1.0 - recency_minutes / 60)

            scores[model_id] = score

        # Filter by confidence and sort
        predictions = [
            (model_id, score) for model_id, score in scores.items() if score >= confidence_threshold
        ]
        predictions.sort(key=lambda x: x[1], reverse=True)

        logger.debug(f"Predicted {len(predictions)} models (top {top_k})")

        return predictions[:top_k]

    def get_sequential_prediction(self, recent_models: List[str], top_k: int = 3) -> List[str]:
        """
        Predict next models based on recent access sequence

        Example:
        - Recent: ["fraud-v1", "fraud-v2"]
        - Returns: ["fraud-v3", "recommendation-core", ...]

        Args:
            recent_models: Models accessed recently (in order)
            top_k: Number of predictions

        Returns:
            List of predicted model IDs
        """
        if not recent_models:
            return []

        predictions: Dict[str, int] = defaultdict(int)

        for recent_model in recent_models:
            if recent_model in self.sequential_patterns:
                for next_model, count in self.sequential_patterns[recent_model].items():
                    predictions[next_model] += count

        # Sort and return
        sorted_preds = sorted(predictions.items(), key=lambda x: x[1], reverse=True)
        return [model_id for model_id, _ in sorted_preds[:top_k]]

    def get_stats(self) -> Dict:
        """
        Get predictor statistics

        Returns:
            Dictionary with prediction stats
        """
        return {
            "models_tracked": len(self.access_history),
            "total_accesses": sum(len(v) for v in self.access_history.values()),
            "sequential_patterns": sum(len(v) for v in self.sequential_patterns.values()),
            "window_days": self.history_window_days,
        }

    def clear(self):
        """Clear all pattern history"""
        self.access_history.clear()
        self.hour_patterns.clear()
        self.day_patterns.clear()
        self.sequential_patterns.clear()
        logger.info("Cleared all access patterns")
