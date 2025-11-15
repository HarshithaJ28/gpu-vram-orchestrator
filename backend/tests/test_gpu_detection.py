"""Tests for GPU Detection Module"""

import pytest
import torch
from src.gpu import GPUDetector, GPUInfo


class TestGPUDetection:
    """Test suite for GPU detector"""

    def test_detector_initializes(self, gpu_detector):
        """GPU detector initializes without errors"""
        assert gpu_detector is not None

    def test_detect_gpus_returns_list(self, gpu_detector):
        """detect_gpus returns a list"""
        gpus = gpu_detector.detect_gpus()
        assert isinstance(gpus, list)
        # In CI: might be 0 GPUs
        # Locally: depends on hardware

    def test_detect_gpus_returns_gpu_info(self, gpu_detector):
        """Each GPU is a GPUInfo dataclass"""
        gpus = gpu_detector.detect_gpus()

        if len(gpus) > 0:
            gpu = gpus[0]
            assert isinstance(gpu, GPUInfo)
            assert gpu.gpu_id >= 0
            assert gpu.name is not None
            assert gpu.total_memory_mb > 0
            assert gpu.compute_capability is not None
            assert gpu.is_available is True

    def test_get_free_memory_returns_int(self, gpu_detector):
        """get_free_memory_mb returns integer"""
        free = gpu_detector.get_free_memory_mb(0)
        assert isinstance(free, int)
        assert free >= 0

    def test_get_free_memory_invalid_gpu(self, gpu_detector):
        """get_free_memory_mb handles invalid GPU ID gracefully"""
        # Should return 0 for invalid GPU, not crash
        free = gpu_detector.get_free_memory_mb(999)
        assert isinstance(free, int)
        assert free == 0  # No GPU, so 0 memory

    def test_get_utilization_percent_returns_float(self, gpu_detector):
        """get_utilization_percent returns float"""
        util = gpu_detector.get_utilization_percent(0)
        assert isinstance(util, float)
        assert 0.0 <= util <= 100.0  # Should be percentage

    def test_get_utilization_percent_handles_no_pynvml(self, gpu_detector):
        """get_utilization_percent handles missing PYNVML gracefully"""
        # If PYNVML not available, should return 0.0 not crash
        util = gpu_detector.get_utilization_percent(0)
        assert isinstance(util, float)
        # In CI, pynvml might not work, so expect 0.0
        if not gpu_detector.pynvml_available:
            assert util == 0.0

    def test_gpu_info_dataclass(self):
        """GPUInfo dataclass works"""
        gpu = GPUInfo(
            gpu_id=0,
            name="Test GPU",
            total_memory_mb=24000,
            compute_capability=(8, 0),
            is_available=True
        )

        assert gpu.gpu_id == 0
        assert gpu.name == "Test GPU"
        assert gpu.total_memory_mb == 24000
        assert gpu.compute_capability == (8, 0)
        assert gpu.is_available is True

    def test_get_gpu_name(self, gpu_detector):
        """get_gpu_name returns string"""
        name = gpu_detector.get_gpu_name(0)
        assert isinstance(name, str)
        # In CI, might be "Unknown" if no GPU

    def test_detect_gpus_with_no_cuda(self, monkeypatch, gpu_detector):
        """detect_gpus handles CUDA unavailable gracefully"""
        # Mock CUDA as unavailable
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        
        gpus = gpu_detector.detect_gpus()
        assert gpus == []  # Should return empty list


class TestGPUDetectionCritical:
    """Critical path tests - these MUST pass"""

    def test_detector_does_not_crash_on_init(self):
        """
        CRITICAL: GPUDetector must never crash on initialization
        This is essential because it's called on app startup
        """
        try:
            detector = GPUDetector()
            # Should successfully initialize
            assert detector is not None
        except Exception as e:
            pytest.fail(f"GPUDetector initialization crashed: {e}")

    def test_detect_gpus_never_raises_exception(self, gpu_detector):
        """
        CRITICAL: detect_gpus must not raise exceptions
        Failing here breaks the entire system
        """
        try:
            gpus = gpu_detector.detect_gpus()
            assert isinstance(gpus, list)
        except Exception as e:
            pytest.fail(f"detect_gpus raised exception: {e}")

    def test_memory_checks_never_raise(self, gpu_detector):
        """
        CRITICAL: Memory queries must fail gracefully
        Should return safe default (0) not crash
        """
        try:
            free = gpu_detector.get_free_memory_mb(999)  # Invalid GPU
            util = gpu_detector.get_utilization_percent(999)  # Invalid GPU
            
            assert isinstance(free, int) and free == 0
            assert isinstance(util, float) and util == 0.0
        except Exception as e:
            pytest.fail(f"Memory check raised exception: {e}")
