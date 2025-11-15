"""Pytest configuration and fixtures for all tests"""

import pytest
import os
import torch
import logging
from src.gpu import GPUDetector, MemoryManager

# Disable GPU for tests (CI environment)
os.environ["GPU_ENABLED"] = "false"
os.environ["TEST_MODE"] = "true"

# Suppress verbose logging during tests
logging.getLogger("torch").setLevel(logging.WARNING)
logging.getLogger("pynvml").setLevel(logging.WARNING)


@pytest.fixture
def gpu_detector():
    """Fixture: GPU Detector instance"""
    return GPUDetector()


@pytest.fixture
def memory_manager():
    """Fixture: Memory Manager instance for testing"""
    return MemoryManager(
        gpu_id=0,
        total_memory_mb=10000,
        reserve_mb=1000
    )


@pytest.fixture
def mock_gpu_list(monkeypatch):
    """Fixture: Mock GPU detection"""
    def mock_detect_gpus():
        from src.gpu import GPUInfo
        return [
            GPUInfo(
                gpu_id=0,
                name="Mock GPU 0",
                total_memory_mb=24000,
                compute_capability=(8, 0),
                is_available=True
            ),
            GPUInfo(
                gpu_id=1,
                name="Mock GPU 1",
                total_memory_mb=24000,
                compute_capability=(8, 0),
                is_available=True
            ),
        ]

    detector = GPUDetector()
    monkeypatch.setattr(detector, "detect_gpus", mock_detect_gpus)
    return detector, mock_detect_gpus()


@pytest.fixture(autouse=True)
def skip_on_no_gpu(request):
    """
    Auto-skip GPU-specific tests if no GPU available

    Usage:
        @pytest.mark.skipif_no_gpu
        def test_something():
            ...
    """
    if hasattr(request, "node"):
        if request.node.get_closest_marker("skipif_no_gpu"):
            if not torch.cuda.is_available():
                pytest.skip("No GPU available")
