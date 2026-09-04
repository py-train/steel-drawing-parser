"""Configuration models for extensible part type system."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import json
from pathlib import Path


@dataclass
class DetectionParameters:
    """Parameters for component detection algorithms."""
    min_size: int = 50
    confidence_threshold: float = 0.7
    aspect_ratio_range: tuple = (1.0, 10.0)
    angle_tolerance: float = 15.0
    line_grouping_distance: int = 20
    custom_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentTypeConfig:
    """Configuration for a specific component type."""
    name: str
    display_name: str
    description: str
    detection_method: str  # Method name to call for detection
    detection_params: DetectionParameters
    validation_rules: List[str] = field(default_factory=list)
    csv_columns: List[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class PartTypeRegistry:
    """Registry for all configured part types."""
    component_types: Dict[str, ComponentTypeConfig] = field(default_factory=dict)
    default_types: List[str] = field(default_factory=list)
    
    def register_type(self, config: ComponentTypeConfig) -> None:
        """Register a new component type."""
        self.component_types[config.name] = config
    
    def get_type(self, name: str) -> Optional[ComponentTypeConfig]:
        """Get configuration for a component type."""
        return self.component_types.get(name)
    
    def get_enabled_types(self) -> List[ComponentTypeConfig]:
        """Get all enabled component types."""
        return [config for config in self.component_types.values() if config.enabled]
    
    def list_type_names(self) -> List[str]:
        """Get list of all registered type names."""
        return list(self.component_types.keys())
    
    def disable_type(self, name: str) -> bool:
        """Disable a component type."""
        if name in self.component_types:
            self.component_types[name].enabled = False
            return True
        return False
    
    def enable_type(self, name: str) -> bool:
        """Enable a component type."""
        if name in self.component_types:
            self.component_types[name].enabled = True
            return True
        return False


class PartTypeConfigLoader:
    """Loads and manages part type configurations."""
    
    def __init__(self, config_dir: str = "config"):
        """
        Initialize the configuration loader.
        
        Args:
            config_dir: Directory containing configuration files
        """
        self.config_dir = Path(config_dir)
        self.registry = PartTypeRegistry()
        self._load_default_types()
    
    def _load_default_types(self) -> None:
        """Load default component types."""
        # Beam configuration
        beam_config = ComponentTypeConfig(
            name="beam",
            display_name="I-Beam/H-Beam",
            description="Structural steel beams including I-beams and H-beams",
            detection_method="extract_beams",
            detection_params=DetectionParameters(
                min_size=100,
                confidence_threshold=0.7,
                aspect_ratio_range=(3.0, 20.0),
                angle_tolerance=15.0,
                line_grouping_distance=20,
                custom_params={"min_parallel_lines": 2}
            ),
            validation_rules=["check_beam_proportions", "validate_beam_dimensions"],
            csv_columns=["beam_depth", "flange_width", "web_thickness", "flange_thickness"]
        )
        
        # Column configuration
        column_config = ComponentTypeConfig(
            name="column",
            display_name="Structural Column",
            description="Vertical structural columns including HSS and W-shapes",
            detection_method="extract_columns",
            detection_params=DetectionParameters(
                min_size=80,
                confidence_threshold=0.7,
                aspect_ratio_range=(1.5, 8.0),
                angle_tolerance=15.0,
                line_grouping_distance=15,
                custom_params={"min_parallel_lines": 2, "vertical_bias": True}
            ),
            validation_rules=["check_column_proportions", "validate_column_dimensions"],
            csv_columns=["column_depth", "column_width", "wall_thickness"]
        )
        
        # Plate configuration
        plate_config = ComponentTypeConfig(
            name="plate",
            display_name="Steel Plate",
            description="Connection plates, gusset plates, and base plates",
            detection_method="extract_plates",
            detection_params=DetectionParameters(
                min_size=50,
                confidence_threshold=0.6,
                aspect_ratio_range=(1.2, 5.0),
                angle_tolerance=10.0,
                custom_params={"contour_based": True}
            ),
            validation_rules=["check_plate_thickness", "validate_plate_dimensions"],
            csv_columns=["plate_length", "plate_width", "plate_thickness"]
        )
        
        # Bolt configuration
        bolt_config = ComponentTypeConfig(
            name="bolt",
            display_name="Structural Bolt",
            description="High-strength structural bolts",
            detection_method="extract_bolts",
            detection_params=DetectionParameters(
                min_size=10,
                confidence_threshold=0.8,
                custom_params={"circle_detection": True, "min_radius": 5, "max_radius": 50}
            ),
            validation_rules=["check_bolt_size", "validate_bolt_grade"],
            csv_columns=["bolt_diameter", "bolt_length", "bolt_grade"]
        )
        
        # Weld configuration
        weld_config = ComponentTypeConfig(
            name="weld",
            display_name="Structural Weld",
            description="Fillet welds, groove welds, and other connections",
            detection_method="extract_welds",
            detection_params=DetectionParameters(
                min_size=20,
                confidence_threshold=0.6,
                custom_params={"symbol_detection": True, "line_pattern": True}
            ),
            validation_rules=["check_weld_size", "validate_weld_type"],
            csv_columns=["weld_size", "weld_length", "weld_type"]
        )
        
        # Register default types
        for config in [beam_config, column_config, plate_config, bolt_config, weld_config]:
            self.registry.register_type(config)
            self.registry.default_types.append(config.name)
    
    def load_from_file(self, config_file: str) -> bool:
        """
        Load component type configurations from a JSON file.
        
        Args:
            config_file: Path to configuration file
            
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            config_path = self.config_dir / config_file
            if not config_path.exists():
                return False
            
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            for type_data in config_data.get('component_types', []):
                # Parse detection parameters
                params_data = type_data.get('detection_params', {})
                detection_params = DetectionParameters(
                    min_size=params_data.get('min_size', 50),
                    confidence_threshold=params_data.get('confidence_threshold', 0.7),
                    aspect_ratio_range=tuple(params_data.get('aspect_ratio_range', [1.0, 10.0])),
                    angle_tolerance=params_data.get('angle_tolerance', 15.0),
                    line_grouping_distance=params_data.get('line_grouping_distance', 20),
                    custom_params=params_data.get('custom_params', {})
                )
                
                # Create component type configuration
                config = ComponentTypeConfig(
                    name=type_data['name'],
                    display_name=type_data.get('display_name', type_data['name'].title()),
                    description=type_data.get('description', ''),
                    detection_method=type_data['detection_method'],
                    detection_params=detection_params,
                    validation_rules=type_data.get('validation_rules', []),
                    csv_columns=type_data.get('csv_columns', []),
                    enabled=type_data.get('enabled', True)
                )
                
                self.registry.register_type(config)
            
            return True
            
        except Exception as e:
            print(f"Failed to load configuration from {config_file}: {e}")
            return False
    
    def save_to_file(self, config_file: str) -> bool:
        """
        Save current registry to a JSON file.
        
        Args:
            config_file: Path to save configuration
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            config_path = self.config_dir / config_file
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert registry to JSON-serializable format
            config_data = {
                'component_types': [],
                'default_types': self.registry.default_types
            }
            
            for config in self.registry.component_types.values():
                type_data = {
                    'name': config.name,
                    'display_name': config.display_name,
                    'description': config.description,
                    'detection_method': config.detection_method,
                    'detection_params': {
                        'min_size': config.detection_params.min_size,
                        'confidence_threshold': config.detection_params.confidence_threshold,
                        'aspect_ratio_range': list(config.detection_params.aspect_ratio_range),
                        'angle_tolerance': config.detection_params.angle_tolerance,
                        'line_grouping_distance': config.detection_params.line_grouping_distance,
                        'custom_params': config.detection_params.custom_params
                    },
                    'validation_rules': config.validation_rules,
                    'csv_columns': config.csv_columns,
                    'enabled': config.enabled
                }
                config_data['component_types'].append(type_data)
            
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Failed to save configuration to {config_file}: {e}")
            return False
    
    def get_registry(self) -> PartTypeRegistry:
        """Get the current part type registry."""
        return self.registry