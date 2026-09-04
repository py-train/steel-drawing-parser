"""Tests for data validation and quality assurance."""

import pytest
from src.extractors.data_validator import DataValidator, ValidationSeverity, DimensionRange, MaterialStandard
from src.models.component import Component, ComponentType, ComponentDimensions, MaterialSpec, Coordinates
from src.models.processing import ValidationResult, ValidationIssue


class TestDimensionRange:
    """Test cases for DimensionRange data model."""
    
    def test_dimension_range_creation(self):
        """Test DimensionRange object creation."""
        range_def = DimensionRange(
            min_value=100.0,
            max_value=1000.0,
            unit="mm",
            description="Test range"
        )
        
        assert range_def.min_value == 100.0
        assert range_def.max_value == 1000.0
        assert range_def.unit == "mm"
        assert range_def.description == "Test range"


class TestMaterialStandard:
    """Test cases for MaterialStandard data model."""
    
    def test_material_standard_creation(self):
        """Test MaterialStandard object creation."""
        standard = MaterialStandard(
            grade="A36",
            specification="ASTM",
            yield_strength_range=(36000, 36000),
            tensile_strength_range=(58000, 80000),
            common_applications=["General construction"]
        )
        
        assert standard.grade == "A36"
        assert standard.specification == "ASTM"
        assert standard.yield_strength_range == (36000, 36000)
        assert standard.tensile_strength_range == (58000, 80000)
        assert "General construction" in standard.common_applications


