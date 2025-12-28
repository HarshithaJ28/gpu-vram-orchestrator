"""Tests for Inference Engine

Tests the core inference pipeline with preprocessing, inference, and postprocessing.
"""

import pytest
import torch
import numpy as np
from typing import Dict, Any
import asyncio

from src.inference.engine import InferenceEngine, InferenceResult


@pytest.fixture
def inference_engine():
    """Create inference engine instance"""
    return InferenceEngine()


@pytest.fixture
def dummy_model():
    """Create simple PyTorch model for testing"""
    model = torch.nn.Sequential(
        torch.nn.Linear(10, 5),
        torch.nn.ReLU(),
        torch.nn.Linear(5, 1)
    )
    model.eval()
    return model


class TestInferenceEngine:
    """Test inference engine functionality"""

    def test_initialization(self, inference_engine):
        """Test engine initialization"""
        assert inference_engine is not None
        assert isinstance(inference_engine.preprocessors, dict)
        assert isinstance(inference_engine.postprocessors, dict)

    def test_default_preprocessing_1d(self, inference_engine):
        """Test default preprocessing with 1D data"""
        input_data = {'data': [1.0, 2.0, 3.0, 4.0, 5.0]}
        tensor = inference_engine._default_preprocess(input_data)
        
        assert isinstance(tensor, torch.Tensor)
        assert tensor.dim() == 2  # Should have batch dimension
        assert tensor.shape[0] == 1
        assert tensor.dtype == torch.float32

    def test_default_preprocessing_2d(self, inference_engine):
        """Test preprocessing with 2D data"""
        input_data = {'data': [[1.0, 2.0], [3.0, 4.0]]}
        tensor = inference_engine._default_preprocess(input_data)
        
        assert tensor.dim() == 2
        assert tensor.shape[0] == 2

    def test_preprocessing_numpy_array(self, inference_engine):
        """Test preprocessing with numpy array"""
        input_data = {'data': np.array([1.0, 2.0, 3.0])}
        tensor = inference_engine._default_preprocess(input_data)
        
        assert isinstance(tensor, torch.Tensor)

    def test_preprocessing_tensor(self, inference_engine):
        """Test preprocessing with torch tensor"""
        input_data = {'data': torch.tensor([1.0, 2.0, 3.0])}
        tensor = inference_engine._default_preprocess(input_data)
        
        assert isinstance(tensor, torch.Tensor)

    def test_preprocessing_missing_data_key(self, inference_engine):
        """Test preprocessing with missing 'data' key"""
        with pytest.raises(ValueError):
            inference_engine._default_preprocess({'input': [1, 2, 3]})

    def test_custom_preprocessor(self, inference_engine):
        """Test registering custom preprocessor"""
        def custom_preprocess(data):
            return torch.tensor([[99.0]])
        
        inference_engine.register_preprocessor('model_1', custom_preprocess)
        assert 'model_1' in inference_engine.preprocessors
        
        result = inference_engine._preprocess({}, 'model_1')
        assert result[0][0].item() == 99.0

    def test_default_postprocessing_single(self, inference_engine):
        """Test default postprocessing with single sample"""
        output = torch.tensor([[0.5, 0.3, 0.2]])  # Batch size 1
        result = inference_engine._default_postprocess(output)
        
        assert isinstance(result, list)
        assert len(result) == 3

    def test_default_postprocessing_batch(self, inference_engine):
        """Test default postprocessing with batch"""
        output = torch.tensor([[0.5, 0.3], [0.2, 0.8]])  # Batch size 2
        result = inference_engine._default_postprocess(output)
        
        assert isinstance(result, list)
        assert len(result) == 2

    def test_custom_postprocessor(self, inference_engine):
        """Test registering custom postprocessor"""
        def custom_postprocess(tensor):
            return "custom_result"
        
        inference_engine.register_postprocessor('model_2', custom_postprocess)
        assert 'model_2' in inference_engine.postprocessors
        
        result = inference_engine._postprocess(torch.tensor([1.0]), 'model_2')
        assert result == "custom_result"

    @pytest.mark.asyncio
    async def test_predict_sync(self, inference_engine, dummy_model):
        """Test synchronous prediction"""
        input_data = {'data': [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]}
        
        result = inference_engine.predict_sync(
            model=dummy_model,
            input_data=input_data,
            model_id='test-model',
            gpu_id=0
        )
        
        assert isinstance(result, (list, float, int))

    @pytest.mark.asyncio
    async def test_predict_async(self, inference_engine, dummy_model):
        """Test asynchronous prediction"""
        input_data = {'data': [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]}
        
        result = await inference_engine.predict(
            model=dummy_model,
            input_data=input_data,
            model_id='test-model',
            gpu_id=0
        )
        
        assert isinstance(result, (list, float, int))

    def test_predict_batch(self, inference_engine, dummy_model):
        """Test batch prediction"""
        batch_data = [
            {'data': [float(i) for i in range(1, 11)]}
            for _ in range(5)
        ]
        
        results = inference_engine.predict_batch(
            model=dummy_model,
            batch_data=batch_data,
            model_id='test-model',
            gpu_id=0,
            batch_size=2
        )
        
        assert len(results) == 5
        assert all(isinstance(r, (list, float, int)) for r in results)

    def test_predict_batch_chunk_processing(self, inference_engine, dummy_model):
        """Test batch prediction with chunking"""
        # Create batch larger than chunk size
        batch_data = [
            {'data': [float(i) for i in range(1, 11)]}
            for _ in range(7)
        ]
        
        results = inference_engine.predict_batch(
            model=dummy_model,
            batch_data=batch_data,
            model_id='test-model',
            gpu_id=0,
            batch_size=3
        )
        
        assert len(results) == 7

    def test_estimate_batch_time(self, inference_engine):
        """Test batch time estimation"""
        time_ms = inference_engine.estimate_batch_time_ms(batch_size=64, gpu_id=0)
        
        assert isinstance(time_ms, float)
        assert time_ms > 0

    def test_get_model_device_cpu(self, inference_engine):
        """Test getting device for CPU model"""
        model = torch.nn.Linear(10, 5)
        device = inference_engine.get_model_device(model)
        
        assert 'cpu' in str(device)

    @pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")
    def test_get_model_device_cuda(self, inference_engine):
        """Test getting device for CUDA model"""
        model = torch.nn.Linear(10, 5).cuda()
        device = inference_engine.get_model_device(model)
        
        assert 'cuda' in str(device)


