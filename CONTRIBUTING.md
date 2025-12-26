# Contributing to GPU VRAM Orchestrator

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to the GPU VRAM Orchestrator project.

## Code of Conduct

This project adheres to the Contributor Covenant Code of Conduct. By participating, you are expected to uphold this code.

## Getting Started

### Prerequisites

- Python 3.10+
- GPU with NVIDIA CUDA 11.8+
- Docker & Docker Compose (for containerized development)
- Git

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/HarshithaJ28/gpu-vram-orchestrator.git
cd gpu-vram-orchestrator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov

# Verify installation
cd backend
python -m pytest tests/ -v --tb=short
```

### Development Workflow

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Follow the code style guidelines (see below)
   - Write tests for new functionality
   - Update documentation as needed

3. **Run tests and linting**
   ```bash
   # Run tests
   cd backend
   python -m pytest tests/ -v --cov=src

   # Check code style
   black --check src/
   isort --check-only src/
   ```

4. **Commit and push**
   ```bash
   git add .
   git commit -m "feat: describe your changes"
   git push origin feature/your-feature-name
   ```

5. **Create a Pull Request**
   - Use a descriptive title
   - Reference any related issues
   - Include test results

## Code Style Guidelines

### Python Code Style

We follow PEP 8 with some project-specific conventions:

```python
# ✓ Good
def calculate_scheduler_score(
    memory_available: float,
    current_load: float,
    affinity_score: float
) -> float:
    """Calculate weighted scheduler score."""
    weights = {
        'memory': 0.5,
        'load': 0.3,
        'affinity': 0.2
    }
    return (
        memory_available * weights['memory'] +
        (1 - current_load) * weights['load'] +
        affinity_score * weights['affinity']
    )

# ✗ Bad
def calc_score(mem,load,aff):
    return mem*0.5 + (1-load)*0.3 + aff*0.2
```

### Type Hints

All functions should have type hints:

```python
from typing import Dict, List, Optional, Tuple

def get_gpu_memory(gpu_id: int) -> Dict[str, float]:
    """Get memory info for a GPU."""
    pass

def predict(
    model_id: str,
    data: Dict[str, any],
    return_timing: bool = False
) -> Dict[str, any]:
    """Run inference."""
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def load_model(model_id: str, gpu_id: Optional[int] = None) -> bool:
    """
    Load a model onto GPU memory.
    
    Args:
        model_id: Unique identifier for the model
        gpu_id: Optional specific GPU to load onto
        
    Returns:
        True if load successful, False otherwise
        
    Raises:
        ValueError: If model_id is invalid
        RuntimeError: If GPU allocation fails
        
    Example:
        >>> load_model('fraud-detection-v1', gpu_id=0)
        True
    """
    pass
```

### Imports

Organize imports in this order:
1. Standard library
2. Third-party libraries
3. Local imports

```python
import json
import time
from typing import Dict, List

import numpy as np
import torch
from fastapi import FastAPI

from src.gpu.detector import GPUDetector
from src.cache.gpu_cache import GPUModelCache
```

## Testing

### Test Structure

Tests should be organized by component:

```
tests/
├── test_gpu_detector.py
├── test_gpu_memory_manager.py
├── test_gpu_scheduler.py
├── test_gpu_cache.py
├── test_predictor.py
├── test_metrics.py
└── test_integration.py
```

### Writing Tests

```python
import pytest
from unittest.mock import Mock, patch

class TestGPUScheduler:
    """Test suite for GPU scheduler."""
    
    @pytest.fixture
    def scheduler(self):
        """Create a scheduler instance for testing."""
        return GPUScheduler(num_gpus=2)
    
    def test_select_gpu_with_most_available_memory(self, scheduler):
        """Test GPU selection prioritizes available memory."""
        # Arrange
        gpu_states = [
            {'gpu_id': 0, 'available_mb': 5000},
            {'gpu_id': 1, 'available_mb': 8000},
        ]
        
        # Act
        selected_gpu = scheduler.select_gpu(gpu_states)
        
        # Assert
        assert selected_gpu == 1
    
    @pytest.mark.asyncio
    async def test_async_scheduling(self):
        """Test async scheduling."""
        scheduler = GPUScheduler()
        result = await scheduler.schedule_async(model_id='test-model')
        assert result is not None
