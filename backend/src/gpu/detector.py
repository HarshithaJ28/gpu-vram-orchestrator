"""GPU Detection Module

Detects available GPUs and provides hardware information.
"""

import torch
import pynvml
from dataclasses import dataclass
from typing import List
import logging

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    """Information about a single GPU device"""
    gpu_id: int
    name: str
    total_memory_mb: int
    compute_capability: tuple
    is_available: bool


class GPUDetector:
    """Detect and monitor GPU hardware"""

    def __init__(self):
        """Initialize GPU detector"""
        try:
            pynvml.nvmlInit()
            self.pynvml_available = True
            logger.info("PYNVML initialized successfully")
        except Exception as e:
            self.pynvml_available = False
            logger.warning(f"PYNVML not available, using PyTorch only. Error: {e}")

    def detect_gpus(self) -> List[GPUInfo]:
        """
        Detect all available GPUs

        Returns:
            List of GPUInfo objects for available GPUs
        """
        if not torch.cuda.is_available():
            logger.warning("CUDA not available - no GPUs detected")
            return []

        gpus = []
        num_gpus = torch.cuda.device_count()
        logger.info(f"Detected {num_gpus} GPU(s)")

        for i in range(num_gpus):
            try:
                name = torch.cuda.get_device_name(i)
                total_mem = torch.cuda.get_device_properties(i).total_memory / (1024**2)
                compute_cap = torch.cuda.get_device_capability(i)

                gpu_info = GPUInfo(
                    gpu_id=i,
                    name=name,
                    total_memory_mb=int(total_mem),
                    compute_capability=compute_cap,
                    is_available=True
                )
                gpus.append(gpu_info)
                logger.info(
                    f"GPU {i}: {name} - {total_mem:.0f}MB "
                    f"Compute Capability: {compute_cap}"
                )

            except Exception as e:
                logger.error(f"Error detecting GPU {i}: {e}")

        return gpus

    def get_free_memory_mb(self, gpu_id: int) -> int:
        """
        Get free memory on GPU in MB

        Args:
            gpu_id: GPU device ID

        Returns:
            Free memory in MB, or 0 if GPU not available

        Raises:
            ValueError: If GPU ID is invalid
        """
        if not torch.cuda.is_available():
            logger.warning("CUDA not available")
            return 0

        try:
            torch.cuda.set_device(gpu_id)
            # mem_get_info returns (free_memory, total_memory)
            free_mem = torch.cuda.mem_get_info(gpu_id)[0] / (1024**2)
            return int(free_mem)
        except Exception as e:
            logger.error(f"Error getting free memory for GPU {gpu_id}: {e}")
            return 0

    def get_utilization_percent(self, gpu_id: int) -> float:
        """
        Get GPU utilization (0-100%)

        Args:
            gpu_id: GPU device ID

        Returns:
            GPU utilization percentage (0.0-100.0), or 0.0 if not available
        """
        if not self.pynvml_available:
            logger.debug("PYNVML not available, returning 0.0")
            return 0.0

        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            return float(util.gpu)
        except Exception as e:
            logger.warning(f"Error getting GPU {gpu_id} utilization: {e}")
            return 0.0

    def get_gpu_name(self, gpu_id: int) -> str:
        """
        Get GPU device name

        Args:
            gpu_id: GPU device ID

        Returns:
            GPU name (e.g., "NVIDIA RTX A100")
        """
        try:
            return torch.cuda.get_device_name(gpu_id)
        except Exception as e:
            logger.error(f"Error getting GPU name: {e}")
            return "Unknown"
