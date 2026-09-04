"""Processing result and validation models."""

from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict
from .component import Component


@dataclass
class ProcessingError:
    """Represents an error that occurred during processing."""
    message: str
    error_type: str
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[str] = None


@dataclass
class ValidationIssue:
    """Represents a validation issue found in extracted data."""
    component_id: str
    issue_type: str
    description: str
    severity: str  # "warning", "error", "info"
    suggested_fix: Optional[str] = None


@dataclass
class ProcessingStats:
    """Statistics about the processing operation."""
    total_pages: int = 0
    components_found: int = 0
    components_with_dimensions: int = 0
    components_with_materials: int = 0
    average_confidence: float = 0.0
    processing_time_seconds: float = 0.0


@dataclass
class ProcessingResult:
    """Result of processing a PDF file."""
    success: bool
    components: List[Component] = field(default_factory=list)
    processing_time: float = 0.0
    pages_processed: int = 0
    errors: List[ProcessingError] = field(default_factory=list)
    summary_stats: Optional[ProcessingStats] = None


@dataclass
class ValidationResult:
    """Result of validating extracted component data."""
    is_valid: bool
    confidence: float
    issues: List[ValidationIssue] = field(default_factory=list)
    suggested_corrections: List[str] = field(default_factory=list)