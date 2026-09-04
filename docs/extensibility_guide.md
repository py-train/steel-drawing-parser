# Steel Drawing Parser - Extensibility Guide

## Overview

The Steel Drawing Parser features a plugin-style architecture that allows you to add new component types without modifying the core system. This guide explains how to extend the system with custom component detectors.

## Architecture

The extensibility system consists of several key components:

1. **Configuration System**: JSON-based configuration for component types
2. **Detector Registry**: Plugin registry for component detection algorithms
3. **Base Classes**: Abstract interfaces for implementing custom detectors
4. **Extensible Part Extractor**: Main orchestrator that uses configured detectors

## Adding a Custom Component Type

### Step 1: Create a Custom Detector

Implement the `ComponentDetector` abstract base class:

```python
from src.extractors.component_detector_base import ComponentDetector
from src.models.part_type_config import ComponentTypeConfig
import numpy as np
from typing import List, Dict, Any

class MyCustomDetector(ComponentDetector):
    """Custom detector for my component type."""
    
    def detect(self, image: np.ndarray, **kwargs) -> List[Dict[str, Any]]:
        """
        Detect components in the image.
        
        Returns:
            List of detection dictionaries with:
            - bbox: {'x': int, 'y': int, 'width': int, 'height': int}
            - confidence: float (0.0 to 1.0)
            - component_type: str (matches config name)
            - features: dict (optional additional data)
        """
        detections = []
        
        # Your detection algorithm here
        # Example:
        detection = {
            'bbox': {'x': 100, 'y': 100, 'width': 50, 'height': 50},
            'confidence': 0.8,
            'component_type': self.config.name,
            'features': {'custom_property': 'value'}
        }
        
        if self.validate_detection(detection):
            detections.append(detection)
        
        return detections
    
    def validate_detection(self, detection: Dict[str, Any]) -> bool:
        """Validate a detection result."""
        bbox = detection.get('bbox')
        if not bbox:
            return False
        
        # Check minimum size
        if bbox['width'] < self.params.min_size or bbox['height'] < self.params.min_size:
            return False
        
        # Check confidence threshold
        if detection.get('confidence', 0) < self.params.confidence_threshold:
            return False
        
        # Add custom validation logic here
        
        return True
```

### Step 2: Create Component Configuration

Define the configuration for your component type:

```python
from src.models.part_type_config import ComponentTypeConfig, DetectionParameters

def create_my_component_config() -> ComponentTypeConfig:
    return ComponentTypeConfig(
        name="my_component",
        display_name="My Custom Component",
        description="Description of my custom component type",
        detection_method="extract_my_components",
        detection_params=DetectionParameters(
            min_size=30,
            confidence_threshold=0.7,
            aspect_ratio_range=(1.0, 5.0),
            angle_tolerance=15.0,
            custom_params={
                "custom_param1": "value1",
                "custom_param2": 42
            }
        ),
        validation_rules=[
            "check_my_component_rule1",
            "check_my_component_rule2"
        ],
        csv_columns=[
            "my_dimension1",
            "my_dimension2",
            "my_property"
        ],
        enabled=True
    )
```

### Step 3: Register the Custom Detector

Add your detector to the system:

```python
from src.extractors.extensible_part_extractor import ExtensiblePartExtractor

# Initialize the extractor
extractor = ExtensiblePartExtractor()

# Create configuration
config = create_my_component_config()

# Register the custom detector
extractor.add_custom_detector("my_component", MyCustomDetector, config)

# Now you can use it
components = extractor.detect_steel_components(image, page_number=1)
```

## Configuration File Format

You can also define component types in JSON configuration files:

```json
{
  "component_types": [
    {
      "name": "my_component",
      "display_name": "My Custom Component",
      "description": "Description of my custom component",
      "detection_method": "extract_my_components",
      "detection_params": {
        "min_size": 30,
        "confidence_threshold": 0.7,
        "aspect_ratio_range": [1.0, 5.0],
        "angle_tolerance": 15.0,
        "line_grouping_distance": 20,
        "custom_params": {
          "custom_param1": "value1",
          "custom_param2": 42
        }
      },
      "validation_rules": [
        "check_my_component_rule1",
        "check_my_component_rule2"
      ],
      "csv_columns": [
        "my_dimension1",
        "my_dimension2",
        "my_property"
      ],
      "enabled": true
    }
  ]
}
```

