"""Core component data models for steel drawing parser."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any


class ComponentType(Enum):
    """Types of steel components that can be extracted."""
    BEAM = "beam"
    COLUMN = "column"
    PLATE = "plate"
    BOLT = "bolt"
    WELD = "weld"


@dataclass
class ComponentDimensions:
    """Dimensions of a steel component."""
    length: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    thickness: Optional[float] = None
    diameter: Optional[float] = None  # For bolts
    unit: str = "mm"  # Default unit: mm, inches, etc.


@dataclass
class MaterialSpec:
    """Material specification for a steel component."""
    grade: Optional[str] = None  # A36, A572, etc.
    yield_strength: Optional[float] = None
    tensile_strength: Optional[float] = None
    specification: Optional[str] = None  # ASTM, etc.


@dataclass
class Coordinates:
    """Location coordinates within a drawing."""
    x: float
    y: float
    page_number: int
    drawing_region: Optional[str] = None


@dataclass
class Component:
    """A steel component extracted from a drawing."""
    id: str
    type: ComponentType
    dimensions: Optional[ComponentDimensions] = None
    material: Optional[MaterialSpec] = None
    location: Optional[Coordinates] = None
    quantity: int = 1
    confidence: float = 0.0
    extraction_metadata: Dict[str, Any] = field(default_factory=dict)