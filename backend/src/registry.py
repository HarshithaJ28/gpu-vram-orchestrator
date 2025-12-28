"""Model Registry Module

Manages model storage, versioning, and metadata.
"""

import os
import json
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class ModelMetadata:
    """Metadata for a registered model"""
    model_id: str
    version: str
    framework: str  # 'pytorch', 'tensorflow', etc.
    size_mb: float
    hash: str  # File hash for integrity
    registered_at: str
    updated_at: str
    description: str = ""
    tags: List[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        d = asdict(self)
        if self.tags is None:
            d['tags'] = []
        return d


class ModelRegistry:
    """
    Manages model storage and metadata

    Responsibilities:
    - Track model files and versions
    - Store/retrieve model metadata
    - Calculate and verify file hashes
    """

    def __init__(self, storage_path: str = "./models"):
        """
        Initialize registry

        Args:
            storage_path: Directory to store models
        """
        self.storage_path = storage_path
        self.metadata_file = os.path.join(storage_path, "registry.json")

        # Create directory if needed
        os.makedirs(storage_path, exist_ok=True)
        os.makedirs(os.path.join(storage_path, "models"), exist_ok=True)

        # Load existing registry
        self.registry: Dict[str, List[ModelMetadata]] = self._load_registry()

        logger.info(f"ModelRegistry initialized at {storage_path}")

    def register_model(
        self,
        model_id: str,
        model_path: str,
        framework: str,
        version: str,
        description: str = "",
        tags: List[str] = None
    ) -> bool:
        """
        Register a model

        Args:
            model_id: Unique model identifier
            model_path: Path to model file
            framework: Framework used ('pytorch', 'tensorflow')
            version: Model version string
            description: Optional description
            tags: Optional list of tags

        Returns:
            True if successful
        """
        if not os.path.exists(model_path):
            logger.error(f"Model file not found: {model_path}")
            return False

        try:
            # Calculate file hash
            file_hash = self._calculate_hash(model_path)

            # Get file size
            size_mb = os.path.getsize(model_path) / (1024 * 1024)

            # Create metadata
            metadata = ModelMetadata(
                model_id=model_id,
                version=version,
                framework=framework,
                size_mb=size_mb,
                hash=file_hash,
                registered_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                description=description,
                tags=tags or []
            )

            # Store in registry
            if model_id not in self.registry:
                self.registry[model_id] = []

            self.registry[model_id].append(metadata)

            # Persist
            self._save_registry()

            logger.info(
                f"Registered {model_id} v{version} ({size_mb:.1f}MB) "
                f"from {os.path.basename(model_path)}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to register {model_id}: {e}")
            return False

    def get_model_path(self, model_id: str, version: str = "latest") -> Optional[str]:
        """
        Get path to model file

        Args:
            model_id: Model identifier
            version: Version to fetch ('latest' or specific version string)

        Returns:
            Path to model file or None if not found
        """
        if model_id not in self.registry:
            logger.warning(f"Model {model_id} not registered")
            return None

        versions = self.registry[model_id]
        if not versions:
            return None

        # Get specified version
        if version == "latest":
            metadata = versions[-1]  # Last registered = newest
        else:
            metadata = next((m for m in versions if m.version == version), None)
            if metadata is None:
                logger.warning(f"Version {version} not found for {model_id}")
                return None

        # Construct path
        model_file = f"{model_id}-{metadata.version}.pth"
        model_path = os.path.join(self.storage_path, "models", model_file)

        if not os.path.exists(model_path):
            logger.warning(f"Model file not found: {model_path}")
            return None

        return model_path

    def get_metadata(self, model_id: str, version: str = "latest") -> Optional[ModelMetadata]:
        """
        Get model metadata

        Args:
            model_id: Model identifier
            version: Version ('latest' or specific)

        Returns:
            ModelMetadata or None
        """
        if model_id not in self.registry:
            return None

        versions = self.registry[model_id]
        if not versions:
            return None

        if version == "latest":
            return versions[-1]
        else:
            return next((m for m in versions if m.version == version), None)

    def list_models(self) -> Dict[str, List[Dict]]:
        """
        List all registered models

        Returns:
            Dict mapping model_id to list of versions
        """
        result = {}
        for model_id, versions in self.registry.items():
            result[model_id] = [
                {
                    'version': v.version,
                    'size_mb': v.size_mb,
                    'registered_at': v.registered_at,
                    'tags': v.tags,
                    'description': v.description
                }
                for v in versions
            ]
        return result

    def verify_model(self, model_id: str, model_path: str) -> bool:
        """
        Verify model file integrity

        Args:
            model_id: Model identifier
            model_path: Path to model file

        Returns:
            True if hash matches
        """
        metadata = self.get_metadata(model_id)
        if metadata is None:
            logger.warning(f"No metadata for {model_id}")
            return False

        actual_hash = self._calculate_hash(model_path)
        if actual_hash != metadata.hash:
            logger.warning(f"Hash mismatch for {model_id}")
            return False

        return True

    def _calculate_hash(self, filepath: str) -> str:
        """Calculate SHA256 hash of file"""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _load_registry(self) -> Dict:
        """Load registry from disk"""
        if not os.path.exists(self.metadata_file):
            return {}

        try:
            with open(self.metadata_file, 'r') as f:
                data = json.load(f)

            # Reconstruct ModelMetadata objects
            registry = {}
            for model_id, versions in data.items():
                registry[model_id] = [
                    ModelMetadata(**v) for v in versions
                ]
            return registry
        except Exception as e:
            logger.warning(f"Error loading registry: {e}")
            return {}

    def _save_registry(self):
        """Save registry to disk"""
        try:
            data = {}
            for model_id, versions in self.registry.items():
                data[model_id] = [v.to_dict() for v in versions]

            with open(self.metadata_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving registry: {e}")
