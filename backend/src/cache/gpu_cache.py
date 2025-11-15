"""GPU Model Cache Module

Thread-safe LRU cache for GPU models with smart eviction.
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
import threading
import time
from typing import Any, Optional, Dict
import logging

logger = logging.getLogger(__name__)


@dataclass
class LoadedModel:
    """Represents a model loaded in GPU memory"""
    model_id: str
    memory_usage_mb: int
    loaded_at: datetime
    last_accessed: datetime
    access_count: int
    is_pinned: bool = False  # Never evict if pinned
    model: Any = None

    @property
    def age_seconds(self) -> float:
        """How many seconds since model was loaded"""
        return (datetime.now() - self.loaded_at).total_seconds()

    @property
    def last_access_age_seconds(self) -> float:
        """How many seconds since last access"""
        return (datetime.now() - self.last_accessed).total_seconds()


class GPUModelCache:
    """
    Thread-safe LRU cache for GPU models

    Handles:
    - Model loading/unloading
    - LRU eviction (least recently used)
    - Pinned models (hot path - never evict)
    - Memory tracking
    - Cache statistics (hit rate, evictions, etc.)
    """

    def __init__(
        self,
        gpu_id: int,
        total_memory_mb: int = 24000,
        reserved_memory_mb: int = 2000
    ):
        """
        Initialize GPU model cache

        Args:
            gpu_id: GPU device ID
            total_memory_mb: Total GPU memory (default 24GB)
            reserved_memory_mb: Memory to reserve for CUDA overhead
        """
        self.gpu_id = gpu_id
        self.total_memory_mb = total_memory_mb
        self.reserved_memory_mb = reserved_memory_mb
        self.available_memory_mb = total_memory_mb - reserved_memory_mb
        self.used_memory_mb = 0

        # LRU cache: model_id -> LoadedModel (OrderedDict maintains insertion order)
        self.models: OrderedDict[str, LoadedModel] = OrderedDict()

        # Thread safety
        self.lock = threading.RLock()

        # Statistics
        self.cache_hits = 0
        self.cache_misses = 0
        self.evictions = 0
        self.failed_loads = 0

        logger.info(
            f"GPU Cache {gpu_id} initialized: "
            f"Total {total_memory_mb}MB, Available {self.available_memory_mb}MB"
        )

    def get_model(self, model_id: str) -> Optional[LoadedModel]:
        """
        Get model from cache

        Args:
            model_id: Model identifier

        Returns:
            LoadedModel if found, None otherwise
            (Updates LRU order on hit)
        """
        with self.lock:
            if model_id not in self.models:
                self.cache_misses += 1
                logger.debug(f"Cache miss for {model_id} on GPU {self.gpu_id}")
                return None

            # Cache hit - move to end (most recently used)
            self.cache_hits += 1
            model = self.models[model_id]
            model.last_accessed = datetime.now()
            model.access_count += 1
            self.models.move_to_end(model_id)

            logger.debug(
                f"Cache hit for {model_id}: "
                f"{self.cache_hits} hits, {self.cache_misses} misses"
            )

            return model

    def load_model(
        self,
        model_id: str,
        model: Any,
        memory_mb: int,
        pin: bool = False
    ) -> bool:
        """
        Load model onto GPU

        Args:
            model_id: Unique model identifier
            model: PyTorch/TensorFlow model object
            memory_mb: Estimated memory usage
            pin: If True, never evict this model

        Returns:
            True if successful, False otherwise
        """
        if not model_id:
            logger.error("Empty model_id")
            self.failed_loads += 1
            return False

        with self.lock:
            # Already loaded?
            if model_id in self.models:
                logger.info(f"Model {model_id} already loaded on GPU {self.gpu_id}")
                return True

            # Size validation
            if memory_mb <= 0:
                logger.warning(f"Invalid memory size for {model_id}: {memory_mb}MB")
                self.failed_loads += 1
                return False

            if memory_mb > self.available_memory_mb:
                logger.error(
                    f"Model {model_id} ({memory_mb}MB) exceeds available "
                    f"GPU {self.gpu_id} memory ({self.available_memory_mb}MB)"
                )
                self.failed_loads += 1
                return False

            # Make space by evicting LRU models
            while self.used_memory_mb + memory_mb > self.available_memory_mb:
                if not self._evict_lru():
                    logger.error(
                        f"Cannot free enough space for {model_id} "
                        f"(need {memory_mb}MB, have {self.available_memory_mb - self.used_memory_mb}MB)"
                    )
                    self.failed_loads += 1
                    return False

            # Load model
            try:
                # In real implementation, this would load to GPU
                # For now, just track in cache
                self.models[model_id] = LoadedModel(
                    model_id=model_id,
                    memory_usage_mb=memory_mb,
                    loaded_at=datetime.now(),
                    last_accessed=datetime.now(),
                    access_count=1,
                    is_pinned=pin,
                    model=model
                )

                self.used_memory_mb += memory_mb

                logger.info(
                    f"Loaded {model_id} on GPU {self.gpu_id}: "
                    f"{memory_mb}MB (total: {self.used_memory_mb}MB)"
                )
                return True

            except Exception as e:
                logger.error(f"Failed to load {model_id}: {e}")
                self.failed_loads += 1
                return False

    def _evict_lru(self) -> bool:
        """
        Evict least recently used model (that's not pinned)

        Returns:
            True if evicted, False if no unpinned models
        """
        with self.lock:
            # Find first unpinned model (LRU order)
            for model_id, model in self.models.items():
                if not model.is_pinned:
                    # Evict this one
                    freed = model.memory_usage_mb
                    del self.models[model_id]
                    self.used_memory_mb -= freed
                    self.evictions += 1

                    logger.info(
                        f"Evicted {model_id} from GPU {self.gpu_id} "
                        f"(freed {freed}MB, total evictions: {self.evictions})"
                    )
                    return True

            # No unpinned models to evict
            logger.warning(
                f"No unpinned models to evict on GPU {self.gpu_id} "
                f"(all {len(self.models)} models are pinned)"
            )
            return False

    def pin_model(self, model_id: str) -> bool:
        """
        Pin a model (never evict)

        Used for hot models (fraud detection, recommendations)

        Args:
            model_id: Model to pin

        Returns:
            True if successful, False if model not found
        """
        with self.lock:
            if model_id not in self.models:
                logger.warning(f"Cannot pin {model_id} - not loaded on GPU {self.gpu_id}")
                return False

            self.models[model_id].is_pinned = True
            logger.info(f"Pinned {model_id} on GPU {self.gpu_id}")
            return True

    def unpin_model(self, model_id: str) -> bool:
        """
        Unpin a model (can be evicted)

        Args:
            model_id: Model to unpin

        Returns:
            True if successful, False if model not found
        """
        with self.lock:
            if model_id not in self.models:
                logger.warning(f"Cannot unpin {model_id} - not loaded on GPU {self.gpu_id}")
                return False

            self.models[model_id].is_pinned = False
            logger.info(f"Unpinned {model_id} on GPU {self.gpu_id}")
            return True

    def unload_model(self, model_id: str) -> bool:
        """
        Explicitly unload a model

        Args:
            model_id: Model to unload

        Returns:
            True if successful, False if not found
        """
        with self.lock:
            if model_id not in self.models:
                return False

            model = self.models[model_id]
            freed = model.memory_usage_mb
            del self.models[model_id]
            self.used_memory_mb -= freed

            logger.info(f"Unloaded {model_id} from GPU {self.gpu_id} (freed {freed}MB)")
            return True

    def get_stats(self) -> Dict:
        """
        Get cache statistics

        Returns:
            Dictionary with comprehensive cache stats
        """
        with self.lock:
            total_requests = self.cache_hits + self.cache_misses
            hit_rate = self.cache_hits / total_requests if total_requests > 0 else 0.0

            return {
                'gpu_id': self.gpu_id,
                'models_loaded': len(self.models),
                'memory_used_mb': self.used_memory_mb,
                'memory_free_mb': self.available_memory_mb - self.used_memory_mb,
                'memory_total_mb': self.available_memory_mb,
                'utilization_pct': (self.used_memory_mb / self.available_memory_mb) * 100 if self.available_memory_mb > 0 else 0,
                'cache_hits': self.cache_hits,
                'cache_misses': self.cache_misses,
                'hit_rate': hit_rate,
                'evictions': self.evictions,
                'failed_loads': self.failed_loads,
                'models': [
                    {
                        'model_id': m.model_id,
                        'memory_mb': m.memory_usage_mb,
                        'access_count': m.access_count,
                        'pinned': m.is_pinned,
                        'age_seconds': m.age_seconds,
                        'last_access_seconds': m.last_access_age_seconds
                    }
                    for m in self.models.values()
                ]
            }

    def clear(self):
        """Clear all models from cache"""
        with self.lock:
            self.models.clear()
            self.used_memory_mb = 0
            logger.info(f"Cleared GPU {self.gpu_id} cache")
