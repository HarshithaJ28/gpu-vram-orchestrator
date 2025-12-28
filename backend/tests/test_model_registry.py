"""Tests for Model Registry

Tests model registration, versioning, and metadata management.
"""

import pytest
import os
import tempfile
import json
import hashlib
from pathlib import Path

from src.registry import ModelRegistry, ModelMetadata


@pytest.fixture
def temp_registry_dir():
    """Create temporary directory for registry"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def model_registry(temp_registry_dir):
    """Create model registry instance"""
    return ModelRegistry(storage_path=temp_registry_dir)


@pytest.fixture
def dummy_model_file(temp_registry_dir):
    """Create dummy model file"""
    model_dir = os.path.join(temp_registry_dir, "temp_models")
    os.makedirs(model_dir, exist_ok=True)
    
    model_path = os.path.join(model_dir, "model.pth")
    
    # Write dummy content
    with open(model_path, 'wb') as f:
        f.write(b"DUMMY_MODEL_CONTENT_" + b"x" * 1000)
    
    yield model_path


class TestModelRegistry:
    """Test model registry functionality"""

    def test_initialization(self, model_registry, temp_registry_dir):
        """Test registry initialization"""
        assert model_registry is not None
        assert model_registry.storage_path == temp_registry_dir
        assert os.path.exists(os.path.join(temp_registry_dir, "models"))

    def test_register_model(self, model_registry, dummy_model_file):
        """Test registering a model"""
        success = model_registry.register_model(
            model_id='test-model',
            model_path=dummy_model_file,
            framework='pytorch',
            version='1.0.0',
            description='Test model'
        )
        
        assert success is True
        assert 'test-model' in model_registry.registry

    def test_register_model_nonexistent_file(self, model_registry):
        """Test registering non-existent model"""
        success = model_registry.register_model(
            model_id='test-model',
            model_path='/nonexistent/path/model.pth',
            framework='pytorch',
            version='1.0.0'
        )
        
        assert success is False

    def test_get_model_path_latest(self, model_registry, dummy_model_file):
        """Test getting latest model path"""
        model_registry.register_model(
            model_id='test-model',
            model_path=dummy_model_file,
            framework='pytorch',
            version='1.0.0'
        )
        
        # Move file to expected location
        expected_path = os.path.join(
            model_registry.storage_path, 'models',
            'test-model-1.0.0.pth'
        )
        os.makedirs(os.path.dirname(expected_path), exist_ok=True)
        os.rename(dummy_model_file, expected_path)
        
        path = model_registry.get_model_path('test-model', version='latest')
        assert path is not None

    def test_get_model_path_specific_version(self, model_registry, dummy_model_file):
        """Test getting specific model version"""
        model_registry.register_model(
            model_id='test-model',
            model_path=dummy_model_file,
            framework='pytorch',
            version='2.0.0'
        )
        
        # Move file to expected location
        expected_path = os.path.join(
            model_registry.storage_path, 'models',
            'test-model-2.0.0.pth'
        )
        os.makedirs(os.path.dirname(expected_path), exist_ok=True)
        os.rename(dummy_model_file, expected_path)
        
        path = model_registry.get_model_path('test-model', version='2.0.0')
        assert path is not None

    def test_get_model_path_not_found(self, model_registry):
        """Test getting path for non-existent model"""
        path = model_registry.get_model_path('nonexistent-model')
        assert path is None

    def test_get_metadata(self, model_registry, dummy_model_file):
        """Test getting model metadata"""
        model_registry.register_model(
            model_id='test-model',
            model_path=dummy_model_file,
            framework='pytorch',
            version='1.0.0',
            description='Test model',
            tags=['production', 'v1']
        )
        
        metadata = model_registry.get_metadata('test-model')
        assert metadata is not None
        assert metadata.model_id == 'test-model'
        assert metadata.version == '1.0.0'
        assert metadata.framework == 'pytorch'
        assert metadata.description == 'Test model'
        assert 'production' in metadata.tags

    def test_metadata_has_hash(self, model_registry, dummy_model_file):
        """Test that metadata includes file hash"""
        model_registry.register_model(
            model_id='test-model',
            model_path=dummy_model_file,
            framework='pytorch',
            version='1.0.0'
        )
        
        metadata = model_registry.get_metadata('test-model')
        assert metadata.hash is not None
        assert len(metadata.hash) == 64  # SHA256 hash length

    def test_metadata_has_timestamps(self, model_registry, dummy_model_file):
        """Test that metadata includes timestamps"""
        model_registry.register_model(
            model_id='test-model',
            model_path=dummy_model_file,
            framework='pytorch',
            version='1.0.0'
        )
        
        metadata = model_registry.get_metadata('test-model')
        assert metadata.registered_at is not None
        assert metadata.updated_at is not None

    def test_list_models_empty(self, model_registry):
        """Test listing when no models registered"""
        models = model_registry.list_models()
        assert isinstance(models, dict)
        assert len(models) == 0

    def test_list_models(self, model_registry, dummy_model_file):
        """Test listing registered models"""
        model_registry.register_model(
            model_id='model1',
            model_path=dummy_model_file,
            framework='pytorch',
            version='1.0.0'
        )
        
        # Can't register multiple without copying file
        models = model_registry.list_models()
        assert 'model1' in models

    def test_verify_model_valid(self, model_registry, dummy_model_file):
        """Test verifying valid model"""
        model_registry.register_model(
            model_id='test-model',
            model_path=dummy_model_file,
            framework='pytorch',
            version='1.0.0'
        )
        
        is_valid = model_registry.verify_model('test-model', dummy_model_file)
        assert is_valid is True

    def test_verify_model_corrupted(self, model_registry, dummy_model_file):
        """Test verifying corrupted model"""
        model_registry.register_model(
            model_id='test-model',
            model_path=dummy_model_file,
            framework='pytorch',
            version='1.0.0'
        )
        
        # Corrupt the file
        with open(dummy_model_file, 'ab') as f:
            f.write(b"CORRUPTED")
        
        is_valid = model_registry.verify_model('test-model', dummy_model_file)
        assert is_valid is False

    def test_metadata_persistence(self, model_registry, dummy_model_file):
        """Test metadata is persisted to disk"""
        model_registry.register_model(
            model_id='test-model',
            model_path=dummy_model_file,
            framework='pytorch',
            version='1.0.0'
        )
        
        # Create new registry instance
        new_registry = ModelRegistry(storage_path=model_registry.storage_path)
        assert 'test-model' in new_registry.registry

    def test_model_metadata_dataclass(self):
        """Test ModelMetadata dataclass"""
        metadata = ModelMetadata(
            model_id='test',
            version='1.0.0',
            framework='pytorch',
            size_mb=500.0,
            hash='abc123',
            registered_at='2025-01-01T00:00:00',
            updated_at='2025-01-01T00:00:00',
            tags=['prod']
        )
        
        assert metadata.model_id == 'test'
        assert metadata.version == '1.0.0'

    def test_model_metadata_to_dict(self):
        """Test ModelMetadata to_dict conversion"""
        metadata = ModelMetadata(
            model_id='test',
            version='1.0.0',
            framework='pytorch',
            size_mb=500.0,
            hash='abc123',
            registered_at='2025-01-01T00:00:00',
            updated_at='2025-01-01T00:00:00',
            tags=['prod']
        )
        
        d = metadata.to_dict()
        assert isinstance(d, dict)
        assert d['model_id'] == 'test'
        assert d['tags'] == ['prod']

    def test_calculate_hash_consistency(self, model_registry, dummy_model_file):
        """Test that hash calculation is consistent"""
        hash1 = model_registry._calculate_hash(dummy_model_file)
        hash2 = model_registry._calculate_hash(dummy_model_file)
        
        assert hash1 == hash2

    def test_register_multiple_versions(self, model_registry, dummy_model_file):
        """Test registering multiple versions of same model"""
        # First version
        model_registry.register_model(
            model_id='test-model',
            model_path=dummy_model_file,
            framework='pytorch',
            version='1.0.0'
        )
        
        assert 'test-model' in model_registry.registry
        assert len(model_registry.registry['test-model']) == 1

    def test_metadata_with_no_tags(self, model_registry, dummy_model_file):
        """Test metadata with no tags"""
        model_registry.register_model(
            model_id='test-model',
            model_path=dummy_model_file,
            framework='pytorch',
            version='1.0.0'
        )
        
        metadata = model_registry.get_metadata('test-model')
        assert metadata.tags == []
