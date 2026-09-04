"""Tests for dimension and material extraction."""

import pytest
import numpy as np
import cv2
from unittest.mock import Mock, patch

from src.extractors.dimension_extractor import DimensionExtractor, TextRegion, DimensionAnnotation
from src.models.component import Component, ComponentType, ComponentDimensions, MaterialSpec, Coordinates
from src.processors.image_extractor import BoundingBox


class TestTextRegion:
    """Test cases for TextRegion data model."""
    
    def test_text_region_creation(self):
        """Test TextRegion object creation."""
        bbox = BoundingBox(10, 20, 100, 30)
        text_region = TextRegion(
            bbox=bbox,
            text="300mm",
            confidence=0.9,
            font_size=12.0
        )
        
        assert text_region.bbox == bbox
        assert text_region.text == "300mm"
        assert text_region.confidence == 0.9
        assert text_region.font_size == 12.0


class TestDimensionAnnotation:
    """Test cases for DimensionAnnotation data model."""
    
    def test_dimension_annotation_creation(self):
        """Test DimensionAnnotation object creation."""
        annotation = DimensionAnnotation(
            value=300.0,
            unit="mm",
            direction="horizontal",
            location=(100, 200),
            confidence=0.8
        )
        
        assert annotation.value == 300.0
        assert annotation.unit == "mm"
        assert annotation.direction == "horizontal"
        assert annotation.location == (100, 200)
        assert annotation.confidence == 0.8


