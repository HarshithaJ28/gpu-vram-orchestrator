"""FastAPI Application Setup

Main entry point for the GPU VRAM Orchestrator API
"""

import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.config import config
from src.gpu import GPUDetector

# Configure logging
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="GPU VRAM Orchestrator",
    description="Production-grade GPU memory orchestration system",
    version="0.1.0"
)

# Global state (will be enhanced in later phases)
_gpu_detector: GPUDetector | None = None


@app.on_event("startup")
async def startup():
    """Initialize system on startup"""
    logger.info("=" * 80)
    logger.info("GPU VRAM Orchestrator starting...")
    logger.info("=" * 80)
    logger.info(config.get_summary())

    global _gpu_detector

    # Initialize GPU detector
    _gpu_detector = GPUDetector()
    gpus = _gpu_detector.detect_gpus()

    if config.GPU_ENABLED:
        if not gpus:
            logger.warning("⚠️  GPU_ENABLED but no GPUs detected. Running in CPU mode.")
        else:
            logger.info(f"✅ Detected {len(gpus)} GPU(s)")
            for gpu in gpus:
                logger.info(f"  - GPU {gpu.gpu_id}: {gpu.name} ({gpu.total_memory_mb}MB)")
    else:
        logger.info("GPU acceleration disabled (GPU_ENABLED=false)")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    logger.info("Shutting down GPU VRAM Orchestrator...")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    logger.debug("Health check requested")
    return {
        "status": "healthy",
        "service": "gpu-vram-orchestrator"
    }


@app.get("/status")
async def status():
    """Get system status"""
    if _gpu_detector is None:
        return JSONResponse(
            status_code=503,
            content={"error": "System not initialized"}
        )

    gpus = _gpu_detector.detect_gpus()
    gpu_info = []

    for gpu in gpus:
        free_mem = _gpu_detector.get_free_memory_mb(gpu.gpu_id)
        util = _gpu_detector.get_utilization_percent(gpu.gpu_id)

        gpu_info.append({
            "gpu_id": gpu.gpu_id,
            "name": gpu.name,
            "total_memory_mb": gpu.total_memory_mb,
            "free_memory_mb": free_mem,
            "compute_capability": gpu.compute_capability,
            "utilization_percent": util
        })

    return {
        "status": "operational",
        "gpus": gpu_info,
        "num_gpus": len(gpus),
        "gpu_enabled": config.GPU_ENABLED
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "GPU VRAM Orchestrator",
        "version": "0.1.0",
        "status": "Phase 1 - Foundation",
        "docs": "/docs",
        "health": "/health",
        "status_endpoint": "/status"
    }


# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle all exceptions"""
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
