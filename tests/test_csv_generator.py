"""Tests for CSV output generation."""

import pytest
import csv
import tempfile
import os
from io import StringIO

from src.generators.csv_generator import CSVGenerator
from src.models.component import Component, ComponentType, ComponentDimensions, MaterialSpec, Coordinates
from src.models.processing import ValidationResult, ValidationIssue


class TestCSVGenerator:
    """Test cases for CSV generator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.generator = CSVGenerator()
    
    def create_test_component(self) -> Component:
        """Create a complete test component."""
        return Component(
            id="beam_001",
            type=ComponentType.BEAM,
            dimensions=ComponentDimensions(
                width=200.0,
                height=400.0,
                length=5000.0,
                thickness=10.0,
                unit="mm"
            ),
            material=MaterialSpec(
                grade="A36",
                specification="ASTM",
                yield_strength=36000.0,
                tensile_strength=65000.0
            ),
            location=Coordinates(x=100.5, y=200.7, page_number=1),
            confidence=0.85,
            quantity=2
        )
    
    def create_minimal_component(self) -> Component:
        """Create a minimal test component."""
        return Component(
            id="minimal_001",
            type=ComponentType.BOLT,
            confidence=0.6
        )
    
    def create_validation_result(self, is_valid: bool = True) -> ValidationResult:
        """Create a test validation result."""
        issues = []
        if not is_valid:
            issues.append(ValidationIssue(
                component_id="test_001",
                issue_type="test_issue",
                description="Test validation issue",
                severity="warning"
            ))
        
        return ValidationResult(
            is_valid=is_valid,
            confidence=0.8,
            issues=issues
        )
    
    def test_generate_csv_single_component(self):
        """Test CSV generation with single component."""
        component = self.create_test_component()
        
        csv_content = self.generator.generate_csv([component])
        
        # Parse CSV content
        reader = csv.DictReader(StringIO(csv_content))
        rows = list(reader)
        
        assert len(rows) == 1
        row = rows[0]
        
        # Check basic fields
        assert row['component_id'] == 'beam_001'
        assert row['component_type'] == 'beam'
        assert row['quantity'] == '2'
        assert row['confidence'] == '0.85'
        
        # Check dimensions
        assert row['width_mm'] == '200.0'
        assert row['height_mm'] == '400.0'
        assert row['length_mm'] == '5000.0'
        assert row['thickness_mm'] == '10.0'
        assert row['dimension_unit'] == 'mm'
        
        # Check materials
        assert row['material_grade'] == 'A36'
        assert row['material_specification'] == 'ASTM'
        assert row['yield_strength_psi'] == '36000'
        assert row['tensile_strength_psi'] == '65000'
        
        # Check location
        assert row['location_x'] == '100.5'
        assert row['location_y'] == '200.7'
        assert row['page_number'] == '1'
    
    def test_generate_csv_multiple_components(self):
        """Test CSV generation with multiple components."""
        components = [
            self.create_test_component(),
            self.create_minimal_component()
        ]
        
        csv_content = self.generator.generate_csv(components)
        
        # Parse CSV content
        reader = csv.DictReader(StringIO(csv_content))
        rows = list(reader)
        
        assert len(rows) == 2
        
        # Check first component (complete)
        assert rows[0]['component_id'] == 'beam_001'
        assert rows[0]['component_type'] == 'beam'
        
        # Check second component (minimal)
        assert rows[1]['component_id'] == 'minimal_001'
        assert rows[1]['component_type'] == 'bolt'
        assert rows[1]['confidence'] == '0.6'
    
    def test_generate_csv_empty_list(self):
        """Test CSV generation with empty component list."""
        csv_content = self.generator.generate_csv([])
        
        # Should have headers but no data rows
        reader = csv.DictReader(StringIO(csv_content))
        rows = list(reader)
        
        assert len(rows) == 0
        assert len(reader.fieldnames) > 0  # Should have headers
    
    def test_generate_csv_with_validation(self):
        """Test CSV generation with validation results."""
        component = self.create_test_component()
        validation_results = {
            component.id: self.create_validation_result(is_valid=False)
        }
        
        csv_content = self.generator.generate_csv([component], validation_results)
        
        reader = csv.DictReader(StringIO(csv_content))
        rows = list(reader)
        
        assert len(rows) == 1
        row = rows[0]
        
        assert row['validation_status'] == 'INVALID'
        assert 'Test validation issue' in row['validation_issues']
    
    def test_generate_csv_without_validation(self):
        """Test CSV generation without validation columns."""
        component = self.create_test_component()
        
        csv_content = self.generator.generate_csv([component], include_validation=False)
        
        reader = csv.DictReader(StringIO(csv_content))
        headers = reader.fieldnames
        
        assert 'validation_status' not in headers
        assert 'validation_issues' not in headers
    
    def test_generate_csv_to_file(self):
        """Test CSV generation to file."""
        component = self.create_test_component()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            csv_content = self.generator.generate_csv([component], output_file=temp_path)
            
            # Check file was created
            assert os.path.exists(temp_path)
            
            # Check file content matches returned content
            with open(temp_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            assert file_content == csv_content
            
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_format_component_row_complete(self):
        """Test formatting complete component row."""
        component = self.create_test_component()
        validation_result = self.create_validation_result(is_valid=True)
        
        row = self.generator.format_component_row(component, validation_result)
        
        # Check all expected fields are present
        expected_fields = [
            'component_id', 'component_type', 'quantity', 'confidence',
            'width_mm', 'height_mm', 'length_mm', 'thickness_mm', 'diameter_mm',
            'dimension_unit', 'material_grade', 'material_specification',
            'yield_strength_psi', 'tensile_strength_psi',
            'location_x', 'location_y', 'page_number',
            'validation_status', 'validation_issues'
        ]
        
        for field in expected_fields:
            assert field in row
        
        # Check specific values
        assert row['component_id'] == 'beam_001'
        assert row['component_type'] == 'beam'
        assert row['quantity'] == 2
        assert row['confidence'] == 0.85
        assert row['validation_status'] == 'VALID'
    
    def test_format_component_row_minimal(self):
        """Test formatting minimal component row."""
        component = self.create_minimal_component()
        
        row = self.generator.format_component_row(component, include_validation=False)
        
        # Check basic fields
        assert row['component_id'] == 'minimal_001'
        assert row['component_type'] == 'bolt'
        assert row['confidence'] == 0.6
        
        # Check missing data handling
        assert row['width_mm'] is None
        assert row['material_grade'] == ''
        assert row['location_x'] is None
    
    def test_get_csv_headers_with_validation(self):
        """Test getting CSV headers with validation columns."""
        headers = self.generator.get_csv_headers(include_validation=True)
        
        assert 'validation_status' in headers
        assert 'validation_issues' in headers
        assert len(headers) == len(self.generator.standard_headers)
    
    def test_get_csv_headers_without_validation(self):
        """Test getting CSV headers without validation columns."""
        headers = self.generator.get_csv_headers(include_validation=False)
        
        assert 'validation_status' not in headers
        assert 'validation_issues' not in headers
        assert len(headers) < len(self.generator.standard_headers)
    
    def test_handle_missing_data(self):
        """Test missing data handling."""
        row_data = {
            'component_id': None,
            'width_mm': None,
            'material_grade': '',
            'quantity': None,
            'confidence': 0.75
        }
        
        handled_row = self.generator.handle_missing_data(row_data)
        
        assert handled_row['component_id'] == 'UNKNOWN'
        assert handled_row['width_mm'] is None  # Numeric fields stay None
        assert handled_row['material_grade'] == ''  # String fields stay empty
        assert handled_row['quantity'] == 1  # Default quantity
        assert handled_row['confidence'] == 0.75  # Existing values preserved
    
    def test_add_custom_column(self):
        """Test adding custom columns."""
        original_count = len(self.generator.get_csv_headers())
        
        self.generator.add_custom_column('custom_field', 'default_value')
        
        new_headers = self.generator.get_csv_headers()
        assert len(new_headers) == original_count + 1
        assert 'custom_field' in new_headers
    
    def test_remove_custom_column(self):
        """Test removing custom columns."""
        self.generator.add_custom_column('temp_field', 'temp_value')
        original_count = len(self.generator.get_csv_headers())
        
        self.generator.remove_custom_column('temp_field')
        
        new_headers = self.generator.get_csv_headers()
        assert len(new_headers) == original_count - 1
        assert 'temp_field' not in new_headers
    
    def test_get_summary_statistics_empty(self):
        """Test summary statistics with empty component list."""
        stats = self.generator.get_summary_statistics([])
        
        assert stats['total_components'] == 0
        assert stats['total_quantity'] == 0
        assert stats['component_types'] == {}
        assert stats['average_confidence'] == 0.0
    
    def test_get_summary_statistics_complete(self):
        """Test summary statistics with components."""
        components = [
            self.create_test_component(),  # quantity=2, confidence=0.85
            self.create_minimal_component()  # quantity=1, confidence=0.6
        ]
        
        stats = self.generator.get_summary_statistics(components)
        
        assert stats['total_components'] == 2
        assert stats['total_quantity'] == 3  # 2 + 1
        assert stats['component_types']['beam'] == 2
        assert stats['component_types']['bolt'] == 1
        assert stats['average_confidence'] == 0.725  # (0.85 + 0.6) / 2
        assert stats['components_with_dimensions'] == 1  # Only complete component
        assert stats['components_with_materials'] == 1
        assert stats['components_with_locations'] == 1
    
    def test_format_dimension_values(self):
        """Test dimension value formatting."""
        assert self.generator._format_dimension(None) is None
        assert self.generator._format_dimension(123.456) == 123.46
        assert self.generator._format_dimension(100.0) == 100.0
    
    def test_format_strength_values(self):
        """Test strength value formatting."""
        assert self.generator._format_strength(None) is None
        assert self.generator._format_strength(36000.7) == 36001
        assert self.generator._format_strength(50000.0) == 50000
    
    def test_format_validation_issues(self):
        """Test validation issues formatting."""
        # Empty issues
        assert self.generator._format_validation_issues([]) == ''
        
        # Single issue
        issue = ValidationIssue(
            component_id="test_001",
            issue_type="test_issue",
            description="Test issue description",
            severity="warning"
        )
        formatted = self.generator._format_validation_issues([issue])
        assert "Test issue description" in formatted
        
        # Multiple issues
        issue2 = ValidationIssue(
            component_id="test_002",
            issue_type="another_issue",
            description="Another issue",
            severity="error"
        )
        formatted = self.generator._format_validation_issues([issue, issue2])
        assert "Test issue description" in formatted
        assert "Another issue" in formatted
        assert ";" in formatted  # Should be separated by semicolons
    
    def test_escape_csv_content(self):
        """Test CSV content escaping."""
        # Test newlines and tabs
        content = "Line 1\nLine 2\tTabbed"
        escaped = self.generator._escape_csv_content(content)
        assert '\n' not in escaped
        assert '\t' not in escaped
        assert "Line 1 Line 2 Tabbed" == escaped
        
        # Test control characters
        content = "Text\x00with\x01control\x02chars"
        escaped = self.generator._escape_csv_content(content)
        assert '\x00' not in escaped
        assert '\x01' not in escaped
        assert '\x02' not in escaped
        
        # Test excessive whitespace
        content = "Too    much     whitespace"
        escaped = self.generator._escape_csv_content(content)
        assert "Too much whitespace" == escaped
    
    def test_csv_special_character_handling(self):
        """Test handling of special characters in CSV output."""
        # Create component with special characters
        component = Component(
            id="special_001",
            type=ComponentType.BEAM,
            material=MaterialSpec(
                grade="A36,Special\"Grade",  # Contains comma and quote
                specification="ASTM\nMultiline"  # Contains newline
            ),
            confidence=0.8
        )
        
        csv_content = self.generator.generate_csv([component])
        
        # Should be valid CSV
        reader = csv.DictReader(StringIO(csv_content))
        rows = list(reader)
        
        assert len(rows) == 1
        row = rows[0]
        
        # Special characters should be handled
        assert row['material_grade'] == 'A36,Special"Grade'  # CSV reader handles quotes
        assert '\n' not in row['material_specification']  # Newlines should be escaped
    
    def test_error_handling_invalid_component(self):
        """Test error handling with invalid component data."""
        # Create component that might cause formatting errors
        component = Component(
            id="error_test",
            type=ComponentType.BEAM,
            confidence=0.8
        )
        
        # Mock an error in dimension formatting by setting invalid dimensions
        component.dimensions = "invalid_dimensions"  # This should cause an error
        
        # Should not crash and return error indication
        row = self.generator.format_component_row(component)
        
        assert row['component_id'] == 'error_test'
        assert row['validation_status'] == 'ERROR'
        assert 'Formatting error' in row['validation_issues']
    
    def test_csv_output_consistency(self):
        """Test that CSV output is consistent across multiple generations."""
        components = [self.create_test_component(), self.create_minimal_component()]
        
        # Generate CSV multiple times
        csv1 = self.generator.generate_csv(components)
        csv2 = self.generator.generate_csv(components)
        
        # Should be identical
        assert csv1 == csv2
    
    def test_large_component_list_performance(self):
        """Test CSV generation with large component list."""
        # Create many components
        components = []
        for i in range(100):
            component = Component(
                id=f"component_{i:03d}",
                type=ComponentType.BEAM,
                confidence=0.8,
                quantity=1
            )
            components.append(component)
        
        # Should complete without issues
        csv_content = self.generator.generate_csv(components)
        
        # Check output
        reader = csv.DictReader(StringIO(csv_content))
        rows = list(reader)
        
        assert len(rows) == 100
        assert all(row['component_type'] == 'beam' for row in rows)
    
    def test_completeness_percentage_calculation(self):
        """Test completeness percentage calculation in summary statistics."""
        components = [
            # Complete component
            self.create_test_component(),
            # Component with only dimensions
            Component(
                id="dims_only",
                type=ComponentType.BEAM,
                dimensions=ComponentDimensions(width=100.0, unit="mm"),
                confidence=0.7
            ),
            # Component with only material
            Component(
                id="mat_only",
                type=ComponentType.COLUMN,
                material=MaterialSpec(grade="A36"),
                confidence=0.6
            ),
            # Minimal component
            self.create_minimal_component()
        ]
        
        stats = self.generator.get_summary_statistics(components)
        
        # Check completeness percentages
        completeness = stats['completeness_percentage']
        assert completeness['dimensions'] == 50.0  # 2 out of 4 components
        assert completeness['materials'] == 50.0   # 2 out of 4 components
        assert completeness['locations'] == 25.0   # 1 out of 4 components