class TestInferenceResult:
    """Test InferenceResult dataclass"""

    def test_result_creation(self):
        """Test creating inference result"""
        result = InferenceResult(
            prediction=[0.5, 0.3, 0.2],
            latency_ms=10.5,
            gpu_id=0,
            model_id='test-model',
            cached=True,
            batch_size=1
        )
        
        assert result.prediction == [0.5, 0.3, 0.2]
        assert result.latency_ms == 10.5
        assert result.cached is True

    def test_result_defaults(self):
        """Test result default values"""
        result = InferenceResult(
            prediction=0.5,
            latency_ms=5.0,
            gpu_id=0,
            model_id='test',
            cached=False
        )
        
        assert result.batch_size == 1  # Default


class TestPreprocessingEdgeCases:
    """Test preprocessing edge cases"""

    def test_empty_list(self):
        """Test preprocessing empty list"""
        engine = InferenceEngine()
        input_data = {'data': []}
        
        # Empty list might be valid depending on use case
        tensor = engine._default_preprocess(input_data)
        assert isinstance(tensor, torch.Tensor)

    def test_large_batch(self):
        """Test preprocessing large batch"""
        engine = InferenceEngine()
        large_batch = [[float(i) for i in range(100)] for _ in range(1000)]
        input_data = {'data': large_batch}
        
        tensor = engine._default_preprocess(input_data)
        assert tensor.shape[0] == 1000

    def test_mixed_numeric_types(self):
        """Test preprocessing with mixed int/float"""
        engine = InferenceEngine()
        input_data = {'data': [1, 2.5, 3, 4.5]}
        
        tensor = engine._default_preprocess(input_data)
        assert tensor.dtype == torch.float32