class TestDimensionExtractor:
    """Test cases for dimension extractor."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.extractor = DimensionExtractor()
    
    def create_test_component(self) -> Component:
        """Create a test component with metadata."""
        return Component(
            id="test_beam_001",
            type=ComponentType.BEAM,
            location=Coordinates(x=200, y=150, page_number=1),
            extraction_metadata={
                'bbox': {'x': 100, 'y': 100, 'width': 200, 'height': 50}
            }
        )
    
    def create_test_image_with_text(self) -> np.ndarray:
        """Create test image with text-like regions."""
        image = np.ones((400, 600), dtype=np.uint8) * 255  # White background
        
        # Add some text-like rectangular regions (simulating text)
        cv2.rectangle(image, (150, 80), (250, 95), 0, -1)   # "300mm" above beam
        cv2.rectangle(image, (320, 120), (380, 135), 0, -1)  # "W12x26" beside beam
        cv2.rectangle(image, (100, 180), (180, 195), 0, -1)  # "A36" below beam
        
        return image
    
    def test_get_component_bbox(self):
        """Test extracting bounding box from component metadata."""
        component = self.create_test_component()
        bbox = self.extractor._get_component_bbox(component)
        
        assert bbox is not None
        assert bbox.x == 100
        assert bbox.y == 100
        assert bbox.width == 200
        assert bbox.height == 50
    
    def test_get_component_bbox_missing_metadata(self):
        """Test handling component without bbox metadata."""
        component = Component(id="test", type=ComponentType.BEAM)
        bbox = self.extractor._get_component_bbox(component)
        
        assert bbox is None
    
    def test_expand_bbox(self):
        """Test bounding box expansion."""
        original_bbox = BoundingBox(100, 100, 200, 50)
        image_shape = (400, 600)
        
        expanded = self.extractor._expand_bbox(original_bbox, image_shape, expansion=25)
        
        assert expanded.x == 75  # 100 - 25
        assert expanded.y == 75  # 100 - 25
        assert expanded.width == 250  # 200 + 2*25
        assert expanded.height == 100  # 50 + 2*25
    
    def test_expand_bbox_boundary_clipping(self):
        """Test bbox expansion with boundary clipping."""
        # Bbox near image edge
        original_bbox = BoundingBox(10, 10, 50, 50)
        image_shape = (100, 100)
        
        expanded = self.extractor._expand_bbox(original_bbox, image_shape, expansion=20)
        
        assert expanded.x == 0  # Clipped to 0
        assert expanded.y == 0  # Clipped to 0
        assert expanded.width <= 100  # Within image bounds
        assert expanded.height <= 100  # Within image bounds
    
    def test_extract_region(self):
        """Test image region extraction."""
        image = np.random.randint(0, 255, (200, 300), dtype=np.uint8)
        bbox = BoundingBox(50, 30, 100, 80)
        
        region = self.extractor._extract_region(image, bbox)
        
        assert region.shape == (80, 100)  # height, width
        assert np.array_equal(region, image[30:110, 50:150])
    
    def test_find_text_regions(self):
        """Test text region detection."""
        test_image = self.create_test_image_with_text()
        
        text_regions = self.extractor._find_text_regions(test_image)
        
        # Should find some text regions
        assert len(text_regions) >= 1
        assert all(isinstance(region, TextRegion) for region in text_regions)
        assert all(region.confidence > 0 for region in text_regions)
        assert all(len(region.text) > 0 for region in text_regions)
    
    def test_simulate_ocr(self):
        """Test OCR simulation."""
        # Create different shaped text regions
        wide_region = np.zeros((10, 50), dtype=np.uint8)  # Wide region
        tall_region = np.zeros((50, 10), dtype=np.uint8)  # Tall region
        square_region = np.zeros((20, 20), dtype=np.uint8)  # Square region
        
        wide_text = self.extractor._simulate_ocr(wide_region)
        tall_text = self.extractor._simulate_ocr(tall_region)
        square_text = self.extractor._simulate_ocr(square_region)
        
        # Should return some text for all regions
        assert isinstance(wide_text, str) and len(wide_text) > 0
        assert isinstance(tall_text, str) and len(tall_text) > 0
        assert isinstance(square_text, str) and len(square_text) > 0
    
    def test_parse_dimension_text(self):
        """Test dimension parsing from text."""
        bbox = BoundingBox(100, 100, 50, 20)
        text_region = TextRegion(bbox=bbox, text="300mm", confidence=0.9)
        
        annotations = self.extractor._parse_dimension_text(text_region)
        
        assert len(annotations) >= 1
        annotation = annotations[0]
        assert annotation.value == 300.0
        assert annotation.unit == "mm"
        assert annotation.confidence == 0.9
    
    def test_parse_dimension_text_multiple_formats(self):
        """Test parsing various dimension formats."""
        test_cases = [
            ("300mm", 300.0, "mm"),
            ("12in", 12.0, "in"),
            ("5ft", 5.0, "ft"),
            ("2.5m", 2.5, "m"),
            ('8"', 8.0, "in"),
        ]
        
        for text, expected_value, expected_unit in test_cases:
            bbox = BoundingBox(0, 0, 50, 20)
            text_region = TextRegion(bbox=bbox, text=text, confidence=0.9)
            
            annotations = self.extractor._parse_dimension_text(text_region)
            
            assert len(annotations) >= 1, f"Failed to parse '{text}'"
            annotation = annotations[0]
            assert annotation.value == expected_value, f"Wrong value for '{text}'"
            assert annotation.unit == expected_unit, f"Wrong unit for '{text}'"
    
    def test_parse_dimension_text_width_height(self):
        """Test parsing width x height format."""
        bbox = BoundingBox(100, 100, 80, 20)
        text_region = TextRegion(bbox=bbox, text="100 x 50", confidence=0.9)
        
        annotations = self.extractor._parse_dimension_text(text_region)
        
        assert len(annotations) == 2
        # Should have both horizontal and vertical dimensions
        directions = [a.direction for a in annotations]
        assert 'horizontal' in directions
        assert 'vertical' in directions
        
        values = [a.value for a in annotations]
        assert 100.0 in values
        assert 50.0 in values
    
    def test_parse_material_text(self):
        """Test material specification parsing."""
        bbox = BoundingBox(100, 100, 50, 20)
        text_region = TextRegion(bbox=bbox, text="W12x26", confidence=0.9)
        
        specs = self.extractor._parse_material_text(text_region)
        
        assert len(specs) >= 1
        spec = specs[0]
        assert 'W12x26' in spec['match']
        assert spec['confidence'] == 0.9
    
    def test_parse_material_text_multiple_formats(self):
        """Test parsing various material formats."""
        test_cases = [
            "W12x26",    # Wide flange
            "A36",       # ASTM grade
            "Grade 50",  # Grade specification
            "Fy = 36",   # Yield strength
        ]
        
        for text in test_cases:
            bbox = BoundingBox(0, 0, 50, 20)
            text_region = TextRegion(bbox=bbox, text=text, confidence=0.9)
            
            specs = self.extractor._parse_material_text(text_region)
            
            assert len(specs) >= 1, f"Failed to parse material '{text}'"
    
    def test_extract_unit(self):
        """Test unit extraction from matched text."""
        import re
        
        test_cases = [
            ("300mm", "mm"),
            ("12in", "in"),
            ('8"', "in"),
            ("5ft", "ft"),
            ("2.5m", "m"),
        ]
        
        for text, expected_unit in test_cases:
            # Create a mock match object
            pattern = r'(\d+(?:\.\d+)?)\s*(?:mm|in|"|ft|m)'
            match = re.search(pattern, text, re.IGNORECASE)
            
            if match:
                unit = self.extractor._extract_unit(text, match)
                assert unit == expected_unit, f"Wrong unit for '{text}': got '{unit}', expected '{expected_unit}'"
    
    def test_infer_dimension_direction(self):
        """Test dimension direction inference."""
        # Wide text region (horizontal dimension)
        wide_bbox = BoundingBox(0, 0, 100, 20)
        wide_region = TextRegion(bbox=wide_bbox, text="300mm", confidence=0.9)
        
        # Tall text region (vertical dimension)
        tall_bbox = BoundingBox(0, 0, 20, 100)
        tall_region = TextRegion(bbox=tall_bbox, text="150mm", confidence=0.9)
        
        # Square text region (diagonal/unknown)
        square_bbox = BoundingBox(0, 0, 50, 50)
        square_region = TextRegion(bbox=square_bbox, text="100mm", confidence=0.9)
        
        assert self.extractor._infer_dimension_direction(wide_region) == "horizontal"
        assert self.extractor._infer_dimension_direction(tall_region) == "vertical"
        assert self.extractor._infer_dimension_direction(square_region) == "diagonal"
    
    def test_create_component_dimensions(self):
        """Test ComponentDimensions creation from annotations."""
        annotations = [
            DimensionAnnotation(300.0, "mm", "horizontal", (100, 100), 0.9),
            DimensionAnnotation(150.0, "mm", "vertical", (100, 100), 0.8),
        ]
        
        dimensions = self.extractor._create_component_dimensions(annotations, ComponentType.BEAM)
        
        assert dimensions.width == 300.0
        assert dimensions.height == 150.0
        assert dimensions.unit == "mm"
    
    def test_create_component_dimensions_empty(self):
        """Test ComponentDimensions creation with no annotations."""
        dimensions = self.extractor._create_component_dimensions([], ComponentType.BEAM)
        
        assert isinstance(dimensions, ComponentDimensions)
        assert dimensions.width is None
        assert dimensions.height is None
    
    def test_create_material_spec(self):
        """Test MaterialSpec creation from parsed specifications."""
        specs = [
            {
                'pattern': r'W(\d+)x(\d+)',
                'match': 'W12x26',
                'groups': ('12', '26'),
                'confidence': 0.9
            },
            {
                'pattern': r'A(\d+)',
                'match': 'A36',
                'groups': ('36',),
                'confidence': 0.8
            }
        ]
        
        material_spec = self.extractor._create_material_spec(specs)
        
        assert material_spec.grade in ['W12x26', 'A36']
        assert material_spec.specification in ['AISC', 'ASTM']
    
    def test_extract_dimensions_integration(self):
        """Test complete dimension extraction workflow."""
        component = self.create_test_component()
        test_image = self.create_test_image_with_text()
        
        dimensions = self.extractor.extract_dimensions(component, test_image)
        
        assert isinstance(dimensions, ComponentDimensions)
        # Should return some dimensions or at least not crash
    
    def test_extract_material_specs_integration(self):
        """Test complete material specification extraction workflow."""
        component = self.create_test_component()
        test_image = self.create_test_image_with_text()
        
        material_spec = self.extractor.extract_material_specs(component, test_image)
        
        assert isinstance(material_spec, MaterialSpec)
        # Should return some material spec or at least not crash
    
    def test_error_handling_invalid_component(self):
        """Test error handling with invalid component."""
        component = Component(id="invalid", type=ComponentType.BEAM)  # No metadata
        test_image = np.ones((100, 100), dtype=np.uint8) * 255
        
        # Should not crash and return default dimensions
        dimensions = self.extractor.extract_dimensions(component, test_image)
        material_spec = self.extractor.extract_material_specs(component, test_image)
        
        assert isinstance(dimensions, ComponentDimensions)
        assert isinstance(material_spec, MaterialSpec)
    
    def test_error_handling_invalid_image(self):
        """Test error handling with invalid image."""
        component = self.create_test_component()
        
        # Should not crash with None image
        dimensions = self.extractor.extract_dimensions(component, None)
        material_spec = self.extractor.extract_material_specs(component, None)
        
        assert isinstance(dimensions, ComponentDimensions)
        assert isinstance(material_spec, MaterialSpec)