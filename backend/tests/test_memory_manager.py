"""Tests for GPU Memory Manager Module"""

import pytest
from src.gpu import MemoryManager, MemoryAllocation


class TestMemoryManager:
    """Test suite for memory manager"""

    def test_memory_manager_initializes(self, memory_manager):
        """Memory manager initializes correctly"""
        assert memory_manager.gpu_id == 0
        assert memory_manager.total_memory_mb == 10000
        assert memory_manager.reserved_memory_mb == 1000
        assert memory_manager.available_memory_mb == 9000
        assert memory_manager.used_memory_mb == 0

    def test_memory_manager_validation(self):
        """Memory manager validates input on init"""
        # Should raise ValueError for invalid total memory
        with pytest.raises(ValueError):
            MemoryManager(gpu_id=0, total_memory_mb=-100)

        # Should raise ValueError if reserve >= total
        with pytest.raises(ValueError):
            MemoryManager(gpu_id=0, total_memory_mb=1000, reserve_mb=1000)

    def test_can_allocate_success(self, memory_manager):
        """can_allocate returns True when space available"""
        assert memory_manager.can_allocate(1000) is True
        assert memory_manager.can_allocate(5000) is True

    def test_can_allocate_failure(self, memory_manager):
        """can_allocate returns False when insufficient space"""
        # Available is 9000 MB
        assert memory_manager.can_allocate(10000) is False  # Too much
        assert memory_manager.can_allocate(-100) is False   # Negative

    def test_allocate_success(self, memory_manager):
        """allocate succeeds and updates state"""
        result = memory_manager.allocate("model-a", 5000)

        assert result is True
        assert memory_manager.used_memory_mb == 5000
        assert "model-a" in memory_manager.allocations

    def test_allocate_failure_insufficient_space(self, memory_manager):
        """allocate fails when insufficient space"""
        result = memory_manager.allocate("model-a", 10000)

        assert result is False
        assert memory_manager.used_memory_mb == 0
        assert "model-a" not in memory_manager.allocations

    def test_allocate_duplicate_model(self, memory_manager):
        """allocate fails for duplicate model IDs"""
        assert memory_manager.allocate("model-a", 2000) is True
        assert memory_manager.allocate("model-a", 2000) is False  # Duplicate

    def test_allocate_invalid_model_name(self, memory_manager):
        """allocate fails for invalid model ID"""
        result = memory_manager.allocate("", 1000)  # Empty name
        assert result is False

    def test_deallocate_success(self, memory_manager):
        """deallocate removes allocation and updates state"""
        memory_manager.allocate("model-a", 5000)
        assert memory_manager.used_memory_mb == 5000

        result = memory_manager.deallocate("model-a")

        assert result is True
        assert memory_manager.used_memory_mb == 0
        assert "model-a" not in memory_manager.allocations

    def test_deallocate_nonexistent_model(self, memory_manager):
        """deallocate fails gracefully for nonexistent model"""
        result = memory_manager.deallocate("nonexistent")
        assert result is False

    def test_get_usage_percent(self, memory_manager):
        """get_usage_percent calculates correctly"""
        assert memory_manager.get_usage_percent() == 0.0

        memory_manager.allocate("model-a", 4500)  # 50% of 9000
        assert memory_manager.get_usage_percent() == 50.0

        memory_manager.allocate("model-b", 4500)  # 100% of 9000
        assert memory_manager.get_usage_percent() == 100.0

    def test_get_free_memory_mb(self, memory_manager):
        """get_free_memory_mb calculates correctly"""
        assert memory_manager.get_free_memory_mb() == 9000

        memory_manager.allocate("model-a", 3000)
        assert memory_manager.get_free_memory_mb() == 6000

    def test_get_fragmentation_ratio(self, memory_manager):
        """get_fragmentation_ratio works"""
        # Empty = 0 fragmentation
        assert memory_manager.get_fragmentation_ratio() == 0.0

        # Add allocations
        memory_manager.allocate("model-a", 2000)
        frag1 = memory_manager.get_fragmentation_ratio()
        assert frag1 > 0.0

        # More allocations = more fragmentation
        memory_manager.allocate("model-b", 1000)
        frag2 = memory_manager.get_fragmentation_ratio()
        assert frag2 > frag1  # Fragmentation increased

    def test_get_largest_free_block_mb(self, memory_manager):
        """get_largest_free_block_mb estimates correctly"""
        # Fully empty
        block = memory_manager.get_largest_free_block_mb()
        assert block == 9000

        # After first allocation
        memory_manager.allocate("model-a", 3000)
        block = memory_manager.get_largest_free_block_mb()
        assert block <= 6000  # At most 6000 left

    def test_get_stats(self, memory_manager):
        """get_stats returns comprehensive statistics"""
        memory_manager.allocate("model-a", 2000)

        stats = memory_manager.get_stats()

        assert stats['gpu_id'] == 0
        assert stats['total_memory_mb'] == 10000
        assert stats['used_memory_mb'] == 2000
        assert stats['free_memory_mb'] == 7000
        assert stats['usage_percent'] == 2000 / 9000 * 100
        assert stats['num_allocations'] == 1
        assert 'fragmentation_ratio' in stats
        assert 'largest_free_block_mb' in stats

    def test_memory_allocation_dataclass(self):
        """MemoryAllocation dataclass works"""
        import time
        alloc = MemoryAllocation(
            model_id="test",
            gpu_id=0,
            size_mb=1000,
            allocated_at=time.time()
        )

        assert alloc.model_id == "test"
        assert alloc.gpu_id == 0
        assert alloc.size_mb == 1000
        assert alloc.age_seconds >= 0

    def test_sequential_allocation_and_deallocation(self, memory_manager):
        """
        Test realistic scenario: multiple allocations and deallocations
        """
        # Allocate 3 models
        assert memory_manager.allocate("model-a", 2000) is True
        assert memory_manager.allocate("model-b", 3000) is True
        assert memory_manager.allocate("model-c", 3000) is True

        assert memory_manager.used_memory_mb == 8000
        assert memory_manager.get_usage_percent() == 8000 / 9000 * 100

        # Deallocate first model
        assert memory_manager.deallocate("model-a") is True
        assert memory_manager.used_memory_mb == 6000

        # Allocate new model (should fit)
        assert memory_manager.allocate("model-d", 2000) is True
        assert memory_manager.used_memory_mb == 8000

        # Try to allocate beyond capacity
        assert memory_manager.allocate("model-e", 2000) is False

        # Deallocate another
        assert memory_manager.deallocate("model-b") is True
        assert memory_manager.used_memory_mb == 5000

        # Now the new allocation should fit
        assert memory_manager.allocate("model-e", 2000) is True


