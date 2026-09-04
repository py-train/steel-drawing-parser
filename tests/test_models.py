"""Tests for data models."""

import pytest
from src.models.component import Component, ComponentType, ComponentDimensions, MaterialSpec, Coordinates
from src.models.config import ExtractionConfig


class TestComponentModels:
    """Test cases for component data models."""
    
    def test_component_creation(self):
        """Test basic component creation."""
        component = Component(
            id="beam_001",
            type=ComponentType.BEAM
        )
        assert component.id == "beam_001"
        assert component.type == ComponentType.BEAM
        assert component.quantity == 1
        assert component.confidence == 0.0
    
    def test_component_with_dimensions(self):
        """Test component with dimensions."""
        dimensions = ComponentDimensions(
            length=5000.0,
            width=200.0,
            height=300.0,
            unit="mm"
        )
        component = Component(
            id="beam_002",
            type=ComponentType.BEAM,
            dimensions=dimensions
        )
        assert component.dimensions.length == 5000.0
        assert component.dimensions.unit == "mm"
    
    def test_material_spec(self):
        """Test material specification."""
        material = MaterialSpec(
            grade="A36",
            yield_strength=250.0,
            specification="ASTM"
        )
        assert material.grade == "A36"
        assert material.yield_strength == 250.0
    
    def test_coordinates(self):
        """Test coordinate system."""
        coords = Coordinates(
            x=100.5,
            y=200.3,
            page_number=1,
            drawing_region="main"
        )
        assert coords.x == 100.5
        assert coords.page_number == 1


class TestConfigModels:
    """Test cases for configuration models."""
    
    def test_extraction_config_defaults(self):
        """Test default extraction configuration."""
        config = ExtractionConfig()
        assert config.min_component_size == 50
        assert config.confidence_threshold == 0.7
        assert "mm" in config.supported_units
        assert config.validate() is True
    
    def test_extraction_config_validation(self):
        """Test configuration validation."""
        # Valid config
        config = ExtractionConfig(
            min_component_size=100,
            confidence_threshold=0.8
        )
        assert config.validate() is True
        
        # Invalid config - negative size
        config.min_component_size = -10
        assert config.validate() is False
        
        # Invalid config - confidence out of range
        config.min_component_size = 50
        config.confidence_threshold = 1.5
        assert config.validate() is False