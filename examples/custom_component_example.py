#!/usr/bin/env python3
"""
Example of how to add a custom component type to the Steel Drawing Parser.

This example shows how to:
1. Create a custom detector for a new component type (angle brackets)
2. Register the detector with the extensible system
3. Use the custom detector in the processing pipeline
"""

import sys
from pathlib import Path
import numpy as np
from typing import List, Dict, Any, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extractors.component_detector_base import ComponentDetector
from src.extractors.extensible_part_extractor import ExtensiblePartExtractor
from src.models.part_type_config import ComponentTypeConfig, DetectionParameters


class AngleBracketDetector(ComponentDetector):
    """Custom detector for angle brackets (L-shaped steel components)."""
    
    def detect(self, image: np.ndarray, **kwargs) -> List[Dict[str, Any]]:
        """
        Detect angle brackets using corner detection and line analysis.
        
        This is a simplified implementation for demonstration purposes.
        A real implementation would use more sophisticated computer vision techniques.
        """
        try:
            import cv2
            detections = []
            
            # Detect corners using Harris corner detection
            corners = cv2.cornerHarris(image, 2, 3, 0.04)
            corners = cv2.dilate(corners, None)
            
            # Find corner locations
            corner_locations = np.where(corners > 0.01 * corners.max())
            
            # Group nearby corners that might form angle brackets
            for i, (y, x) in enumerate(zip(corner_locations[0], corner_locations[1])):
                # Define a region around the corner
                region_size = self.params.custom_params.get('region_size', 50)
                x1, y1 = max(0, x - region_size), max(0, y - region_size)
                x2, y2 = min(image.shape[1], x + region_size), min(image.shape[0], y + region_size)
                
                # Extract region
                region = image[y1:y2, x1:x2]
                
                # Analyze the region for L-shaped patterns
                if self._is_angle_bracket_region(region):
                    detection = {
                        'bbox': {
                            'x': x1,
                            'y': y1,
                            'width': x2 - x1,
                            'height': y2 - y1
                        },
                        'confidence': self._calculate_angle_confidence(region),
                        'component_type': self.config.name,
                        'features': {
                            'corner_x': x,
                            'corner_y': y,
                            'region_size': region_size,
                            'angle_type': 'L-bracket'
                        }
                    }
                    
                    if self.validate_detection(detection):
                        detections.append(detection)
            
            self.logger.debug(f"Found {len(detections)} angle bracket detections")
            return detections
            
        except Exception as e:
            self.logger.error(f"Angle bracket detection failed: {e}")
            return []
    
    def validate_detection(self, detection: Dict[str, Any]) -> bool:
        """Validate angle bracket detection."""
        bbox = detection.get('bbox')
        if not bbox:
            return False
        
        # Check minimum size
        if bbox['width'] < self.params.min_size or bbox['height'] < self.params.min_size:
            return False
        
        # Check confidence
        if detection.get('confidence', 0) < self.params.confidence_threshold:
            return False
        
        # Angle brackets should be roughly square (not too elongated)
        aspect_ratio = max(bbox['width'], bbox['height']) / min(bbox['width'], bbox['height'])
        if aspect_ratio > 3.0:  # Too elongated
            return False
        
        return True
    
    def _is_angle_bracket_region(self, region: np.ndarray) -> bool:
        """
        Check if a region contains an L-shaped pattern.
        
        This is a simplified heuristic - a real implementation would be more sophisticated.
        """
        if region.size == 0:
            return False
        
        # Look for perpendicular lines meeting at a corner
        import cv2
        
        # Detect edges
        edges = cv2.Canny(region, 50, 150)
        
        # Detect lines
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=20, 
                               minLineLength=10, maxLineGap=5)
        
        if lines is None or len(lines) < 2:
            return False
        
        # Check for perpendicular lines
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
            angles.append(angle)
        
        # Look for approximately perpendicular angles (90 degrees apart)
        for i, angle1 in enumerate(angles):
            for angle2 in angles[i+1:]:
                angle_diff = abs(angle1 - angle2)
                if 80 <= angle_diff <= 100 or 260 <= angle_diff <= 280:
                    return True
        
        return False
    
    def _calculate_angle_confidence(self, region: np.ndarray) -> float:
        """Calculate confidence score for angle bracket detection."""
        if region.size == 0:
            return 0.0
        
        # Simple confidence based on edge density and corner strength
        import cv2
        
        edges = cv2.Canny(region, 50, 150)
        edge_density = np.sum(edges > 0) / edges.size
        
        # Higher edge density in a small region suggests a structural component
        confidence = min(0.9, 0.3 + edge_density * 2.0)
        
        return confidence


