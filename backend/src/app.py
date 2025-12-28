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

from src.config import config
from src.gpu import GPUDetector
from src.cache.gpu_cache import GPUModelCache
from src.scheduler.gpu_scheduler import GPUScheduler
from src.inference.engine import InferenceEngine, InferenceResult
from src.registry import ModelRegistry
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown"""
    global _gpu_detector, _gpu_caches, _scheduler, _inference_engine, _model_registry, _metrics

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
        logger.info("=" * 80)
        logger.info("✓ ModelMesh Ready!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"✗ Startup failed: {e}", exc_info=True)
        raise

    yield  # ← Application runs here

    # Shutdown
    logger.info("Shutting down ModelMesh...")
    try:
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
async def predict(request: PredictionRequest):
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
    """
    start_time = time.time()

    if not _scheduler or not _inference_engine or not _gpu_caches:
        raise HTTPException(500, "System not initialized")

    try:
        # ===== STEP 1: Route request =====
        gpu_id, was_cached = _scheduler.route_request(request.model_id)
        gpu_cache = _gpu_caches[gpu_id]

        _scheduler.record_request(gpu_id)

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
async def predict_batch(request: BatchPredictionRequest):
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


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        'service': 'ModelMesh',
        'version': '1.0.0',
        'description': 'Multi-model GPU serving with intelligent caching',
        'docs': '/docs',
        'endpoints': {
            'prediction': '/predict (POST)',
            'batch_prediction': '/predict/batch (POST)',
            'health': '/health (GET)',
            'info': '/info (GET)',
            'stats': '/stats/gpu (GET)'
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

