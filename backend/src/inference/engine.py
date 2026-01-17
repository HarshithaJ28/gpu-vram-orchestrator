"""Production-Grade Inference Engine

Handles model inference with preprocessing, postprocessing, and GPU management.
"""

import torch
import logging
import numpy as np
from typing import Any, Dict, List, Callable
from dataclasses import dataclass
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class InferenceResult:
    """Result from model inference"""

    prediction: Any
    latency_ms: float
    gpu_id: int
    model_id: str
    cached: bool
    batch_size: int = 1


class InferenceEngine:
    """
    Production-grade inference engine

    Features:
    - Synchronous and asynchronous inference
    - Batch processing
    - Custom preprocessing/postprocessing pipelines
    - Automatic device management
    - Comprehensive error handling
    """

    def __init__(self):
        """Initialize inference engine"""
        self.preprocessors: Dict[str, Callable] = {}
        self.postprocessors: Dict[str, Callable] = {}
        logger.info("InferenceEngine initialized")

    def register_preprocessor(self, model_id: str, preprocessor: Callable):
        """
        Register custom preprocessing function

        Args:
            model_id: Model identifier
            preprocessor: Function that transforms input_data dict to
                torch.Tensor
        """
        self.preprocessors[model_id] = preprocessor
        logger.info(f"Registered preprocessor for {model_id}")

    def register_postprocessor(self, model_id: str, postprocessor: Callable):
        """
        Register custom postprocessing function

        Args:
            model_id: Model identifier
            postprocessor: Function that takes torch.Tensor and returns output
        """
        self.postprocessors[model_id] = postprocessor
        logger.info(f"Registered postprocessor for {model_id}")

    async def predict(
        self, model: torch.nn.Module, input_data: Dict[str, Any], model_id: str, gpu_id: int
    ) -> Any:
        """
        Run asynchronous inference on model

        Flow:
        1. Preprocess input
        2. Move to GPU
        3. Run forward pass
        4. Postprocess output

        Args:
            model: Loaded PyTorch model
            input_data: Input data dictionary
            model_id: Model identifier
            gpu_id: GPU device ID

        Returns:
            Model prediction
        """
        try:
            # Preprocess
            input_tensor = self._preprocess(input_data, model_id)

            # Run synchronously (inference is typically CPU-bound for latency)
            with torch.no_grad():
                if torch.cuda.is_available():
                    input_tensor = input_tensor.to(f"cuda:{gpu_id}")

                # Forward pass
                output = model(input_tensor)

            # Postprocess
            prediction = self._postprocess(output, model_id)

            logger.debug(f"Inference for {model_id} completed")
            return prediction

        except Exception as e:
            logger.error(f"Inference failed for {model_id}: {e}", exc_info=True)
            raise

    def predict_sync(
        self, model: torch.nn.Module, input_data: Dict[str, Any], model_id: str, gpu_id: int
    ) -> Any:
        """
        Run synchronous inference (blocking)

        Args:
            model: Loaded PyTorch model
            input_data: Input data dictionary
            model_id: Model identifier
            gpu_id: GPU device ID

        Returns:
            Model prediction
        """
        try:
            # Preprocess
            input_tensor = self._preprocess(input_data, model_id)

            # Run inference
            with torch.no_grad():
                if torch.cuda.is_available():
                    input_tensor = input_tensor.to(f"cuda:{gpu_id}")

                output = model(input_tensor)

            # Postprocess
            prediction = self._postprocess(output, model_id)
            return prediction

        except Exception as e:
            logger.error(f"Inference failed for {model_id}: {e}", exc_info=True)
            raise

    async def predict_batch(
        self,
        model: torch.nn.Module,
        batch_data: List[Dict[str, Any]],
        model_id: str,
        gpu_id: int,
        batch_size: int = 32,
    ) -> List[Any]:
        """
        Batch inference for multiple inputs (async)

        More efficient than calling predict() multiple times because:
        - Single GPU transfer
        - Vectorized operations
        - Better GPU utilization

        Args:
            model: Loaded PyTorch model
            batch_data: List of input data dictionaries
            model_id: Model identifier
            gpu_id: GPU device ID
            batch_size: Process this many at once

        Returns:
            List of predictions
        """
        predictions = []

        try:
            # Process in chunks
            for i in range(0, len(batch_data), batch_size):
                chunk = batch_data[i : i + batch_size]

                # Preprocess each item
                batch_tensors = [self._preprocess(data, model_id) for data in chunk]

                # Stack into single batch tensor
                try:
                    batch_tensor = torch.cat(batch_tensors, dim=0)
                except RuntimeError:
                    # If tensors have different shapes, stack dimension 0
                    batch_tensor = torch.stack(batch_tensors)

                # Run batch inference in async context
                loop = asyncio.get_event_loop()
                batch_output = await loop.run_in_executor(
                    None, self._run_batch_inference, model, batch_tensor, gpu_id
                )

                # Postprocess each output
                for j in range(len(chunk)):
                    # Extract single output
                    if batch_output.dim() > 1:
                        output = batch_output[j : j + 1]
                    else:
                        output = batch_output[j]

                    prediction = self._postprocess(output, model_id)
                    predictions.append(prediction)

            logger.debug(f"Batch inference for {model_id} " f"completed ({len(batch_data)} items)")
            return predictions

        except Exception as e:
            logger.error(f"Batch inference failed for {model_id}: {e}", exc_info=True)
            raise

    def _run_batch_inference(
        self, model: torch.nn.Module, batch_tensor: torch.Tensor, gpu_id: int
    ) -> torch.Tensor:
        """
        Synchronous batch inference (runs in executor)

        Separated to run in thread pool without blocking event loop.
        """
        with torch.no_grad():
            if torch.cuda.is_available():
                batch_tensor = batch_tensor.to(f"cuda:{gpu_id}")

            batch_output = model(batch_tensor)

        return batch_output

    def _preprocess(self, input_data: Dict[str, Any], model_id: str) -> torch.Tensor:
        """
        Preprocess input data

        If custom preprocessor registered, use it.
        Otherwise, use default preprocessing.

        Args:
            input_data: Input data dictionary
            model_id: Model identifier

        Returns:
            Preprocessed torch.Tensor
        """
        if model_id in self.preprocessors:
            return self.preprocessors[model_id](input_data)

        return self._default_preprocess(input_data)

    def _default_preprocess(self, input_data: Dict[str, Any]) -> torch.Tensor:
        """
        Default preprocessing

        Expects input_data['data'] containing:
        - List/array of numbers
        - Or nested lists (for images, sequences)

        Args:
            input_data: Input data dictionary

        Returns:
            Preprocessed tensor (batch_size, ...)
        """
        if "data" not in input_data:
            raise ValueError("Input must contain 'data' key")

        data = input_data["data"]

        # Convert to tensor
        if isinstance(data, (list, np.ndarray)):
            tensor = torch.tensor(data, dtype=torch.float32)
        elif isinstance(data, torch.Tensor):
            tensor = data.float()
        else:
            raise ValueError(f"Unsupported data type: {type(data)}")

        # Add batch dimension if needed
        if tensor.dim() == 1:
            tensor = tensor.unsqueeze(0)  # (N,) → (1, N)

        return tensor

    def _postprocess(self, output: torch.Tensor, model_id: str) -> Any:
        """
        Postprocess model output

        If custom postprocessor registered, use it.
        Otherwise, use default postprocessing.

        Args:
            output: Model output tensor
            model_id: Model identifier

        Returns:
            Postprocessed output (typically list or dict)
        """
        if model_id in self.postprocessors:
            return self.postprocessors[model_id](output)

        return self._default_postprocess(output)

    def _default_postprocess(self, output: torch.Tensor) -> Any:
        """
        Default postprocessing

        Converts tensor to list/dict for JSON serialization

        Args:
            output: Model output tensor

        Returns:
            JSON-serializable output
        """
        # Move to CPU if on GPU
        if output.is_cuda:
            output = output.cpu()

        # Detach from computation graph
        output_np = output.detach().numpy()

        # If single sample batch, remove batch dimension
        if output_np.ndim > 1 and output_np.shape[0] == 1:
            output_np = output_np[0]

        # Convert to list
        return output_np.tolist()

    def get_model_device(self, model: torch.nn.Module) -> str:
        """Get the device a model is on"""
        try:
            return next(model.parameters()).device
        except StopIteration:
            return "cpu"

    def estimate_batch_time_ms(self, batch_size: int, gpu_id: int) -> float:
        """Estimate inference time for batch (rough estimate)"""
        # Rough: ~1ms per 32 items on modern GPU
        return (batch_size / 32.0) * 1.0
