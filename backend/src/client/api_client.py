"""GPU VRAM Orchestrator Python Client

Simple client for interacting with the GPU VRAM Orchestrator API.
"""

import requests
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class GPUOrchestratorClient:
    """Client for GPU VRAM Orchestrator API"""

    def __init__(self, base_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        """
        Initialize client

        Args:
            base_url: Base URL of the orchestrator API
            api_key: Optional API key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self._setup_headers()

    def _setup_headers(self):
        """Setup default headers"""
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'GPUOrchestratorClient/1.0'
        })
        if self.api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {self.api_key}'
            })

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """
        Make HTTP request to API

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments to pass to requests

        Returns:
            Response JSON dictionary

        Raises:
            requests.exceptions.RequestException: On network error
            ValueError: On invalid response
        """
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise

    # Health & Status

    def health(self) -> Dict:
        """Check API health"""
        return self._make_request('GET', '/health')

    def status(self) -> Dict:
        """Get complete system status"""
        return self._make_request('GET', '/status')

    # Predictions

    def predict(self, model_id: str, input_data: Dict, **kwargs) -> Dict:
        """
        Run inference on a model

        Args:
            model_id: Model identifier
            input_data: Input features/data
            **kwargs: Additional parameters (batch_size, return_timing, etc.)

        Returns:
            Prediction result with GPU info and timing
        """
        payload = {
            'model_id': model_id,
            'input_data': input_data,
            **kwargs
        }
        return self._make_request('POST', '/predict', json=payload)

    def predict_batch(self, model_id: str, samples: List[Dict], **kwargs) -> Dict:
        """
        Run batch inference

        Args:
            model_id: Model identifier
            samples: List of input samples
            **kwargs: Additional parameters

        Returns:
            Batch prediction results
        """
        payload = {
            'model_id': model_id,
            'samples': samples,
            **kwargs
        }
        return self._make_request('POST', '/predict/batch', json=payload)

    # Model Management

    def list_models(self, status: Optional[str] = None, gpu_id: Optional[int] = None) -> Dict:
        """
        List all available models

        Args:
            status: Optional status filter (loaded, available, unavailable)
            gpu_id: Optional GPU ID filter

        Returns:
            List of models with their status
        """
        params = {}
        if status:
            params['status'] = status
        if gpu_id is not None:
            params['gpu_id'] = gpu_id
        return self._make_request('GET', '/models', params=params)

    def load_model(self, model_id: str, gpu_id: Optional[int] = None, pin: bool = False) -> Dict:
        """
        Pre-load a model onto GPU

        Args:
            model_id: Model identifier
            gpu_id: Optional specific GPU ID
            pin: Whether to pin model to prevent eviction

        Returns:
            Load status and task info
        """
        payload = {
            'model_id': model_id,
            'pin': pin
        }
        if gpu_id is not None:
            payload['gpu_id'] = gpu_id
        return self._make_request('POST', '/models/load', json=payload)

    def unload_model(self, model_id: str, gpu_id: int) -> Dict:
        """
        Unload a model from GPU

        Args:
            model_id: Model identifier
            gpu_id: GPU ID

        Returns:
            Unload status and freed memory
        """
        payload = {'model_id': model_id, 'gpu_id': gpu_id}
        return self._make_request('POST', '/models/unload', json=payload)

    def pin_model(self, model_id: str, gpu_id: int) -> Dict:
        """Pin a model to prevent LRU eviction"""
        payload = {'model_id': model_id, 'gpu_id': gpu_id}
        return self._make_request('POST', '/models/pin', json=payload)

    def unpin_model(self, model_id: str, gpu_id: int) -> Dict:
        """Unpin a model"""
        payload = {'model_id': model_id, 'gpu_id': gpu_id}
        return self._make_request('POST', '/models/unpin', json=payload)

    # Statistics & Metrics

    def stats(self) -> Dict:
        """Get comprehensive system statistics"""
        return self._make_request('GET', '/stats')

    def gpu_stats(self, gpu_id: int) -> Dict:
        """Get statistics for a specific GPU"""
        return self._make_request('GET', f'/stats/gpu/{gpu_id}')

    def metrics(self, format: str = 'prometheus') -> str:
        """
        Get metrics

        Args:
            format: Format ('prometheus' or 'json')

        Returns:
            Metrics in specified format
        """
        endpoint = '/metrics/json' if format == 'json' else '/metrics'
        response = self.session.get(f"{self.base_url}{endpoint}")
        response.raise_for_status()
        return response.text if format == 'prometheus' else response.json()

    # Configuration

    def config(self) -> Dict:
        """Get current configuration"""
        return self._make_request('GET', '/config')

    def update_config(self, config: Dict) -> Dict:
        """
        Update configuration

        Args:
            config: Configuration updates

        Returns:
            Updated configuration status
        """
        return self._make_request('POST', '/config/update', json=config)

    # Context Manager Support

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()


class GPUOrchestratorAsyncClient:
    """Async client for GPU VRAM Orchestrator API"""

    def __init__(self, base_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        """
        Initialize async client

        Args:
            base_url: Base URL of the orchestrator API
            api_key: Optional API key for authentication
        """
        import aiohttp

        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> 'aiohttp.ClientSession':
        """Get or create aiohttp session"""
        import aiohttp

        if self.session is None:
            headers = {'Content-Type': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make async HTTP request"""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"

        async with session.request(method, url, **kwargs) as response:
            response.raise_for_status()
            return await response.json()

    async def predict(self, model_id: str, input_data: Dict, **kwargs) -> Dict:
        """Run inference (async)"""
        payload = {
            'model_id': model_id,
            'input_data': input_data,
            **kwargs
        }
        return await self._make_request('POST', '/predict', json=payload)

    async def status(self) -> Dict:
        """Get status (async)"""
        return await self._make_request('GET', '/status')

    async def close(self):
        """Close session"""
        if self.session:
            await self.session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