class TestDataValidator:
    """Test cases for data validator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = DataValidator()
    
    def create_test_beam_component(self) -> Component:
        """Create a test beam component with valid dimensions."""
        return Component(
            id="beam_001",
            type=ComponentType.BEAM,
            dimensions=ComponentDimensions(
                width=200.0,  # mm
                height=400.0,  # mm
                thickness=10.0,  # mm
                unit="mm"
            ),
            material=MaterialSpec(
                grade="A36",
                specification="ASTM",
                yield_strength=36000.0
            ),
            location=Coordinates(x=100, y=200, page_number=1),
            confidence=0.8
        )
    
    def create_test_bolt_component(self) -> Component:
        """Create a test bolt component."""
        return Component(
            id="bolt_001",
            type=ComponentType.BOLT,
            dimensions=ComponentDimensions(
                diameter=20.0,  # mm
                length=80.0,    # mm
                unit="mm"
            ),
            material=MaterialSpec(
                grade="A325",
                specification="ASTM"
            ),
            confidence=0.9
        )
    
    def test_validate_dimensions_valid_beam(self):
        """Test dimension validation for valid beam."""
        component = self.create_test_beam_component()
        
        result = self.validator.validate_dimensions(component)
        
        assert result.is_valid is True
        assert result.confidence > 0.8
        assert len(result.issues) == 0
    
    def test_validate_dimensions_missing_dimensions(self):
        """Test validation with missing dimensions."""
        component = Component(
            id="test_001",
            type=ComponentType.BEAM,
            confidence=0.8
        )
        
        result = self.validator.validate_dimensions(component)
        
        assert result.is_valid is True  # Missing dimensions is warning, not error
        assert result.confidence == 0.5
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == "missing_dimensions"
        assert result.issues[0].severity == ValidationSeverity.WARNING.value
    
    def test_validate_dimensions_out_of_range(self):
        """Test validation with dimensions out of range."""
        component = Component(
            id="beam_002",
            type=ComponentType.BEAM,
            dimensions=ComponentDimensions(
                width=50.0,    # Too small for beam
                height=2000.0, # Too large for beam
                unit="mm"
            ),
            confidence=0.8
        )
        
        result = self.validator.validate_dimensions(component)
        
        assert result.is_valid is True  # Warnings, not errors
        assert result.confidence < 0.8  # Reduced confidence
        assert len(result.issues) == 2
        
        issue_types = [issue.issue_type for issue in result.issues]
        assert "dimension_too_small" in issue_types
        assert "dimension_too_large" in issue_types
    
    def test_validate_dimensions_unusual_aspect_ratio(self):
        """Test validation with unusual aspect ratio."""
        component = Component(
            id="beam_003",
            type=ComponentType.BEAM,
            dimensions=ComponentDimensions(
                width=10000.0,  # Very wide
                height=100.0,   # Very thin
                unit="mm"
            ),
            confidence=0.8
        )
        
        result = self.validator.validate_dimensions(component)
        
        assert len(result.issues) >= 1
        aspect_ratio_issues = [issue for issue in result.issues 
                             if issue.issue_type == "unusual_aspect_ratio"]
        assert len(aspect_ratio_issues) == 1
    
    def test_validate_dimensions_unit_conversion(self):
        """Test dimension validation with unit conversion."""
        component = Component(
            id="beam_004",
            type=ComponentType.BEAM,
            dimensions=ComponentDimensions(
                width=8.0,   # inches
                height=16.0, # inches
                unit="in"
            ),
            confidence=0.8
        )
        
        result = self.validator.validate_dimensions(component)
        
        # Should convert to mm and validate (8" = 203mm, 16" = 406mm - valid for beam)
        assert result.is_valid is True
        assert result.confidence > 0.8
    
    def test_validate_materials_valid_grade(self):
        """Test material validation with valid grade."""
        material = MaterialSpec(
            grade="A36",
            specification="ASTM",
            yield_strength=36000.0,
            tensile_strength=65000.0
        )
        
        result = self.validator.validate_materials(material)
        
        assert result.is_valid is True
        assert result.confidence > 0.9
        assert len(result.issues) == 0
    
    def test_validate_materials_missing_material(self):
        """Test validation with missing material."""
        result = self.validator.validate_materials(None)
        
        assert result.is_valid is True  # Missing material is info, not error
        assert result.confidence == 0.5
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == "missing_material"
    
    def test_validate_materials_unrecognized_grade(self):
        """Test validation with unrecognized grade."""
        material = MaterialSpec(
            grade="UNKNOWN_GRADE",
            specification="ASTM"
        )
        
        result = self.validator.validate_materials(material)
        
        assert result.is_valid is True  # Warning, not error
        assert result.confidence < 1.0
        assert len(result.issues) >= 1
        
        grade_issues = [issue for issue in result.issues 
                       if issue.issue_type == "unrecognized_grade"]
        assert len(grade_issues) == 1
    
    def test_validate_materials_unknown_specification(self):
        """Test validation with unknown specification."""
        material = MaterialSpec(
            grade="A36",
            specification="UNKNOWN_SPEC"
        )
        
        result = self.validator.validate_materials(material)
        
        assert result.is_valid is True
        unknown_spec_issues = [issue for issue in result.issues 
                             if issue.issue_type == "unknown_specification"]
        assert len(unknown_spec_issues) == 1
    
    def test_validate_materials_strength_values(self):
        """Test validation of strength values."""
        # Valid strength values
        material_valid = MaterialSpec(
            grade="A36",
            yield_strength=36000.0,
            tensile_strength=65000.0
        )
        
        result = self.validator.validate_materials(material_valid)
        assert result.is_valid is True
        
        # Invalid strength values (yield > tensile)
        material_invalid = MaterialSpec(
            grade="A36",
            yield_strength=70000.0,  # Higher than tensile
            tensile_strength=65000.0
        )
        
        result = self.validator.validate_materials(material_invalid)
        assert result.is_valid is False  # This should be an error
        
        strength_errors = [issue for issue in result.issues 
                         if issue.issue_type == "strength_relationship_error"]
        assert len(strength_errors) == 1
    
    def test_validate_materials_out_of_range_strength(self):
        """Test validation with strength values out of typical range."""
        material = MaterialSpec(
            grade="A36",
            yield_strength=150000.0,  # Too high
            tensile_strength=200000.0  # Too high
        )
        
        result = self.validator.validate_materials(material)
        
        unusual_strength_issues = [issue for issue in result.issues 
                                 if "unusual" in issue.issue_type]
        assert len(unusual_strength_issues) >= 1
    
    def test_validate_materials_grade_strength_consistency(self):
        """Test consistency between grade and strength values."""
        # A36 with inconsistent yield strength
        material = MaterialSpec(
            grade="A36",
            specification="ASTM",
            yield_strength=50000.0  # Too high for A36
        )
        
        result = self.validator.validate_materials(material)
        
        mismatch_issues = [issue for issue in result.issues 
                         if issue.issue_type == "grade_strength_mismatch"]
        assert len(mismatch_issues) == 1
    
    def test_calculate_confidence_complete_component(self):
        """Test confidence calculation for complete component."""
        component = self.create_test_beam_component()
        
        confidence = self.validator.calculate_confidence(component)
        
        assert 0.0 <= confidence <= 1.0
        assert confidence > 0.7  # Should be high for complete, valid component
    
    def test_calculate_confidence_incomplete_component(self):
        """Test confidence calculation for incomplete component."""
        component = Component(
            id="incomplete_001",
            type=ComponentType.BEAM,
            confidence=0.6
            # Missing dimensions and material
        )
        
        confidence = self.validator.calculate_confidence(component)
        
        assert 0.0 <= confidence <= 1.0
        assert confidence < 0.6  # Should be lower due to missing information
    
    def test_calculate_confidence_grouped_component(self):
        """Test confidence calculation for grouped component."""
        component = self.create_test_beam_component()
        component.quantity = 5  # Grouped component
        
        confidence = self.validator.calculate_confidence(component)
        
        # Should have higher confidence due to quantity factor
        single_component = self.create_test_beam_component()
        single_confidence = self.validator.calculate_confidence(single_component)
        
        assert confidence >= single_confidence
    
    def test_convert_dimensions_to_mm(self):
        """Test dimension unit conversion."""
        # Test millimeters (no conversion)
        dims_mm = ComponentDimensions(width=200.0, height=400.0, unit="mm")
        converted = self.validator._convert_dimensions_to_mm(dims_mm)
        assert converted['width'] == 200.0
        assert converted['height'] == 400.0
        
        # Test inches to mm
        dims_in = ComponentDimensions(width=8.0, height=16.0, unit="in")
        converted = self.validator._convert_dimensions_to_mm(dims_in)
        assert abs(converted['width'] - 203.2) < 0.1  # 8 * 25.4
        assert abs(converted['height'] - 406.4) < 0.1  # 16 * 25.4
        
        # Test feet to mm
        dims_ft = ComponentDimensions(width=1.0, unit="ft")
        converted = self.validator._convert_dimensions_to_mm(dims_ft)
        assert abs(converted['width'] - 304.8) < 0.1  # 1 * 304.8
    
    def test_validate_material_grade_patterns(self):
        """Test material grade pattern recognition."""
        test_grades = [
            ("W12x26", True),   # Wide flange
            ("A36", True),      # ASTM grade
            ("Grade 50", True), # Grade specification
            ("S12x35", True),   # Standard beam
            ("INVALID", False)  # Invalid grade
        ]
        
        for grade, should_be_recognized in test_grades:
            material = MaterialSpec(grade=grade, specification="ASTM")
            result = self.validator.validate_materials(material)
            
            unrecognized_issues = [issue for issue in result.issues 
                                 if issue.issue_type == "unrecognized_grade"]
            
            if should_be_recognized:
                assert len(unrecognized_issues) == 0, f"Grade {grade} should be recognized"
            else:
                assert len(unrecognized_issues) > 0, f"Grade {grade} should not be recognized"
    
    def test_dimension_completeness_calculation(self):
        """Test dimension completeness calculation."""
        # Complete dimensions
        complete_dims = ComponentDimensions(
            width=200.0, height=400.0, length=5000.0, 
            thickness=10.0, diameter=None, unit="mm"
        )
        completeness = self.validator._calculate_dimension_completeness(complete_dims)
        assert completeness > 0.8  # 4/5 fields + unit bonus
        
        # Minimal dimensions
        minimal_dims = ComponentDimensions(width=200.0, unit="pixels")
        completeness = self.validator._calculate_dimension_completeness(minimal_dims)
        assert completeness < 0.5  # Only 1/5 fields, no unit bonus for pixels
    
    def test_material_completeness_calculation(self):
        """Test material completeness calculation."""
        # Complete material
        complete_mat = MaterialSpec(
            grade="A36", specification="ASTM",
            yield_strength=36000.0, tensile_strength=65000.0
        )
        completeness = self.validator._calculate_material_completeness(complete_mat)
        assert completeness == 1.0  # All 4 fields filled
        
        # Minimal material
        minimal_mat = MaterialSpec(grade="A36")
        completeness = self.validator._calculate_material_completeness(minimal_mat)
        assert completeness == 0.25  # Only 1/4 fields filled
    
    def test_error_handling_invalid_component(self):
        """Test error handling with invalid component data."""
        # Component with None dimensions that cause errors
        component = Component(
            id="error_test",
            type=ComponentType.BEAM,
            confidence=0.8
        )
        
        # Should not crash and return reasonable results
        result = self.validator.validate_dimensions(component)
        assert isinstance(result, ValidationResult)
        
        confidence = self.validator.calculate_confidence(component)
        assert 0.0 <= confidence <= 1.0
    
    def test_validation_severity_levels(self):
        """Test that different validation issues have appropriate severity levels."""
        # Create component with various issues
        component = Component(
            id="severity_test",
            type=ComponentType.BEAM,
            dimensions=ComponentDimensions(
                width=50.0,    # Too small (warning)
                height=2000.0, # Too large (warning)
                unit="mm"
            ),
            material=MaterialSpec(
                grade="UNKNOWN",  # Unrecognized (warning)
                yield_strength=70000.0,  # Higher than tensile (error)
                tensile_strength=65000.0
            ),
            confidence=0.8
        )
        
        dim_result = self.validator.validate_dimensions(component)
        mat_result = self.validator.validate_materials(component.material)
        
        all_issues = dim_result.issues + mat_result.issues
        
        # Should have mix of severities
        severities = {issue.severity for issue in all_issues}
        assert ValidationSeverity.WARNING.value in severities
        
        # Should have at least one error (strength relationship)
        assert ValidationSeverity.ERROR.value in severities
    
    def test_flag_inconsistencies_duplicate_ids(self):
        """Test inconsistency detection for duplicate component IDs."""
        components = [
            Component(id="duplicate_001", type=ComponentType.BEAM, confidence=0.8),
            Component(id="duplicate_001", type=ComponentType.COLUMN, confidence=0.7),
            Component(id="unique_001", type=ComponentType.PLATE, confidence=0.9)
        ]
        
        issues = self.validator.flag_inconsistencies(components)
        
        duplicate_issues = [issue for issue in issues if issue.issue_type == "duplicate_id"]
        assert len(duplicate_issues) == 1
        assert duplicate_issues[0].severity == ValidationSeverity.ERROR.value
    
    def test_flag_inconsistencies_empty_list(self):
        """Test inconsistency detection with empty component list."""
        issues = self.validator.flag_inconsistencies([])
        assert len(issues) == 0
    
    def test_flag_inconsistencies_unusual_distribution(self):
        """Test detection of unusual component distributions."""
        # Create many bolts (unusual distribution)
        components = []
        for i in range(15):  # Many bolts
            components.append(Component(
                id=f"bolt_{i:03d}",
                type=ComponentType.BOLT,
                confidence=0.8,
                quantity=1
            ))
        
        # Add a few other components
        components.append(Component(id="beam_001", type=ComponentType.BEAM, confidence=0.8))
        components.append(Component(id="column_001", type=ComponentType.COLUMN, confidence=0.8))
        
        issues = self.validator.flag_inconsistencies(components)
        
        distribution_issues = [issue for issue in issues if issue.issue_type == "unusual_distribution"]
        assert len(distribution_issues) >= 1
        assert "bolt ratio" in distribution_issues[0].description.lower()
    
    def test_flag_inconsistencies_missing_locations(self):
        """Test detection of missing location information."""
        components = [
            Component(id="located_001", type=ComponentType.BEAM, confidence=0.8,
                     location=Coordinates(x=100, y=200, page_number=1)),
            Component(id="missing_loc_001", type=ComponentType.BEAM, confidence=0.8),
            Component(id="missing_loc_002", type=ComponentType.COLUMN, confidence=0.7)
        ]
        
        issues = self.validator.flag_inconsistencies(components)
        
        location_issues = [issue for issue in issues if issue.issue_type == "missing_locations"]
        assert len(location_issues) == 1
        assert "2 components missing location" in location_issues[0].description
    
    def test_flag_inconsistencies_location_clustering(self):
        """Test detection of location clustering."""
        # Create many components at similar locations
        components = []
        for i in range(8):  # Many components at same location
            components.append(Component(
                id=f"clustered_{i:03d}",
                type=ComponentType.BOLT,
                confidence=0.8,
                location=Coordinates(x=100 + i, y=200 + i, page_number=1)  # Very close locations
            ))
        
        issues = self.validator.flag_inconsistencies(components)
        
        clustering_issues = [issue for issue in issues if issue.issue_type == "location_clustering"]
        assert len(clustering_issues) >= 1
        assert "clustered at similar location" in clustering_issues[0].description
    
    def test_flag_inconsistencies_material_dimension_mismatch(self):
        """Test detection of material-dimension mismatches."""
        # W12 beam with wrong dimensions
        component = Component(
            id="mismatch_001",
            type=ComponentType.BEAM,
            dimensions=ComponentDimensions(
                width=600.0,  # 24 inches in mm, but grade suggests 12 inches
                height=300.0,
                unit="mm"
            ),
            material=MaterialSpec(grade="W12x26", specification="ASTM"),
            confidence=0.8
        )
        
        issues = self.validator.flag_inconsistencies([component])
        
        mismatch_issues = [issue for issue in issues if issue.issue_type == "material_dimension_mismatch"]
        assert len(mismatch_issues) == 1
        assert "W12x26" in mismatch_issues[0].description
    
    def test_flag_inconsistencies_confidence_anomalies(self):
        """Test detection of confidence anomalies."""
        # Create components with mostly low confidence
        components = []
        for i in range(10):
            components.append(Component(
                id=f"low_conf_{i:03d}",
                type=ComponentType.BEAM,
                confidence=0.2  # Very low confidence
            ))
        
        # Add one high confidence component
        components.append(Component(id="high_conf_001", type=ComponentType.BEAM, confidence=0.9))
        
        issues = self.validator.flag_inconsistencies(components)
        
        confidence_issues = [issue for issue in issues if issue.issue_type == "low_confidence_pattern"]
        assert len(confidence_issues) >= 1
        assert "unusually low confidence" in confidence_issues[0].description
    
    def test_generate_confidence_report_empty_list(self):
        """Test confidence report generation with empty component list."""
        report = self.validator.generate_confidence_report([])
        
        assert report['total_components'] == 0
        assert report['average_confidence'] == 0.0
        assert len(report['low_confidence_components']) == 0
        assert len(report['high_confidence_components']) == 0
    
    def test_generate_confidence_report_complete(self):
        """Test comprehensive confidence report generation."""
        components = [
            # High confidence component
            Component(
                id="high_001",
                type=ComponentType.BEAM,
                dimensions=ComponentDimensions(width=200.0, height=400.0, unit="mm"),
                material=MaterialSpec(grade="A36", specification="ASTM"),
                confidence=0.9,
                location=Coordinates(x=100, y=200, page_number=1)
            ),
            # Medium confidence component
            Component(
                id="medium_001",
                type=ComponentType.COLUMN,
                dimensions=ComponentDimensions(width=300.0, unit="mm"),
                confidence=0.6
            ),
            # Low confidence component
            Component(
                id="low_001",
                type=ComponentType.PLATE,
                confidence=0.3
            )
        ]
        
        report = self.validator.generate_confidence_report(components)
        
        # Check basic statistics
        assert report['total_components'] == 3
        assert 0.0 <= report['average_confidence'] <= 1.0
        assert 0.0 <= report['min_confidence'] <= 1.0
        assert 0.0 <= report['max_confidence'] <= 1.0
        
        # Check distribution
        assert 'confidence_distribution' in report
        assert 'very_low' in report['confidence_distribution']
        assert 'high' in report['confidence_distribution']
        
        # Check component categorization
        assert len(report['low_confidence_components']) >= 1
        assert len(report['high_confidence_components']) >= 0
        
        # Check confidence by type
        assert 'confidence_by_type' in report
        assert len(report['confidence_by_type']) > 0
        
        # Check recommendations
        assert 'recommendations' in report
        assert isinstance(report['recommendations'], list)
    
    def test_generate_confidence_report_recommendations(self):
        """Test confidence report recommendation generation."""
        # Create components with various issues
        components = []
        
        # Many low confidence components
        for i in range(8):
            components.append(Component(
                id=f"low_{i:03d}",
                type=ComponentType.BEAM,
                confidence=0.2  # Very low
            ))
        
        # Few high confidence components
        for i in range(2):
            components.append(Component(
                id=f"high_{i:03d}",
                type=ComponentType.BEAM,
                confidence=0.9,
                dimensions=ComponentDimensions(width=200.0, height=400.0, unit="mm"),
                material=MaterialSpec(grade="A36", specification="ASTM")
            ))
        
        report = self.validator.generate_confidence_report(components)
        
        recommendations = report['recommendations']
        assert len(recommendations) > 0
        
        # Should recommend improving confidence
        confidence_recommendations = [r for r in recommendations if 'confidence' in r.lower()]
        assert len(confidence_recommendations) > 0
    
    def test_dimension_variation_detection(self):
        """Test detection of high dimension variation in similar components."""
        # Create beams with very different dimensions
        dimensions_list = [
            ComponentDimensions(width=100.0, height=200.0, unit="mm"),
            ComponentDimensions(width=500.0, height=1000.0, unit="mm"),  # Much larger
            ComponentDimensions(width=150.0, height=300.0, unit="mm")
        ]
        
        issues = self.validator._check_dimension_variation(ComponentType.BEAM, dimensions_list)
        
        variation_issues = [issue for issue in issues if issue.issue_type == "high_dimension_variation"]
        assert len(variation_issues) >= 1
        assert "variation" in variation_issues[0].description.lower()
    
    def test_material_variation_detection(self):
        """Test detection of material variation in similar components."""
        # Create materials with different grades
        materials_list = [
            MaterialSpec(grade="A36", specification="ASTM"),
            MaterialSpec(grade="A572", specification="ASTM"),
            MaterialSpec(grade="A992", specification="ASTM"),
            MaterialSpec(grade="Grade 50", specification="AISC")
        ]
        
        issues = self.validator._check_material_variation(ComponentType.BEAM, materials_list)
        
        variation_issues = [issue for issue in issues if issue.issue_type == "material_inconsistency"]
        assert len(variation_issues) >= 1
        assert "different material grades" in variation_issues[0].description.lower()
    
    def test_location_clustering_detection(self):
        """Test location clustering detection algorithm."""
        components = [
            Component(id="cluster1_1", type=ComponentType.BOLT, confidence=0.8,
                     location=Coordinates(x=100, y=200, page_number=1)),
            Component(id="cluster1_2", type=ComponentType.BOLT, confidence=0.8,
                     location=Coordinates(x=105, y=205, page_number=1)),  # Close to first
            Component(id="cluster1_3", type=ComponentType.BOLT, confidence=0.8,
                     location=Coordinates(x=110, y=210, page_number=1)),  # Close to others
            Component(id="isolated", type=ComponentType.BEAM, confidence=0.8,
                     location=Coordinates(x=500, y=600, page_number=1))   # Far away
        ]
        
        clusters = self.validator._find_location_clusters(components, cluster_distance=20.0)
        
        assert len(clusters) == 1  # Should find one cluster
        assert len(clusters[0]) == 3  # Three components in cluster
    
    def test_confidence_issue_identification(self):
        """Test identification of specific confidence issues."""
        # Component with multiple issues
        component = Component(
            id="issues_001",
            type=ComponentType.BEAM,
            confidence=0.3  # Low confidence
            # Missing dimensions, material, and location
        )
        
        issues = self.validator._identify_confidence_issues(component)
        
        assert "Missing dimensions" in issues
        assert "Missing material specification" in issues
        assert "Low detection confidence" in issues
        assert "Missing location information" in issues
    
    def test_error_handling_in_inconsistency_detection(self):
        """Test error handling in inconsistency detection methods."""
        # Test with malformed component data
        components = [
            Component(id="test_001", type=ComponentType.BEAM, confidence=0.8)
        ]
        
        # Should not crash and return reasonable results
        issues = self.validator.flag_inconsistencies(components)
        assert isinstance(issues, list)
        
        report = self.validator.generate_confidence_report(components)
        assert isinstance(report, dict)
        assert 'total_components' in report