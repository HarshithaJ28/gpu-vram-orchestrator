"""GPU Memory Manager Module

Manages GPU memory allocation and deallocation.
"""

import torch
import time
from dataclasses import dataclass, field
from typing import Dict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class MemoryAllocation:
    """Represents a memory allocation on GPU"""

    model_id: str
    gpu_id: int
    size_mb: int
    allocated_at: float
    allocated_timestamp: datetime = field(default_factory=datetime.now)

    @property
    def age_seconds(self) -> float:
        """How many seconds since allocation"""
        return time.time() - self.allocated_at


class MemoryManager:
    """Manage GPU memory allocation and deallocation"""

    def __init__(self, gpu_id: int, total_memory_mb: int, reserve_mb: int = 2000):
        """
        Initialize memory manager

        Args:
            gpu_id: GPU device ID
            total_memory_mb: Total GPU memory available in MB
            reserve_mb: Memory to reserve for CUDA overhead (default 2GB)

        Critical: Always reserve 2-3GB for CUDA runtime overhead.
        This prevents unexpected OOM errors.
        """
        # Validation: sanity checks
        if total_memory_mb <= 0:
            raise ValueError(f"Invalid total_memory_mb: {total_memory_mb}")
        if reserve_mb >= total_memory_mb:
            raise ValueError(f"Reserve ({reserve_mb}MB) >= total ({total_memory_mb}MB)")

        self.gpu_id = gpu_id
        self.total_memory_mb = total_memory_mb
        self.reserved_memory_mb = reserve_mb
        self.available_memory_mb = total_memory_mb - reserve_mb
        self.used_memory_mb = 0

        # Track allocations: model_id -> MemoryAllocation
        self.allocations: Dict[str, MemoryAllocation] = {}

        logger.info(
            f"Memory Manager initialized for GPU {gpu_id}: "
            f"Total: {total_memory_mb}MB, "
            f"Available: {self.available_memory_mb}MB"
        )

    def can_allocate(self, size_mb: int) -> bool:
        """
        Check if we have space for this allocation

        Args:
            size_mb: Required memory in MB

        Returns:
            True if allocation would fit, False otherwise
        """
        if size_mb < 0:
            logger.warning(f"Negative allocation size: {size_mb}MB")
            return False

        available = self.available_memory_mb - self.used_memory_mb
        can_fit = (self.used_memory_mb + size_mb) <= self.available_memory_mb

        if not can_fit:
            logger.debug(
                f"Cannot allocate {size_mb}MB (used: {self.used_memory_mb}MB, "
                f"available: {available}MB)"
            )

        return can_fit

    def allocate(self, model_id: str, size_mb: int) -> bool:
        """
        Allocate memory for model

        Args:
            model_id: Unique model ID
            size_mb: Memory requirement in MB

        Returns:
            True if allocation successful, False otherwise
        """
        # Validation
        if not model_id:
            logger.error("Empty model_id")
            return False

        if model_id in self.allocations:
            logger.warning(f"Model {model_id} already allocated")
            return False

        if not self.can_allocate(size_mb):
            logger.warning(
                f"Cannot allocate {size_mb}MB for {model_id} " f"(used: {self.used_memory_mb}MB)"
            )
            return False

        # Allocate
        self.allocations[model_id] = MemoryAllocation(
            model_id=model_id, gpu_id=self.gpu_id, size_mb=size_mb, allocated_at=time.time()
        )
        self.used_memory_mb += size_mb

        logger.debug(
            f"Allocated {size_mb}MB for {model_id} " f"(total used: {self.used_memory_mb}MB)"
        )
        return True

    def deallocate(self, model_id: str) -> bool:
        """
        Deallocate memory for a model

        Args:
            model_id: Model to deallocate

        Returns:
            True if deallocation successful, False otherwise
        """
        if model_id not in self.allocations:
            logger.warning(f"Model {model_id} not allocated")
            return False

        alloc = self.allocations[model_id]
        self.used_memory_mb -= alloc.size_mb
        del self.allocations[model_id]

        # Critical: Always clear GPU cache after deallocation
        # (but only if CUDA is available)
        try:
            if torch.cuda.is_available():
                torch.cuda.set_device(self.gpu_id)
                torch.cuda.empty_cache()
            logger.debug(f"Deallocated {alloc.size_mb}MB for {model_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing GPU cache: {e}")
            # Still return True because memory was logically freed
            # even if GPU cache clearing failed
            return True

    def get_usage_percent(self) -> float:
        """
        Get memory usage as percentage

        Returns:
            Usage percentage (0-100)
        """
        if self.available_memory_mb <= 0:
            return 0.0
        return (self.used_memory_mb / self.available_memory_mb) * 100

    def get_free_memory_mb(self) -> int:
        """
        Get free memory available

        Returns:
            Free memory in MB
        """
        return self.available_memory_mb - self.used_memory_mb

    def get_fragmentation_ratio(self) -> float:
        """
        Calculate memory fragmentation ratio

        0.0 = perfect, 1.0 = heavily fragmented

        Simple heuristic: (number of allocations) /
        (total available memory / 1000)
        This estimates internal fragmentation.

        Returns:
            Fragmentation ratio (0-1)
        """
        if self.used_memory_mb == 0:
            return 0.0

        # More allocations → more fragmented
        num_allocations = len(self.allocations)
        norm_factor = self.available_memory_mb / 1000
        fragmentation = min(num_allocations / norm_factor, 1.0)
        return fragmentation

    def get_largest_free_block_mb(self) -> int:
        """
        Estimate largest contiguous free block (simplified)

        In reality, this would require GPU level memory info.
        We approximate with worst-case: total free / (num allocations + 1)

        Returns:
            Estimated largest free block in MB
        """
        free = self.get_free_memory_mb()
        if len(self.allocations) == 0:
            return free

        # Rough estimate: assuming equal-sized fragments
        num_fragments = len(self.allocations) + 1
        return max(free // num_fragments, 0)

    def get_stats(self) -> dict:
        """
        Get comprehensive memory statistics

        Returns:
            Dictionary with memory stats
        """
        return {
            "gpu_id": self.gpu_id,
            "total_memory_mb": self.total_memory_mb,
            "reserved_memory_mb": self.reserved_memory_mb,
            "available_memory_mb": self.available_memory_mb,
            "used_memory_mb": self.used_memory_mb,
            "free_memory_mb": self.get_free_memory_mb(),
            "usage_percent": self.get_usage_percent(),
            "num_allocations": len(self.allocations),
            "fragmentation_ratio": self.get_fragmentation_ratio(),
            "largest_free_block_mb": self.get_largest_free_block_mb(),
        }