Load the configuration:

```python
extractor = ExtensiblePartExtractor(
    config_dir="my_config_dir",
    config_file="my_components.json"
)
```

## Detection Parameters

The `DetectionParameters` class provides common configuration options:

- **min_size**: Minimum component size in pixels
- **confidence_threshold**: Minimum confidence score (0.0 to 1.0)
- **aspect_ratio_range**: Tuple of (min_ratio, max_ratio) for component proportions
- **angle_tolerance**: Tolerance in degrees for angle-based detection
- **line_grouping_distance**: Maximum distance for grouping parallel lines
- **custom_params**: Dictionary for detector-specific parameters

## Runtime Management

### Enable/Disable Component Types

```python
# Disable a component type
extractor.disable_component_type("my_component")

# Enable a component type
extractor.enable_component_type("my_component")

# Check supported types
supported_types = extractor.get_supported_types()
```

### Get Configuration

```python
# Get configuration for a component type
config = extractor.get_detector_config("my_component")
if config:
    print(f"Display name: {config.display_name}")
    print(f"Min size: {config.detection_params.min_size}")
```

## Best Practices

### 1. Detection Algorithm Design

- **Use OpenCV**: Leverage OpenCV for computer vision operations
- **Multi-stage Detection**: Use coarse-to-fine detection strategies
- **Confidence Scoring**: Provide meaningful confidence scores
- **Feature Extraction**: Extract relevant geometric features

### 2. Validation Logic

- **Size Constraints**: Validate minimum and maximum sizes
- **Aspect Ratios**: Check component proportions
- **Geometric Properties**: Validate shape characteristics
- **Context Awareness**: Consider surrounding elements

### 3. Configuration Management

- **Reasonable Defaults**: Provide sensible default parameters
- **Parameter Documentation**: Document custom parameters
- **Validation Rules**: Define clear validation criteria
- **CSV Columns**: Specify relevant output attributes

### 4. Error Handling

- **Graceful Degradation**: Handle detection failures gracefully
- **Logging**: Use the provided logger for debugging
- **Exception Safety**: Catch and handle exceptions appropriately

## Example: Angle Bracket Detector

See `examples/custom_component_example.py` for a complete example of implementing a custom angle bracket detector.

## Integration with Web Interface

Custom component types automatically integrate with the web interface:

1. **Detection**: Custom detectors run as part of the processing pipeline
2. **Results**: Custom components appear in results summaries
3. **CSV Output**: Custom CSV columns are included in downloads
4. **Configuration**: Component types can be enabled/disabled via configuration

## Testing Custom Detectors

Create unit tests for your custom detectors:

```python
import pytest
from your_detector import MyCustomDetector
from src.models.part_type_config import ComponentTypeConfig, DetectionParameters

def test_my_custom_detector():
    config = ComponentTypeConfig(
        name="test_component",
        display_name="Test Component",
        description="Test",
        detection_method="test",
        detection_params=DetectionParameters()
    )
    
    detector = MyCustomDetector(config)
    
    # Create test image
    test_image = create_test_image()
    
    # Test detection
    detections = detector.detect(test_image)
    
    # Validate results
    assert len(detections) >= 0
    for detection in detections:
        assert detector.validate_detection(detection)
```

## Troubleshooting

### Common Issues

1. **No Detections**: Check confidence thresholds and validation logic
2. **Import Errors**: Ensure proper Python path configuration
3. **Configuration Errors**: Validate JSON syntax and parameter types
4. **Performance Issues**: Optimize detection algorithms for large images

### Debugging Tips

1. **Enable Debug Logging**: Set log level to DEBUG
2. **Visualize Detections**: Draw bounding boxes on test images
3. **Parameter Tuning**: Experiment with detection parameters
4. **Unit Testing**: Test individual components in isolation

## Future Enhancements

The extensibility system is designed to support future enhancements:

- **Machine Learning Integration**: Support for ML-based detectors
- **Multi-scale Detection**: Hierarchical component detection
- **Semantic Understanding**: Context-aware component relationships
- **Performance Optimization**: GPU acceleration and parallel processing