"""Tests for steel component part extractor."""

import pytest
import numpy as np
import cv2
from unittest.mock import Mock

from src.extractors.part_extractor import PartExtractor, DetectionCandidate
from src.models.component import ComponentType, Component, ComponentDimensions, MaterialSpec, Coordinates
from src.processors.image_extractor import BoundingBox


class TestDetectionCandidate:
    """Test cases for DetectionCandidate data model."""
    
    def test_detection_candidate_creation(self):
        """Test DetectionCandidate object creation."""
        bbox = BoundingBox(10, 20, 100, 50, 0.8)
        features = {'test_feature': 'value'}
        
        candidate = DetectionCandidate(
            bbox=bbox,
            component_type=ComponentType.BEAM,
            confidence=0.9,
            features=features
        )
        
        assert candidate.bbox == bbox
        assert candidate.component_type == ComponentType.BEAM
        assert candidate.confidence == 0.9
        assert candidate.features == features
        assert candidate.contour is None


class TestPartExtractor:
    """Test cases for part extractor."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.extractor = PartExtractor(min_component_size=30, confidence_threshold=0.5)
    
    def create_test_image_with_beam(self) -> np.ndarray:
        """Create test image with horizontal beam-like structure."""
        image = np.ones((400, 600), dtype=np.uint8) * 255  # White background
        
        # Draw horizontal beam (two parallel lines)
        cv2.line(image, (100, 150), (400, 150), 0, 2)  # Top flange
        cv2.line(image, (100, 170), (400, 170), 0, 2)  # Bottom flange
        cv2.line(image, (250, 150), (250, 170), 0, 2)  # Web (vertical connection)
        
        return image
    
    def create_test_image_with_column(self) -> np.ndarray:
        """Create test image with vertical column-like structure."""
        image = np.ones((400, 600), dtype=np.uint8) * 255  # White background
        
        # Draw vertical column (two parallel vertical lines)
        cv2.line(image, (200, 50), (200, 350), 0, 2)   # Left flange
        cv2.line(image, (220, 50), (220, 350), 0, 2)   # Right flange
        cv2.line(image, (200, 200), (220, 200), 0, 2)  # Web (horizontal connection)
        
        return image
    
    def create_test_image_with_plate(self) -> np.ndarray:
        """Create test image with rectangular plate."""
        image = np.ones((400, 600), dtype=np.uint8) * 255  # White background
        
        # Draw filled rectangle (plate)
        cv2.rectangle(image, (150, 100), (350, 200), 0, -1)
        
        return image
    
    def create_test_image_with_bolts(self) -> np.ndarray:
        """Create test image with circular bolts."""
        image = np.ones((400, 600), dtype=np.uint8) * 255  # White background
        
        # Draw filled circles (bolts) - make them larger and more distinct
        cv2.circle(image, (200, 150), 12, 0, -1)  # Larger radius
        cv2.circle(image, (250, 150), 12, 0, -1)
        cv2.circle(image, (300, 150), 12, 0, -1)
        
        # Add some contrast around the circles
        cv2.circle(image, (200, 150), 15, 128, 2)  # Gray outline
        cv2.circle(image, (250, 150), 15, 128, 2)
        cv2.circle(image, (300, 150), 15, 128, 2)
        
        return image
    
    def create_complex_test_image(self) -> np.ndarray:
        """Create test image with multiple component types."""
        image = np.ones((500, 700), dtype=np.uint8) * 255  # White background
        
        # Horizontal beam
        cv2.line(image, (100, 150), (400, 150), 0, 2)
        cv2.line(image, (100, 170), (400, 170), 0, 2)
        
        # Vertical column
        cv2.line(image, (200, 50), (200, 300), 0, 2)
        cv2.line(image, (220, 50), (220, 300), 0, 2)
        
        # Plate
        cv2.rectangle(image, (450, 100), (600, 200), 0, -1)
        
        # Bolts
        cv2.circle(image, (500, 250), 6, 0, -1)
        cv2.circle(image, (550, 250), 6, 0, -1)
        
        return image
    
    def test_detect_steel_components_empty_image(self):
        """Test component detection on empty image."""
        empty_image = np.ones((200, 300), dtype=np.uint8) * 255
        
        components = self.extractor.detect_steel_components(empty_image)
        
        # Should return empty list for blank image
        assert isinstance(components, list)
        assert len(components) == 0
    
    def test_extract_beams_horizontal_lines(self):
        """Test beam extraction from image with horizontal lines."""
        test_image = self.create_test_image_with_beam()
        
        candidates = self.extractor.extract_beams(test_image)
        
        # Should detect at least one beam candidate
        assert len(candidates) >= 1
        assert all(isinstance(c, DetectionCandidate) for c in candidates)
        assert all(c.component_type == ComponentType.BEAM for c in candidates)
        assert all(c.confidence > 0 for c in candidates)
    
    def test_extract_columns_vertical_lines(self):
        """Test column extraction from image with vertical lines."""
        test_image = self.create_test_image_with_column()
        
        candidates = self.extractor.extract_columns(test_image)
        
        # Should detect at least one column candidate
        assert len(candidates) >= 1
        assert all(isinstance(c, DetectionCandidate) for c in candidates)
        assert all(c.component_type == ComponentType.COLUMN for c in candidates)
        assert all(c.confidence > 0 for c in candidates)
    
    def test_extract_plates_rectangular_shapes(self):
        """Test plate extraction from image with rectangular shapes."""
        test_image = self.create_test_image_with_plate()
        
        candidates = self.extractor.extract_plates(test_image)
        
        # Should detect at least one plate candidate
        assert len(candidates) >= 1
        assert all(isinstance(c, DetectionCandidate) for c in candidates)
        assert all(c.component_type == ComponentType.PLATE for c in candidates)
        assert all(c.confidence > 0 for c in candidates)
    
    def test_extract_connections_circular_shapes(self):
        """Test connection extraction from image with circular shapes."""
        test_image = self.create_test_image_with_bolts()
        
        candidates = self.extractor.extract_connections(test_image)
        
        # Should detect bolt candidates
        assert len(candidates) >= 1
        assert all(isinstance(c, DetectionCandidate) for c in candidates)
        assert all(c.component_type == ComponentType.BOLT for c in candidates)
        assert all(c.confidence > 0 for c in candidates)
    
    def test_detect_steel_components_complex_image(self):
        """Test complete detection pipeline on complex image."""
        test_image = self.create_complex_test_image()
        
        components = self.extractor.detect_steel_components(test_image, page_number=1)
        
        # Should detect multiple components
        assert len(components) >= 2
        assert all(isinstance(c, Component) for c in components)
        
        # Check that different component types are detected
        component_types = {c.type for c in components}
        assert len(component_types) >= 2  # Should have at least 2 different types
        
        # Verify component properties
        for component in components:
            assert component.id is not None
            assert component.confidence > 0
            assert component.location is not None
            assert component.location.page_number == 1
            assert component.dimensions is not None
    
    def test_confidence_threshold_filtering(self):
        """Test that confidence threshold filters out low-confidence detections."""
        # Create extractor with high confidence threshold
        high_threshold_extractor = PartExtractor(confidence_threshold=0.9)
        
        test_image = self.create_test_image_with_beam()
        
        # Should detect fewer components with high threshold
        components_high = high_threshold_extractor.detect_steel_components(test_image)
        components_low = self.extractor.detect_steel_components(test_image)
        
        # High threshold should result in fewer or equal detections
        assert len(components_high) <= len(components_low)
    
    def test_min_component_size_filtering(self):
        """Test that minimum size filtering works."""
        # Create extractor with large minimum size
        large_size_extractor = PartExtractor(min_component_size=200)
        
        test_image = self.create_test_image_with_bolts()  # Small circular components
        
        components = large_size_extractor.detect_steel_components(test_image)
        
        # Should detect fewer or no small components
        assert len(components) == 0 or all(
            c.dimensions.width >= 200 or c.dimensions.height >= 200 
            for c in components
        )
    
    def test_group_parallel_lines(self):
        """Test parallel line grouping functionality."""
        # Create test lines
        lines = [
            {'line': [100, 150, 400, 150], 'length': 300, 'midpoint': (250, 150)},
            {'line': [100, 170, 400, 170], 'length': 300, 'midpoint': (250, 170)},
            {'line': [100, 300, 400, 300], 'length': 300, 'midpoint': (250, 300)},
        ]
        
        groups = self.extractor._group_parallel_lines(lines, max_distance=25)
        
        # Should group the first two lines together (they're close)
        assert len(groups) >= 1
        
        # Find the group with the most lines
        largest_group = max(groups, key=len)
        assert len(largest_group) >= 2
    
    def test_non_maximum_suppression(self):
        """Test non-maximum suppression removes overlapping detections."""
        # Create overlapping candidates
        bbox1 = BoundingBox(100, 100, 50, 50, 0.9)
        bbox2 = BoundingBox(110, 110, 50, 50, 0.7)  # Overlapping with bbox1
        bbox3 = BoundingBox(200, 200, 50, 50, 0.8)  # Non-overlapping
        
        candidates = [
            DetectionCandidate(bbox1, ComponentType.BEAM, 0.9, {}),
            DetectionCandidate(bbox2, ComponentType.BEAM, 0.7, {}),
            DetectionCandidate(bbox3, ComponentType.BEAM, 0.8, {})
        ]
        
        filtered = self.extractor._apply_non_maximum_suppression(candidates, overlap_threshold=0.1)
        
        # Should keep the higher confidence detection and the non-overlapping one
        assert len(filtered) == 2
        confidences = [c.confidence for c in filtered]
        assert 0.9 in confidences  # Highest confidence kept
        assert 0.8 in confidences  # Non-overlapping kept
        assert 0.7 not in confidences  # Lower confidence overlapping suppressed
    
    def test_bbox_overlap_calculation(self):
        """Test bounding box overlap calculation."""
        bbox1 = BoundingBox(0, 0, 100, 100)
        bbox2 = BoundingBox(50, 50, 100, 100)  # 50% overlap
        bbox3 = BoundingBox(200, 200, 100, 100)  # No overlap
        
        overlap_50 = self.extractor._calculate_bbox_overlap(bbox1, bbox2)
        overlap_0 = self.extractor._calculate_bbox_overlap(bbox1, bbox3)
        
        # Intersection is 50x50 = 2500, Union is 10000 + 10000 - 2500 = 17500
        # So overlap should be 2500/17500 ≈ 0.143
        assert 0.1 < overlap_50 < 0.2  # Should be around 14%
        assert overlap_0 == 0.0
    
    def test_candidate_to_component_conversion(self):
        """Test conversion from detection candidate to component."""
        bbox = BoundingBox(100, 150, 200, 50, 0.8)
        features = {'test_feature': 'value'}
        
        candidate = DetectionCandidate(
            bbox=bbox,
            component_type=ComponentType.BEAM,
            confidence=0.8,
            features=features
        )
        
        component = self.extractor._candidate_to_component(candidate, page_number=2)
        
        assert component is not None
        assert isinstance(component, Component)
        assert component.type == ComponentType.BEAM
        assert component.confidence == 0.8
        assert component.location.page_number == 2
        assert component.location.x == bbox.center[0]
        assert component.location.y == bbox.center[1]
        assert component.dimensions.width == bbox.width
        assert component.dimensions.height == bbox.height
        assert 'detection_features' in component.extraction_metadata
    
    def test_error_handling_invalid_image(self):
        """Test error handling with invalid image input."""
        # Test with None
        components = self.extractor.detect_steel_components(None)
        assert components == []
        
        # Test with empty array
        empty_array = np.array([])
        components = self.extractor.detect_steel_components(empty_array)
        assert components == []
    
    def test_component_id_uniqueness(self):
        """Test that generated component IDs are unique."""
        test_image = self.create_complex_test_image()
        
        components = self.extractor.detect_steel_components(test_image)
        
        if len(components) > 1:
            component_ids = [c.id for c in components]
            assert len(component_ids) == len(set(component_ids))  # All IDs should be unique
    
    def test_quantity_counting_similar_components(self):
        """Test quantity counting for similar components."""
        # Create image with multiple similar bolts
        image = np.ones((400, 600), dtype=np.uint8) * 255
        
        # Draw multiple identical circles (bolts)
        positions = [(150, 150), (200, 150), (250, 150), (300, 150)]
        for pos in positions:
            cv2.circle(image, pos, 12, 0, -1)
            cv2.circle(image, pos, 15, 128, 2)  # Gray outline
        
        components = self.extractor.detect_steel_components(image)
        
        # Should group similar bolts together
        bolt_components = [c for c in components if c.type == ComponentType.BOLT]
        
        if bolt_components:
            # Check if quantities were counted correctly
            total_bolts = sum(c.quantity for c in bolt_components)
            assert total_bolts >= 3  # Should detect most of the bolts
    
    def test_are_components_similar(self):
        """Test component similarity detection."""
        # Create two similar components
        comp1 = Component(
            id="bolt_1",
            type=ComponentType.BOLT,
            dimensions=ComponentDimensions(width=20.0, height=20.0, unit="pixels"),
            extraction_metadata={'bbox': {'x': 100, 'y': 100, 'width': 20, 'height': 20}}
        )
        
        comp2 = Component(
            id="bolt_2", 
            type=ComponentType.BOLT,
            dimensions=ComponentDimensions(width=22.0, height=21.0, unit="pixels"),
            extraction_metadata={'bbox': {'x': 200, 'y': 100, 'width': 22, 'height': 21}}
        )
        
        # Different type component
        comp3 = Component(
            id="beam_1",
            type=ComponentType.BEAM,
            dimensions=ComponentDimensions(width=20.0, height=20.0, unit="pixels")
        )
        
        assert self.extractor._are_components_similar(comp1, comp2) is True
        assert self.extractor._are_components_similar(comp1, comp3) is False
    
    def test_are_dimensions_similar(self):
        """Test dimension similarity checking."""
        dim1 = ComponentDimensions(width=100.0, height=50.0, unit="mm")
        dim2 = ComponentDimensions(width=105.0, height=52.0, unit="mm")  # Within 10% tolerance
        dim3 = ComponentDimensions(width=150.0, height=50.0, unit="mm")  # Outside tolerance
        
        assert self.extractor._are_dimensions_similar(dim1, dim2) is True
        assert self.extractor._are_dimensions_similar(dim1, dim3) is False
    
    def test_are_materials_similar(self):
        """Test material similarity checking."""
        mat1 = MaterialSpec(grade="A36", specification="ASTM")
        mat2 = MaterialSpec(grade="A36", specification="ASTM")
        mat3 = MaterialSpec(grade="A572", specification="ASTM")
        
        assert self.extractor._are_materials_similar(mat1, mat2) is True
        assert self.extractor._are_materials_similar(mat1, mat3) is False
    
    def test_are_sizes_similar(self):
        """Test bounding box size similarity."""
        bbox1 = {'width': 100, 'height': 50}
        bbox2 = {'width': 105, 'height': 52}  # Similar size
        bbox3 = {'width': 200, 'height': 50}  # Different size
        
        assert self.extractor._are_sizes_similar(bbox1, bbox2) is True
        assert self.extractor._are_sizes_similar(bbox1, bbox3) is False
    
    def test_create_representative_component(self):
        """Test creation of representative component from group."""
        # Create group of similar components
        components = []
        for i, (x, y) in enumerate([(100, 100), (150, 100), (200, 100)]):
            comp = Component(
                id=f"bolt_{i}",
                type=ComponentType.BOLT,
                location=Coordinates(x=x, y=y, page_number=1),
                confidence=0.8 + i * 0.05,  # Varying confidence
                quantity=1
            )
            components.append(comp)
        
        representative = self.extractor._create_representative_component(components)
        
        assert representative.quantity == 3
        assert representative.location.x == 150.0  # Average x position
        assert representative.location.y == 100.0  # Average y position
        assert 'quantity_group' in representative.extraction_metadata
        
        group_data = representative.extraction_metadata['quantity_group']
        assert group_data['total_count'] == 3
        assert len(group_data['individual_locations']) == 3
    
    def test_get_component_locations(self):
        """Test getting all component locations."""
        # Create component with quantity group
        component = Component(
            id="bolt_group",
            type=ComponentType.BOLT,
            location=Coordinates(x=150, y=100, page_number=1),
            quantity=3,
            extraction_metadata={
                'quantity_group': {
                    'individual_locations': [
                        {'x': 100, 'y': 100},
                        {'x': 150, 'y': 100},
                        {'x': 200, 'y': 100}
                    ]
                }
            }
        )
        
        locations = self.extractor.get_component_locations([component])
        
        assert 'bolt_group' in locations
        component_locations = locations['bolt_group']
        assert len(component_locations) >= 3  # Main location + individual locations
    
    def test_get_quantity_statistics(self):
        """Test quantity statistics calculation."""
        components = [
            Component(id="bolt_1", type=ComponentType.BOLT, quantity=3),
            Component(id="bolt_2", type=ComponentType.BOLT, quantity=1),
            Component(id="beam_1", type=ComponentType.BEAM, quantity=2),
        ]
        
        stats = self.extractor.get_quantity_statistics(components)
        
        assert stats['total_unique_components'] == 3
        assert stats['total_individual_parts'] == 6  # 3 + 1 + 2
        assert stats['by_type']['bolt']['unique'] == 2
        assert stats['by_type']['bolt']['total'] == 4  # 3 + 1
        assert stats['by_type']['beam']['unique'] == 1
        assert stats['by_type']['beam']['total'] == 2
        assert stats['grouped_components'] == 2  # Components with quantity > 1
        assert stats['single_components'] == 1   # Components with quantity = 1