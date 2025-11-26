"""
Base Algorithm class for Tau signal processing plugins.

Algorithms process input data (audio, signals) and produce output (spike events,
filtered signals, features). Each algorithm defines its parameters, build process,
and execution interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Type
import subprocess


@dataclass
class AlgorithmParams:
    """Base class for algorithm parameters."""
    pass


@dataclass
class AlgorithmOutput:
    """Standard output format for algorithm results."""
    data: Any  # Primary output data
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None


class Algorithm(ABC):
    """
    Base class for Tau algorithms.

    Subclasses implement signal processing algorithms that can be:
    - Built from source (C, Rust, etc.)
    - Configured with parameters
    - Run on input data
    - Produce structured output
    """

    name: str = "base"
    version: str = "0.0.0"
    description: str = ""

    def __init__(self, params: Optional[AlgorithmParams] = None):
        self.params = params or self.default_params()
        self._binary_path: Optional[Path] = None

    @classmethod
    @abstractmethod
    def default_params(cls) -> AlgorithmParams:
        """Return default parameters for this algorithm."""
        pass

    @abstractmethod
    def run(self, input_path: Path, output_path: Optional[Path] = None) -> AlgorithmOutput:
        """
        Execute the algorithm on input data.

        Args:
            input_path: Path to input file (audio, signal data, etc.)
            output_path: Optional output path (algorithm may generate its own)

        Returns:
            AlgorithmOutput with results and metadata
        """
        pass

    def is_built(self) -> bool:
        """Check if algorithm binary/resources are available."""
        return self._binary_path is not None and self._binary_path.exists()

    def build(self, force: bool = False) -> bool:
        """
        Build algorithm from source if needed.

        Args:
            force: Rebuild even if already built

        Returns:
            True if build succeeded
        """
        return True  # Override in subclasses that need building

    def get_version(self) -> str:
        """Return algorithm version string."""
        return self.version

    def validate_params(self) -> List[str]:
        """
        Validate current parameters.

        Returns:
            List of error messages (empty if valid)
        """
        return []


class AlgorithmRegistry:
    """
    Registry for available algorithms.

    Provides discovery and instantiation of algorithm plugins.
    """

    _algorithms: Dict[str, Type[Algorithm]] = {}

    @classmethod
    def register(cls, algorithm_class: Type[Algorithm]) -> Type[Algorithm]:
        """
        Register an algorithm class.

        Can be used as a decorator:
            @AlgorithmRegistry.register
            class MyAlgorithm(Algorithm):
                ...
        """
        cls._algorithms[algorithm_class.name] = algorithm_class
        return algorithm_class

    @classmethod
    def get(cls, name: str) -> Optional[Type[Algorithm]]:
        """Get algorithm class by name."""
        return cls._algorithms.get(name)

    @classmethod
    def list(cls) -> List[str]:
        """List all registered algorithm names."""
        return list(cls._algorithms.keys())

    @classmethod
    def create(cls, name: str, params: Optional[AlgorithmParams] = None) -> Optional[Algorithm]:
        """Create an algorithm instance by name."""
        algo_class = cls.get(name)
        if algo_class:
            return algo_class(params)
        return None
