"""FastAPI Application

Production-grade GPU VRAM Orchestrator API
"""

import logging
import time
import traceback
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from dataclasses import asdict

from src.config import config
from src.gpu import GPUDetector
from src.cache.gpu_cache import GPUModelCache
from src.scheduler.gpu_scheduler import GPUScheduler
from src.inference.engine import InferenceEngine, InferenceResult
from src.registry import ModelRegistry
from src.predictor import ModelAccessPredictor, ModelPreloader
from src.monitoring.metrics import MetricsCollector

# Configure logging
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# GLOBAL APPLICATION STATE
# ============================================================================

_gpu_detector: Optional[GPUDetector] = None
_gpu_caches: List[GPUModelCache] = []
_scheduler: Optional[GPUScheduler] = None
_inference_engine: Optional[InferenceEngine] = None
_model_registry: Optional[ModelRegistry] = None
_metrics: Optional[MetricsCollector] = None
_predictor: Optional[ModelAccessPredictor] = None
_preloader: Optional[ModelPreloader] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown"""
    global _gpu_detector, _gpu_caches, _scheduler, _inference_engine, _model_registry, _metrics
    global _predictor, _preloader

    logger.info("=" * 80)
    logger.info("🚀 GPU VRAM Orchestrator (ModelMesh) Starting...")
    logger.info("=" * 80)

    try:
        # Initialize GPU detector
        _gpu_detector = GPUDetector()
        gpus = _gpu_detector.detect_gpus()

        if config.GPU_ENABLED and gpus:
            logger.info(f"✓ Detected {len(gpus)} GPU(s)")
            for gpu in gpus:
                logger.info(f"  GPU {gpu.gpu_id}: {gpu.name} ({gpu.total_memory_mb}MB)")

            # Initialize GPU caches (one per GPU)
            _gpu_caches = [
                GPUModelCache(
                    gpu_id=i,
                    total_memory_mb=gpu.total_memory_mb,
                    reserved_memory_mb=2000
                )
                for i, gpu in enumerate(gpus)
            ]

            # Initialize scheduler
            _scheduler = GPUScheduler(_gpu_caches)

        else:
            logger.warning("⚠️  GPU_ENABLED but no GPUs detected or GPU disabled")
            if config.GPU_ENABLED:
                logger.info("Running in CPU-only mode")

        # Initialize other components
        _inference_engine = InferenceEngine()
        _model_registry = ModelRegistry(storage_path=config.MODELS_DIR)
        _metrics = MetricsCollector(use_prometheus=True)

        logger.info("✓ Inference engine initialized")
        logger.info("✓ Model registry initialized")
        logger.info("✓ Metrics collector initialized")

        # Initialize ML-based predictor
        _predictor = ModelAccessPredictor(
            history_window_hours=24,
            min_observations=5
        )
        logger.info("✓ Access pattern predictor initialized")

        # Initialize and start preloader
        _preloader = ModelPreloader(
            predictor=_predictor,
            scheduler=_scheduler,
            registry=_model_registry,
            interval_seconds=60,  # Run every minute
            confidence_threshold=0.5,
            max_preloads_per_cycle=3
        )
        await _preloader.start()
        logger.info("✓ Model preloader started (cycle=60s, confidence=0.5)")

        logger.info("=" * 80)
        logger.info("✓ ModelMesh Ready with Predictive Loading!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"✗ Startup failed: {e}", exc_info=True)
        raise

    yield  # ← Application runs here

    # Shutdown
    logger.info("Shutting down ModelMesh...")
    try:
        # Stop preloader first
        if _preloader:
            await _preloader.stop()
            logger.info("✓ Preloader stopped")
        
        # Clean up GPU memory
        for gpu_cache in _gpu_caches:
            gpu_cache.clear()
        logger.info("✓ Cleaned up GPU memory")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(
    title="ModelMesh - GPU VRAM Orchestrator",
    description="Production-grade multi-model GPU serving with intelligent caching",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# PROMETHEUS METRICS ENDPOINT
# ============================================================================
from prometheus_client import make_asgi_app
try:
    metrics_app = make_asgi_app()
    app.mount("/prometheus", metrics_app)
    logger.info("✓ Prometheus metrics mounted at /prometheus")
except Exception as e:
    logger.warning(f"⚠️  Failed to mount Prometheus: {e}")


# ============================================================================
# SECURITY MIDDLEWARE - API KEY AUTHENTICATION
# ============================================================================
from fastapi import Header, HTTPException, Depends
from functools import lru_cache
import os

@lru_cache(maxsize=1)
def get_api_key() -> str:
    """Get API key from environment"""
    key = os.getenv("API_KEY", "default-key")
    if key == "default-key":
        logger.warning("⚠️  Using default API key - set API_KEY env var in production")
    return key

async def verify_api_key(x_api_key: str = Header(None)):
    """Verify API key from request header"""
    api_key_enabled = os.getenv("API_KEYS_ENABLED", "true").lower() == "true"
    
    if not api_key_enabled:
        return True  # Skip auth if disabled
    
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide 'X-API-Key' header"
        )
    
    expected_key = get_api_key()
    if x_api_key != expected_key:
        logger.warning(f"Invalid API key attempted: {x_api_key[:8]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return True


# ============================================================================
# RATE LIMITING MIDDLEWARE
# ============================================================================
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request, exc):
    """Handle rate limit exceeded"""
    return JSONResponse(
        status_code=429,
        content={"error": "Rate limit exceeded", "detail": str(exc.detail)}
    )

logger.info("✓ Rate limiting configured")


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class PredictionRequest(BaseModel):
    """Single prediction request"""
    model_id: str
    data: Dict[str, Any]
    timeout_ms: Optional[int] = 5000


class PredictionResponse(BaseModel):
    """Single prediction response"""
    model_id: str
    prediction: Any
    latency_ms: float
    gpu_id: Optional[int] = None
    cached: bool
    batch_size: int = 1


class BatchPredictionRequest(BaseModel):
    """Batch prediction request"""
    model_id: str
    batch_data: List[Dict[str, Any]]
    batch_size: int = 32


class BatchPredictionResponse(BaseModel):
    """Batch prediction response"""
    model_id: str
    predictions: List[Any]
    latency_ms: float
    gpu_id: Optional[int] = None
    cached: bool
    batch_size: int


class ModelLoadRequest(BaseModel):
    """Model loading request"""
    model_id: str
    model_path: str
    gpu_id: Optional[int] = None
    pin: bool = False


# ============================================================================
# PREDICTION ENDPOINTS
# ============================================================================

@app.post("/predict", response_model=PredictionResponse)
@limiter.limit("100/minute")
async def predict(request: PredictionRequest, api_key_valid: bool = Depends(verify_api_key)):
    """
    Make prediction using specified model

    **Flow:**
    1. Route to optimal GPU (scheduler)
    2. Get model from cache or load it
    3. Run inference
    4. Return prediction

    **Response Time:**
    - First request (cold): ~100ms (includes model loading)
    - Subsequent requests (hot): ~5-10ms (cached)
    
    **Headers required:**
    - X-API-Key: Your API key
    """
    start_time = time.time()

    if not _scheduler or not _inference_engine or not _gpu_caches:
        raise HTTPException(500, "System not initialized")

    try:
        # ===== STEP 1: Route request =====
        gpu_id, was_cached = _scheduler.route_request(request.model_id)
        gpu_cache = _gpu_caches[gpu_id]

        _scheduler.record_request(gpu_id)

        # ===== STEP 1B: Record access for ML predictor =====
        if _predictor:
            _predictor.record_access(request.model_id, gpu_id)

        try:
            # ===== STEP 2: Get or load model =====
            loaded_model = gpu_cache.get_model(request.model_id)

            if loaded_model is None:
                # Cold start - load model
                logger.info(f"[{request.model_id}] Cold start - loading to GPU {gpu_id}")

                model_path = _model_registry.get_model_path(request.model_id)
                if not model_path:
                    raise HTTPException(404, f"Model {request.model_id} not found")

                success = gpu_cache.load_model(request.model_id, model_path=model_path)
                if not success:
                    raise HTTPException(500, f"Failed to load {request.model_id}")

                loaded_model = gpu_cache.get_model(request.model_id)

            # ===== STEP 3: Run inference =====
            prediction = await _inference_engine.predict(
                model=loaded_model.model,
                input_data=request.data,
                model_id=request.model_id,
                gpu_id=gpu_id
            )

            # ===== STEP 4: Record metrics =====
            latency_ms = (time.time() - start_time) * 1000
            _metrics.record_inference_latency(request.model_id, latency_ms)
            if was_cached:
                _metrics.record_cache_hit(gpu_id)
            else:
                _metrics.record_cache_miss(gpu_id)

            logger.info(
                f"[{request.model_id}] Prediction: {latency_ms:.1f}ms "
                f"({'HOT' if was_cached else 'COLD'})"
            )

            return PredictionResponse(
                model_id=request.model_id,
                prediction=prediction,
                latency_ms=latency_ms,
                gpu_id=gpu_id,
                cached=was_cached,
                batch_size=1
            )

        finally:
            _scheduler.release_request(gpu_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Prediction failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, str(e))


@app.post("/predict/batch", response_model=BatchPredictionResponse)
@limiter.limit("50/minute")
async def predict_batch(request: BatchPredictionRequest, api_key_valid: bool = Depends(verify_api_key)):
    """
    Batch prediction for multiple inputs

    More efficient than individual predictions because:
    - Single GPU transfer
    - Vectorized operations
    - Better GPU utilization
    """
    start_time = time.time()

    if not _scheduler or not _inference_engine or not _gpu_caches:
        raise HTTPException(500, "System not initialized")

    try:
        # Route
        gpu_id, was_cached = _scheduler.route_request(request.model_id)
        gpu_cache = _gpu_caches[gpu_id]

        _scheduler.record_request(gpu_id)

        try:
            # Load model if needed
            loaded_model = gpu_cache.get_model(request.model_id)
            if loaded_model is None:
                model_path = _model_registry.get_model_path(request.model_id)
                if not model_path:
                    raise HTTPException(404, f"Model {request.model_id} not found")

                success = gpu_cache.load_model(request.model_id, model_path=model_path)
                if not success:
                    raise HTTPException(500, f"Failed to load {request.model_id}")

                loaded_model = gpu_cache.get_model(request.model_id)

            # Batch inference
            predictions = _inference_engine.predict_batch(
                model=loaded_model.model,
                batch_data=request.batch_data,
                model_id=request.model_id,
                gpu_id=gpu_id,
                batch_size=request.batch_size
            )

            latency_ms = (time.time() - start_time) * 1000
            _metrics.record_inference_latency(request.model_id, latency_ms)
            if was_cached:
                _metrics.record_cache_hit(gpu_id)
            else:
                _metrics.record_cache_miss(gpu_id)

            logger.info(
                f"[{request.model_id}] Batch ({len(request.batch_data)} items): "
                f"{latency_ms:.1f}ms"
            )

            return BatchPredictionResponse(
                model_id=request.model_id,
                predictions=predictions,
                latency_ms=latency_ms,
                gpu_id=gpu_id,
                cached=was_cached,
                batch_size=len(request.batch_data)
            )

        finally:
            _scheduler.release_request(gpu_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch prediction failed: {e}")
        raise HTTPException(500, str(e))


# ============================================================================
# MODEL MANAGEMENT ENDPOINTS
# ============================================================================

@app.post("/models/load")
async def load_model(request: ModelLoadRequest):
    """
    Explicitly load a model to GPU

    Useful for pre-warming cache with hot models
    """
    if not _gpu_caches or not _scheduler:
        raise HTTPException(500, "System not initialized")

    try:
        # Select GPU if not specified
        if request.gpu_id is not None:
            gpu_cache = _gpu_caches[request.gpu_id]
        else:
            gpu_id, _ = _scheduler.route_request(request.model_id)
            gpu_cache = _gpu_caches[gpu_id]

        success = gpu_cache.load_model(
            model_id=request.model_id,
            model_path=request.model_path,
            pin=request.pin
        )

        if not success:
            raise HTTPException(500, f"Failed to load {request.model_id}")

        return {
            'model_id': request.model_id,
            'status': 'loaded',
            'gpu_id': gpu_cache.gpu_id,
            'pinned': request.pin
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Model load failed: {e}")
        raise HTTPException(500, str(e))


@app.post("/models/{model_id}/evict")
async def evict_model(model_id: str, gpu_id: Optional[int] = None):
    """
    Evict model from GPU(s)

    Remove model from cache to free GPU memory
    """
    if not _gpu_caches:
        raise HTTPException(500, "System not initialized")

    if gpu_id is not None:
        # Evict from specific GPU
        if gpu_id >= len(_gpu_caches):
            raise HTTPException(400, f"Invalid GPU ID: {gpu_id}")

        success = _gpu_caches[gpu_id].unload_model(model_id)
        return {
            'model_id': model_id,
            'evicted_from': [gpu_id] if success else [],
            'success': success
        }
    else:
        # Evict from all GPUs
        evicted_from = []
        for gpu_cache in _gpu_caches:
            if gpu_cache.unload_model(model_id):
                evicted_from.append(gpu_cache.gpu_id)

        return {
            'model_id': model_id,
            'evicted_from': evicted_from,
            'success': len(evicted_from) > 0
        }


@app.post("/models/{model_id}/pin")
async def pin_model(model_id: str, gpu_id: int):
    """Pin model (never evict)"""
    if gpu_id >= len(_gpu_caches):
        raise HTTPException(400, f"Invalid GPU ID: {gpu_id}")

    success = _gpu_caches[gpu_id].pin_model(model_id)
    if not success:
        raise HTTPException(404, f"Model {model_id} not loaded on GPU {gpu_id}")

    return {'model_id': model_id, 'gpu_id': gpu_id, 'pinned': True}


@app.post("/models/{model_id}/unpin")
async def unpin_model(model_id: str, gpu_id: int):
    """Unpin model (can be evicted)"""
    if gpu_id >= len(_gpu_caches):
        raise HTTPException(400, f"Invalid GPU ID: {gpu_id}")

    success = _gpu_caches[gpu_id].unpin_model(model_id)
    if not success:
        raise HTTPException(404, f"Model {model_id} not loaded on GPU {gpu_id}")

    return {'model_id': model_id, 'gpu_id': gpu_id, 'pinned': False}


# ============================================================================
# STATISTICS & MONITORING ENDPOINTS
# ============================================================================

@app.get("/stats/gpu")
async def get_gpu_stats():
    """Get statistics for all GPUs"""
    if not _gpu_caches:
        return {"error": "No GPUs available"}

    return [gpu.get_stats() for gpu in _gpu_caches]


@app.get("/stats/gpu/{gpu_id}")
async def get_gpu_stats_by_id(gpu_id: int):
    """Get statistics for specific GPU"""
    if gpu_id >= len(_gpu_caches):
        raise HTTPException(400, f"GPU {gpu_id} not found")

    return _gpu_caches[gpu_id].get_stats()


@app.get("/stats/scheduler")
async def get_scheduler_stats():
    """Get scheduler state"""
    if not _scheduler:
        raise HTTPException(500, "Scheduler not initialized")

    return _scheduler.get_stats()


@app.get("/stats/models")
async def get_models_stats():
    """Get all loaded models across GPUs"""
    models_by_gpu = {}

    for gpu_cache in _gpu_caches:
        stats = gpu_cache.get_stats()
        models_by_gpu[f"gpu_{gpu_cache.gpu_id}"] = stats['models']

    return models_by_gpu


@app.get("/registry/models")
async def list_registered_models():
    """List all registered models"""
    if not _model_registry:
        raise HTTPException(500, "Registry not initialized")

    return _model_registry.list_models()


@app.get("/metrics/predictions")
async def get_prediction_metrics():
    """Get prediction metrics"""
    if not _metrics:
        raise HTTPException(500, "Metrics not initialized")

    return _metrics.export_metrics_dict()


# ============================================================================
# HEALTH & INFO ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    total_models = sum(len(gpu.models) for gpu in _gpu_caches) if _gpu_caches else 0
    avg_util = (
        sum(gpu.get_stats()['utilization_pct'] for gpu in _gpu_caches) / len(_gpu_caches)
        if _gpu_caches else 0
    )

    cache_hit_rate = (
        sum(gpu.get_stats()['hit_rate'] for gpu in _gpu_caches) / len(_gpu_caches)
        if _gpu_caches else 0
    )

    return {
        'status': 'healthy',
        'service': 'ModelMesh',
        'num_gpus': len(_gpu_caches),
        'total_models_loaded': total_models,
        'avg_gpu_utilization_pct': avg_util,
        'cache_hit_rate': cache_hit_rate
    }


@app.get("/info")
async def get_info():
    """Get system information"""
    gpus_info = []
    if _gpu_detector:
        detected_gpus = _gpu_detector.detect_gpus()
        gpus_info = [
            {
                'gpu_id': gpu.gpu_id,
                'name': gpu.name,
                'compute_capability': gpu.compute_capability,
                'total_memory_mb': gpu.total_memory_mb
            }
            for gpu in detected_gpus
        ]

    return {
        'service': 'ModelMesh GPU VRAM Orchestrator',
        'version': '1.0.0',
        'status': 'operational',
        'gpus': gpus_info,
        'config': {
            'gpu_enabled': config.GPU_ENABLED,
            'models_dir': config.MODELS_DIR
        }
    }


# ============================================================================
# MODEL REGISTRY ENDPOINTS (WEEK 2)
# ============================================================================

@app.post("/registry/register")
async def register_model(
    model_id: str,
    model_path: str,
    version: str = "v1",
    framework: str = "pytorch",
    task_type: str = "classification",
    description: str = "",
    tags: Optional[List[str]] = None
):
    """Register a new model in the registry"""
    if not _model_registry:
        raise HTTPException(500, "Registry not initialized")

    try:
        metadata = _model_registry.register_model(
            model_id=model_id,
            model_path=model_path,
            version=version,
            framework=framework,
            task_type=task_type,
            description=description,
            tags=tags or []
        )
        return asdict(metadata)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Model registration failed: {e}")
        raise HTTPException(500, str(e))


@app.get("/registry/models")
async def list_registered_models(
    framework: Optional[str] = None,
    task_type: Optional[str] = None
):
    """List all registered models with optional filtering"""
    if not _model_registry:
        raise HTTPException(500, "Registry not initialized")

    try:
        models = _model_registry.list_models(
            framework=framework,
            task_type=task_type
        )
        return models
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(500, str(e))


@app.get("/registry/models/{model_id}")
async def get_model_metadata(model_id: str):
    """Get metadata for specific model"""
    if not _model_registry:
        raise HTTPException(500, "Registry not initialized")

    try:
        metadata = _model_registry.get_model_metadata(model_id)
        if not metadata:
            raise HTTPException(404, f"Model {model_id} not found")
        
        return asdict(metadata)
    except Exception as e:
        logger.error(f"Failed to get model metadata: {e}")
        raise HTTPException(500, str(e))


@app.delete("/registry/models/{model_id}")
async def delete_model(model_id: str):
    """Delete a model from registry"""
    if not _model_registry:
        raise HTTPException(500, "Registry not initialized")

    try:
        success = _model_registry.delete_model(model_id)
        if not success:
            raise HTTPException(404, f"Model {model_id} not found")
        
        return {"deleted": model_id, "success": True}
    except Exception as e:
        logger.error(f"Failed to delete model: {e}")
        raise HTTPException(500, str(e))


@app.get("/registry/search")
async def search_models(query: str):
    """Search models by query string"""
    if not _model_registry:
        raise HTTPException(500, "Registry not initialized")

    try:
        results = _model_registry.search_models(query)
        return results
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(500, str(e))


@app.post("/registry/models/{model_id}/verify")
async def verify_model(model_id: str):
    """Verify model file integrity"""
    if not _model_registry:
        raise HTTPException(500, "Registry not initialized")

    try:
        is_valid = _model_registry.verify_model(model_id)
        return {
            'model_id': model_id,
            'valid': is_valid
        }
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        raise HTTPException(500, str(e))


@app.get("/registry/stats")
async def get_registry_stats():
    """Get registry statistics"""
    if not _model_registry:
        raise HTTPException(500, "Registry not initialized")

    try:
        stats = _model_registry.get_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(500, str(e))


# ============================================================================
# PREDICTOR ENDPOINTS (WEEK 2)
# ============================================================================

@app.get("/predictor/predictions")
async def get_predictions(top_k: int = 5):
    """Get current model predictions (most likely to be accessed soon)"""
    if not _predictor:
        raise HTTPException(500, "Predictor not initialized")

    try:
        predictions = _predictor.predict_next_models(top_k=top_k, min_probability=0.3)
        return [
            {'model_id': model_id, 'probability': float(prob)}
            for model_id, prob in predictions
        ]
    except Exception as e:
        logger.error(f"Failed to get predictions: {e}")
        raise HTTPException(500, str(e))


@app.get("/predictor/patterns/{model_id}")
async def get_model_patterns(model_id: str):
    """Get learned access patterns for a specific model"""
    if not _predictor:
        raise HTTPException(500, "Predictor not initialized")

    try:
        patterns = _predictor.get_pattern_summary(model_id)
        return patterns
    except Exception as e:
        logger.error(f"Failed to get patterns: {e}")
        raise HTTPException(500, str(e))


@app.get("/predictor/stats")
async def get_predictor_stats():
    """Get predictor statistics"""
    if not _predictor:
        raise HTTPException(500, "Predictor not initialized")

    try:
        stats = _predictor.get_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get predictor stats: {e}")
        raise HTTPException(500, str(e))


# ============================================================================
# PRELOADER ENDPOINTS (WEEK 2)
# ============================================================================

@app.get("/preloader/stats")
async def get_preloader_stats():
    """Get preloader statistics"""
    if not _preloader:
        raise HTTPException(500, "Preloader not initialized")

    try:
        stats = _preloader.get_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get preloader stats: {e}")
        raise HTTPException(500, str(e))


@app.post("/preloader/start")
async def start_preloader():
    """Start preloader (if stopped)"""
    if not _preloader:
        raise HTTPException(500, "Preloader not initialized")

    try:
        if _preloader.running:
            return {'status': 'already_running'}
        
        await _preloader.start()
        return {'status': 'started'}
    except Exception as e:
        logger.error(f"Failed to start preloader: {e}")
        raise HTTPException(500, str(e))


@app.post("/preloader/stop")
async def stop_preloader():
    """Stop preloader"""
    if not _preloader:
        raise HTTPException(500, "Preloader not initialized")

    try:
        if not _preloader.running:
            return {'status': 'already_stopped'}
        
        await _preloader.stop()
        return {'status': 'stopped'}
    except Exception as e:
        logger.error(f"Failed to stop preloader: {e}")
        raise HTTPException(500, str(e))


@app.post("/preloader/reset-stats")
async def reset_preloader_stats():
    """Reset preloader statistics"""
    if not _preloader:
        raise HTTPException(500, "Preloader not initialized")

    try:
        _preloader.reset_stats()
        return {'status': 'reset'}
    except Exception as e:
        logger.error(f"Failed to reset stats: {e}")
        raise HTTPException(500, str(e))


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        'service': 'ModelMesh',
        'version': '1.0.0',
        'description': 'Multi-model GPU serving with intelligent caching + predictive preloading',
        'docs': '/docs',
        'features': {
            'week1': ['GPU caching', 'Smart scheduling', 'LRU eviction', 'Batch inference'],
            'week2': ['Model registry', 'ML predictive loading', 'Background preloader']
        },
        'endpoints': {
            'prediction': '/predict (POST)',
            'batch_prediction': '/predict/batch (POST)',
            'registry': '/registry/models (GET|POST|DELETE)',
            'predictor': '/predictor/predictions (GET)',
            'preloader': '/preloader/stats (GET)',
            'health': '/health (GET)',
            'docs': '/docs (GET)'
        }
    }


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle all unhandled exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=config.HOST,
        port=config.PORT,
        log_level=config.LOG_LEVEL.lower()
    )

