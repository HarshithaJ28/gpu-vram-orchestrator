"""Configuration module

Loads configuration from environment variables
"""

import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Config:
    """Application configuration"""

    # GPU Settings
    GPU_ENABLED: bool = os.getenv("GPU_ENABLED", "true").lower() == "true"
    NUM_GPUS: Optional[int] = None  # Auto-detect if None
    GPU_RESERVE_MB: int = int(os.getenv("GPU_RESERVE_MB", "2000"))

    # Scheduler Settings
    SCHEDULER_MEMORY_WEIGHT: float = float(os.getenv("SCHEDULER_MEMORY_WEIGHT", "0.50"))
    SCHEDULER_LOAD_WEIGHT: float = float(os.getenv("SCHEDULER_LOAD_WEIGHT", "0.30"))
    SCHEDULER_AFFINITY_WEIGHT: float = float(os.getenv("SCHEDULER_AFFINITY_WEIGHT", "0.20"))

    # Cache Settings
    MAX_PINNED_MODELS: int = int(os.getenv("MAX_PINNED_MODELS", "5"))
    MODELS_DIR: str = os.getenv("MODELS_DIR", "./models")

    # Predictor Settings
    HISTORY_WINDOW_DAYS: int = int(os.getenv("HISTORY_WINDOW_DAYS", "30"))
    PREDICTION_CONFIDENCE_THRESHOLD: float = float(
        os.getenv("PREDICTION_CONFIDENCE_THRESHOLD", "0.4")
    )

    # Server Settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")

    # Redis Settings (for multi-node)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Testing
    TEST_MODE: bool = os.getenv("TEST_MODE", "false").lower() == "true"

    def __init__(self):
        """Initialize and validate configuration"""
        # Validate weights sum to 1.0
        total_weight = (
            self.SCHEDULER_MEMORY_WEIGHT
            + self.SCHEDULER_LOAD_WEIGHT
            + self.SCHEDULER_AFFINITY_WEIGHT
        )
        if abs(total_weight - 1.0) > 0.01:  # Allow small floating point error
            logger.warning(
                f"Scheduler weights don't sum to 1.0: {total_weight}. "
                f"Normalizing..."
            )
            # Normalize
            self.SCHEDULER_MEMORY_WEIGHT /= total_weight
            self.SCHEDULER_LOAD_WEIGHT /= total_weight
            self.SCHEDULER_AFFINITY_WEIGHT /= total_weight

        logger.info(f"Configuration loaded: GPU_ENABLED={self.GPU_ENABLED}")

    def get_summary(self) -> str:
        """Get configuration summary for logging"""
        return f"""
Configuration Summary:
  GPU_ENABLED: {self.GPU_ENABLED}
  GPU_RESERVE_MB: {self.GPU_RESERVE_MB}
  Scheduler Weights: Memory={self.SCHEDULER_MEMORY_WEIGHT}, Load={self.SCHEDULER_LOAD_WEIGHT}, Affinity={self.SCHEDULER_AFFINITY_WEIGHT}
  MAX_PINNED_MODELS: {self.MAX_PINNED_MODELS}
  Server: {self.HOST}:{self.PORT}
  Log Level: {self.LOG_LEVEL}
        """


# Global config instance
config = Config()
