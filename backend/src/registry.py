"""Model Registry Module

Complete model storage system with versioning, metadata management, and integrity checking.
"""

import os
import json
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class ModelMetadata:
    """Metadata for a registered model"""
    model_id: str
    version: str
    framework: str  # 'pytorch', 'tensorflow', etc.
    task_type: str  # 'classification', 'regression', etc.
    model_path: str
    config_path: Optional[str] = None
    size_mb: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    checksum: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)


class ModelRegistry:
    """
    Model registry with local file storage and versioning.
    
    Features:
    - Model versioning
    - Metadata management
    - Model upload/download
    - Search and filtering
    - Automatic checksums
    - File integrity verification
    
    Storage structure:
    ./models/
      ├── metadata.json          # All model metadata
      ├── model-id-v1/
      │   ├── model.pth          # Model weights
      │   ├── config.json        # Model config
      │   └── checksum.txt       # File checksum
      ├── model-id-v2/
      │   └── ...
    """
    
    def __init__(self, storage_path: str = "./models"):
        self.storage_path = Path(storage_path)
        self.metadata_file = self.storage_path / "metadata.json"
        
        # Create storage directory
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Load existing metadata
        self.metadata: Dict[str, ModelMetadata] = self._load_metadata()
        
        logger.info(f"Model registry initialized at {self.storage_path}")
        logger.info(f"Loaded {len(self.metadata)} models")

    def register_model(
        self,
        model_id: str,
        model_path: str,
        version: str = "v1",
        framework: str = "pytorch",
        task_type: str = "classification",
        config_path: Optional[str] = None,
        description: str = "",
        tags: Optional[List[str]] = None,
        metrics: Optional[Dict[str, float]] = None,
        overwrite: bool = False
    ) -> ModelMetadata:
        """
        Register a new model.
        
        Args:
            model_id: Unique model identifier
            model_path: Path to model file (local)
            version: Model version (e.g., 'v1', 'v2')
            framework: ML framework used (pytorch, tensorflow, etc.)
            task_type: Type of task (classification, regression, etc.)
            config_path: Optional config file path
            description: Model description
            tags: Tags for categorization
            metrics: Performance metrics
            overwrite: Whether to overwrite existing model
        
        Returns:
            ModelMetadata object
        
        Raises:
            ValueError: If model exists and overwrite=False
            FileNotFoundError: If model file doesn't exist
        """
        full_model_id = f"{model_id}-{version}"
        
        # Check if exists
        if full_model_id in self.metadata and not overwrite:
            raise ValueError(
                f"Model {full_model_id} already exists. Use overwrite=True to replace."
            )
        
        # Validate source file exists
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        # Create model directory
        model_dir = self.storage_path / full_model_id
        model_dir.mkdir(exist_ok=True)
        
        # Copy model file
        dest_model_path = model_dir / "model.pth"
        shutil.copy2(model_path, dest_model_path)
        logger.info(f"Copied model to {dest_model_path}")
        
        # Copy config if provided
        dest_config_path = None
        if config_path and os.path.exists(config_path):
            dest_config_path = model_dir / "config.json"
            shutil.copy2(config_path, dest_config_path)
            dest_config_path = str(dest_config_path)
            logger.info(f"Copied config to {dest_config_path}")
        
        # Calculate file size
        size_mb = os.path.getsize(dest_model_path) / (1024 * 1024)
        
        # Calculate checksum
        checksum = self._calculate_checksum(dest_model_path)
        checksum_file = model_dir / "checksum.txt"
        checksum_file.write_text(checksum)
        logger.info(f"Checksum: {checksum[:16]}...")
        
        # Create metadata
        metadata = ModelMetadata(
            model_id=model_id,
            version=version,
            framework=framework,
            task_type=task_type,
            model_path=str(dest_model_path),
            config_path=dest_config_path,
            size_mb=size_mb,
            description=description,
            tags=tags or [],
            metrics=metrics or {},
            checksum=checksum
        )
        
        # Save metadata
        self.metadata[full_model_id] = metadata
        self._save_metadata()
        
        logger.info(f"Registered model {full_model_id} ({size_mb:.2f} MB)")
        return metadata

    def get_model_path(self, model_id: str) -> Optional[str]:
        """
        Get path to model file.
        
        Args:
            model_id: Full model ID (e.g., 'fraud-detection-v3')
        
        Returns:
            Path to model file, or None if not found
        """
        if model_id not in self.metadata:
            logger.warning(f"Model {model_id} not found in registry")
            return None
        
        model_path = self.metadata[model_id].model_path
        
        if not os.path.exists(model_path):
            logger.error(f"Model file not found: {model_path}")
            return None
        
        return model_path
    
    def get_model_metadata(self, model_id: str) -> Optional[ModelMetadata]:
        """Get metadata for a model"""
        return self.metadata.get(model_id)
    
    def list_models(
        self,
        framework: Optional[str] = None,
        task_type: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        List models with optional filtering.
        
        Args:
            framework: Filter by framework
            task_type: Filter by task type
            tags: Filter by tags (must have all tags)
        
        Returns:
            List of model metadata dicts
        """
        models = list(self.metadata.values())
        
        # Filter by framework
        if framework:
            models = [m for m in models if m.framework == framework]
        
        # Filter by task type
        if task_type:
            models = [m for m in models if m.task_type == task_type]
        
        # Filter by tags
        if tags:
            models = [
                m for m in models
                if all(tag in m.tags for tag in tags)
            ]
        
        return [m.to_dict() for m in models]
    
    def search_models(self, query: str) -> List[Dict]:
        """
        Search models by query string.
        
        Searches in:
        - model_id
        - description
        - tags
        """
        query_lower = query.lower()
        results = []
        
        for metadata in self.metadata.values():
            # Search in model_id
            if query_lower in metadata.model_id.lower():
                results.append(metadata)
                continue
            
            # Search in description
            if query_lower in metadata.description.lower():
                results.append(metadata)
                continue
            
            # Search in tags
            if any(query_lower in tag.lower() for tag in metadata.tags):
                results.append(metadata)
                continue
        
        return [m.to_dict() for m in results]
    
    def delete_model(self, model_id: str) -> bool:
        """
        Delete a model from registry.
        
        Args:
            model_id: Full model ID
        
        Returns:
            True if deleted, False otherwise
        """
        if model_id not in self.metadata:
            logger.warning(f"Model {model_id} not found")
            return False
        
        # Get model directory
        model_dir = self.storage_path / model_id
        
        # Delete directory
        if model_dir.exists():
            shutil.rmtree(model_dir)
            logger.info(f"Deleted model directory: {model_dir}")
        
        # Remove from metadata
        del self.metadata[model_id]
        self._save_metadata()
        
        logger.info(f"Deleted model {model_id}")
        return True
    
    def update_metadata(
        self,
        model_id: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metrics: Optional[Dict[str, float]] = None
    ) -> Optional[ModelMetadata]:
        """
        Update model metadata.
        
        Args:
            model_id: Full model ID
            description: New description
            tags: New tags
            metrics: New metrics
        
        Returns:
            Updated metadata, or None if not found
        """
        if model_id not in self.metadata:
            logger.warning(f"Model {model_id} not found")
            return None
        
        metadata = self.metadata[model_id]
        
        if description is not None:
            metadata.description = description
        
        if tags is not None:
            metadata.tags = tags
        
        if metrics is not None:
            metadata.metrics = metrics
        
        metadata.updated_at = datetime.now().isoformat()
        
        self._save_metadata()
        
        logger.info(f"Updated metadata for {model_id}")
        return metadata
    
    def verify_model(self, model_id: str) -> bool:
        """
        Verify model file integrity using checksum.
        
        Returns:
            True if valid, False otherwise
        """
        if model_id not in self.metadata:
            logger.warning(f"Model {model_id} not found")
            return False
        
        metadata = self.metadata[model_id]
        model_path = metadata.model_path
        
        if not os.path.exists(model_path):
            logger.error(f"Model file not found: {model_path}")
            return False
        
        stored_checksum = metadata.checksum
        current_checksum = self._calculate_checksum(model_path)
        
        is_valid = stored_checksum == current_checksum
        
        if not is_valid:
            logger.error(f"Checksum mismatch for {model_id}!")
            logger.error(f"  Expected: {stored_checksum}")
            logger.error(f"  Got: {current_checksum}")
        else:
            logger.debug(f"Model {model_id} verified: {stored_checksum[:16]}...")
        
        return is_valid
    
    def get_stats(self) -> Dict:
        """Get registry statistics"""
        total_models = len(self.metadata)
        total_size_mb = sum(m.size_mb for m in self.metadata.values())
        
        # Count by framework
        frameworks: Dict[str, int] = {}
        for m in self.metadata.values():
            frameworks[m.framework] = frameworks.get(m.framework, 0) + 1
        
        # Count by task type
        task_types: Dict[str, int] = {}
        for m in self.metadata.values():
            task_types[m.task_type] = task_types.get(m.task_type, 0) + 1
        
        return {
            'total_models': total_models,
            'total_size_mb': total_size_mb,
            'frameworks': frameworks,
            'task_types': task_types,
            'storage_path': str(self.storage_path)
        }
    
    def _load_metadata(self) -> Dict[str, ModelMetadata]:
        """Load metadata from file"""
        if not self.metadata_file.exists():
            logger.info("No existing metadata file")
            return {}
        
        try:
            with open(self.metadata_file, 'r') as f:
                data = json.load(f)
            
            # Convert dicts to ModelMetadata objects
            metadata = {}
            for model_id, model_data in data.items():
                metadata[model_id] = ModelMetadata(**model_data)
            
            logger.info(f"Loaded metadata for {len(metadata)} models")
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            return {}
    
    def _save_metadata(self):
        """Save metadata to file"""
        try:
            # Convert ModelMetadata objects to dicts
            data = {}
            for model_id, metadata in self.metadata.items():
                data[model_id] = asdict(metadata)
            
            # Write to file
            with open(self.metadata_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Saved metadata to {self.metadata_file}")
            
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
    
    def _calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of file"""
        sha256 = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        
        return sha256.hexdigest()