```

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_gpu_cache.py

# Run specific test with verbose output
pytest tests/test_gpu_cache.py::TestGPUModelCache::test_eviction -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=html

# Run only unit tests (exclude integration)
pytest tests/ -m "not integration"
```

### Coverage Requirements

- Minimum coverage: 80%
- Critical paths (GPU manager, scheduler): 95%+
- New code must have tests before merge

## Documentation

### Updating Documentation

When making changes that affect users, update relevant documentation:

- **API Changes**: Update [API.md](API.md)
- **Architecture Changes**: Update [ARCHITECTURE.md](ARCHITECTURE.md)
- **Deployment Changes**: Update [DEPLOYMENT.md](DEPLOYMENT.md)
- **New Features**: Add examples to `examples/`

### Documentation Style

Use clear, concise language with code examples:

```markdown
## Feature Name

Brief description of the feature.

### Usage

```python
# Example code
scheduler = GPUScheduler()
gpu_id = scheduler.select_gpu(gpu_states)
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| gpu_states | List | List of GPU state dicts |

### Returns

Returns the GPU ID with the best fit.
```

## Commit Messages

Follow Conventional Commits format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Code style
- `refactor`: Code refactoring
- `test`: Test changes
- `chore`: Build, CI, etc.

Example:
```
feat(scheduler): add affinity-based GPU selection

Implement affinity scoring to colocate similar models on same GPU.
Reduces model migration overhead by 30%.

Fixes #123
```

## Pull Request Process

1. **Before submitting**:
   - Run tests: `pytest tests/ -v`
   - Check coverage: `pytest tests/ --cov=src`
   - Format code: `black src/` and `isort src/`

2. **PR checklist**:
   - [ ] Tests pass locally
   - [ ] Coverage maintained (≥80%)
   - [ ] Documentation updated
   - [ ] No breaking changes (or documented)
   - [ ] Commits follow conventional format

3. **Review process**:
   - At least one maintainer review required
   - All discussions must be resolved
   - CI pipeline must pass

## Performance Considerations

When contributing optimizations:

1. **Benchmark before and after**
   - Use `examples/performance_benchmarks.py`
   - Report baseline and improvement percentages

2. **Profile code**
   ```python
   import cProfile
   import pstats
   
   profiler = cProfile.Profile()
   profiler.enable()
   # Your code here
   profiler.disable()
   stats = pstats.Stats(profiler)
   stats.sort_stats('cumulative')
   stats.print_stats(20)
   ```

3. **Avoid breaking changes**
   - Maintain backward compatibility
   - Deprecate old APIs gradually
   - Update migration guide

## Security

### Reporting Security Issues

**Do not** open public issues for security vulnerabilities. Instead:

1. Email: security@example.com
2. Include proof of concept
3. Allow 90 days for fix before public disclosure

### Secure Coding

- Validate all inputs
- Sanitize error messages (no internal details)
- Use TLS/SSL for network communication
- Rotate credentials regularly

## Performance Optimization

When proposing performance improvements:

1. Provide benchmarks showing improvement
2. Ensure no regression in other areas
3. Document any trade-offs

Example:

```
Optimization: Reduce scheduler latency

Before: Avg 2.5ms, P99 5.2ms
After: Avg 0.45ms, P99 1.0ms
Improvement: 5.6x faster

Trade-off: Slightly lower prediction accuracy (78% → 77%)
```

## Becoming a Maintainer

Maintainers should:
- Have contributed significantly to the project
- Demonstrate deep understanding of codebase
- Commit to ongoing maintenance
- Follow the same guidelines as contributors

## Questions?

- **Documentation**: Check [README.md](README.md) and docs/
- **How-to**: See `examples/` directory
- **Issues**: Search GitHub Issues
- **Discussions**: Use GitHub Discussions

## License

By contributing to GPU VRAM Orchestrator, you agree your contributions will be licensed under the same MIT License.

---

Thank you for contributing! 🙌