class TestMemoryManagerCritical:
    """Critical path tests - these MUST pass"""

    def test_allocate_never_negative_memory(self, memory_manager):
        """
        CRITICAL: Memory used can never go negative
        This would cause catastrophic failure
        """
        memory_manager.allocate("model-a", 1000)
        memory_manager.deallocate("model-a")

        assert memory_manager.used_memory_mb >= 0

    def test_allocate_respects_total_memory(self, memory_manager):
        """
        CRITICAL: Used memory can never exceed available
        This would cause GPU OOM errors
        """
        # Try to allocate everything
        memory_manager.allocate("model-a", 5000)
        memory_manager.allocate("model-b", 4000)

        # This would exceed available space
        result = memory_manager.allocate("model-c", 1000)
        assert result is False  # Must fail

        assert memory_manager.used_memory_mb <= memory_manager.available_memory_mb

    def test_no_memory_leaks(self, memory_manager):
        """
        CRITICAL: Deallocate must fully recover memory
        Memory leaks would eventually crash the system
        """
        memory_manager.allocate("model-1", 3000)
        memory_manager.deallocate("model-1")

        # Should be able to allocate same space repeatedly
        for i in range(5):
            memory_manager.allocate(f"model-{i+2}", 3000)
            assert memory_manager.used_memory_mb == 3000
            memory_manager.deallocate(f"model-{i+2}")
            assert memory_manager.used_memory_mb == 0  # Fully recovered
