"""Configuration models for the steel drawing parser."""

from dataclasses import dataclass, field
from typing import List, Optional
from .processing import ProcessingResult, ProcessingError


@dataclass
class ExtractionConfig:
    """Configuration parameters for component extraction."""
    min_component_size: int = 50  # pixels
    dimension_tolerance: float = 0.1
    confidence_threshold: float = 0.7
    supported_units: List[str] = field(default_factory=lambda: ["mm", "in", "ft"])
    material_standards: List[str] = field(default_factory=lambda: ["ASTM", "AISC"])
    dpi: int = 300  # DPI for PDF to image conversion
    
    def validate(self) -> bool:
        """Validate configuration parameters."""
        if self.min_component_size <= 0:
            return False
        if not 0.0 <= self.confidence_threshold <= 1.0:
            return False
        if self.dpi <= 0:
            return False
        return True


@dataclass
class CLIConfig:
    """Configuration for command-line interface operations."""
    input_files: List[str] = field(default_factory=list)
    output_directory: str = "output"
    batch_mode: bool = False
    verbose: bool = False
    format: str = "csv"  # Future: json, xml
    config_file: Optional[str] = None


@dataclass
class BatchResult:
    """Result of batch processing multiple files."""
    total_files: int
    successful_files: int
    failed_files: int
    processing_time: float
    results: List[ProcessingResult] = field(default_factory=list)
    errors: List[ProcessingError] = field(default_factory=list)