def create_custom_angle_bracket_config() -> ComponentTypeConfig:
    """Create configuration for angle bracket detection."""
    return ComponentTypeConfig(
        name="angle_bracket",
        display_name="Angle Bracket",
        description="L-shaped steel angle brackets and structural angles",
        detection_method="extract_angle_brackets",
        detection_params=DetectionParameters(
            min_size=30,
            confidence_threshold=0.6,
            aspect_ratio_range=(0.5, 3.0),
            angle_tolerance=10.0,
            custom_params={
                "region_size": 50,
                "corner_threshold": 0.01,
                "perpendicular_tolerance": 10.0
            }
        ),
        validation_rules=[
            "check_angle_dimensions",
            "validate_perpendicular_legs"
        ],
        csv_columns=[
            "leg1_length",
            "leg2_length",
            "thickness",
            "angle_type"
        ],
        enabled=True
    )


def demonstrate_custom_detector():
    """Demonstrate how to use a custom detector."""
    print("🔧 Steel Drawing Parser - Custom Component Type Example")
    print("=" * 60)
    
    try:
        # Create the extensible part extractor
        print("1. Initializing extensible part extractor...")
        extractor = ExtensiblePartExtractor(config_dir="config")
        
        print(f"   Default supported types: {extractor.get_supported_types()}")
        
        # Create custom angle bracket configuration
        print("\n2. Creating custom angle bracket detector...")
        angle_config = create_custom_angle_bracket_config()
        
        # Add the custom detector
        extractor.add_custom_detector("angle_bracket", AngleBracketDetector, angle_config)
        
        print(f"   Updated supported types: {extractor.get_supported_types()}")
        
        # Create a test image with some basic shapes
        print("\n3. Creating test image...")
        test_image = np.zeros((300, 400), dtype=np.uint8)
        
        # Draw an L-shaped pattern (angle bracket)
        test_image[100:120, 50:150] = 255  # Horizontal leg
        test_image[100:200, 50:70] = 255   # Vertical leg
        
        # Draw some other shapes for comparison
        test_image[50:70, 200:350] = 255   # Horizontal line (beam)
        test_image[150:250, 300:320] = 255 # Vertical line (column)
        
        print("   Test image created with L-shaped pattern")
        
        # Run detection
        print("\n4. Running component detection...")
        components = extractor.detect_steel_components(test_image, page_number=1)
        
        print(f"   Detected {len(components)} components:")
        for component in components:
            print(f"   - {component.type.value}: {component.id} "
                  f"(confidence: {component.confidence:.2f}, quantity: {component.quantity})")
            if hasattr(component, 'attributes') and component.attributes:
                print(f"     Features: {component.attributes}")
        
        # Demonstrate configuration management
        print("\n5. Demonstrating configuration management...")
        
        # Get configuration for the custom type
        config = extractor.get_detector_config("angle_bracket")
        if config:
            print(f"   Angle bracket config: {config.display_name}")
            print(f"   Min size: {config.detection_params.min_size}")
            print(f"   Confidence threshold: {config.detection_params.confidence_threshold}")
        
        # Disable and re-enable the custom type
        print("\n6. Testing enable/disable functionality...")
        print(f"   Before disable: {extractor.get_supported_types()}")
        
        extractor.disable_component_type("angle_bracket")
        print(f"   After disable: {extractor.get_supported_types()}")
        
        extractor.enable_component_type("angle_bracket")
        print(f"   After re-enable: {extractor.get_supported_types()}")
        
        print("\n✅ Custom detector demonstration completed successfully!")
        print("\n📝 Key Features Demonstrated:")
        print("   • Custom detector implementation")
        print("   • Configuration-based component registration")
        print("   • Runtime enable/disable of component types")
        print("   • Integration with existing processing pipeline")
        print("   • Extensible CSV output columns")
        
    except Exception as e:
        print(f"❌ Error during demonstration: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    demonstrate_custom_detector()