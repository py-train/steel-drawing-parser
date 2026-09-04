"""CSV output generation for extracted steel components."""

import csv
import logging
from typing import List, Dict, Any, Optional, TextIO
from io import StringIO
from dataclasses import asdict

from ..models.component import Component, ComponentType, ComponentDimensions, MaterialSpec
from ..models.processing import ValidationResult
from ..utils.performance_monitor import get_performance_monitor, monitor_performance


class CSVGenerator:
    """Generates structured CSV output for extracted steel components."""
    
    def __init__(self):
        self.logger = logging.getLogger('steel_parser.csv_generator')
        self.performance_monitor = get_performance_monitor()
        
        # Standard column headers
        self.standard_headers = [
            'component_id',
            'component_type',
            'quantity',
            'width_mm',
            'height_mm',
            'length_mm',
            'thickness_mm',
            'diameter_mm',
            'dimension_unit',
            'material_grade',
            'material_specification',
            'yield_strength_psi',
            'tensile_strength_psi',
            'location_x',
            'location_y',
            'page_number',
            'confidence',
            'validation_status',
            'validation_issues'
        ]
        
        # Additional columns that can be added dynamically
        self.additional_headers = []
    
    @monitor_performance("csv_generation")
    def generate_csv(self, components: List[Component], 
                    validation_results: Optional[Dict[str, ValidationResult]] = None,
                    output_file: Optional[str] = None,
                    include_validation: bool = True) -> str:
        """
        Generate CSV output for components.
        
        Args:
            components: List of components to export
            validation_results: Optional validation results keyed by component ID
            output_file: Optional file path to write CSV to
            include_validation: Whether to include validation columns
            
        Returns:
            CSV content as string
        """
        try:
            # Create string buffer for CSV content
            output = StringIO()
            
            # Get headers with performance monitoring
            with self.performance_monitor.monitor_operation(
                "csv_header_generation",
                include_validation=include_validation
            ):
                headers = self.get_csv_headers(include_validation=include_validation)
            
            # Create CSV writer
            writer = csv.DictWriter(output, fieldnames=headers, 
                                  quoting=csv.QUOTE_MINIMAL, 
                                  lineterminator='\n')
            
            # Write header row
            writer.writeheader()
            
            # Write component rows with performance monitoring
            with self.performance_monitor.monitor_operation(
                "csv_row_formatting",
                component_count=len(components),
                include_validation=include_validation
            ):
                for component in components:
                    row_data = self.format_component_row(
                        component, 
                        validation_results.get(component.id) if validation_results else None,
                        include_validation=include_validation
                    )
                    writer.writerow(row_data)
            
            # Get CSV content
            csv_content = output.getvalue()
            output.close()
            
            # Write to file if specified
            if output_file:
                with self.performance_monitor.monitor_operation(
                    "csv_file_writing",
                    output_file=output_file,
                    content_size=len(csv_content)
                ):
                    with open(output_file, 'w', newline='', encoding='utf-8') as f:
                        f.write(csv_content)
                    self.logger.info(f"CSV output written to {output_file}")
            
            self.logger.info(f"Generated CSV with {len(components)} components")
            return csv_content
            
        except Exception as e:
            self.logger.error(f"Failed to generate CSV: {str(e)}")
            raise
    
    def format_component_row(self, component: Component, 
                           validation_result: Optional[ValidationResult] = None,
                           include_validation: bool = True) -> Dict[str, Any]:
        """
        Format a single component as a CSV row.
        
        Args:
            component: Component to format
            validation_result: Optional validation result for the component
            include_validation: Whether to include validation columns
            
        Returns:
            Dictionary representing CSV row
        """
        try:
            # Basic component information
            row = {
                'component_id': component.id,
                'component_type': component.type.value,
                'quantity': component.quantity,
                'confidence': round(component.confidence, 3) if component.confidence else None
            }
            
            # Dimension information
            if component.dimensions:
                dims = component.dimensions
                row.update({
                    'width_mm': self._format_dimension(dims.width),
                    'height_mm': self._format_dimension(dims.height),
                    'length_mm': self._format_dimension(dims.length),
                    'thickness_mm': self._format_dimension(dims.thickness),
                    'diameter_mm': self._format_dimension(dims.diameter),
                    'dimension_unit': dims.unit or ''
                })
            else:
                row.update({
                    'width_mm': None,
                    'height_mm': None,
                    'length_mm': None,
                    'thickness_mm': None,
                    'diameter_mm': None,
                    'dimension_unit': ''
                })
            
            # Material information
            if component.material:
                mat = component.material
                row.update({
                    'material_grade': self._escape_csv_content(mat.grade or ''),
                    'material_specification': self._escape_csv_content(mat.specification or ''),
                    'yield_strength_psi': self._format_strength(mat.yield_strength),
                    'tensile_strength_psi': self._format_strength(mat.tensile_strength)
                })
            else:
                row.update({
                    'material_grade': '',
                    'material_specification': '',
                    'yield_strength_psi': None,
                    'tensile_strength_psi': None
                })
            
            # Location information
            if component.location:
                loc = component.location
                row.update({
                    'location_x': round(loc.x, 1) if loc.x is not None else None,
                    'location_y': round(loc.y, 1) if loc.y is not None else None,
                    'page_number': loc.page_number
                })
            else:
                row.update({
                    'location_x': None,
                    'location_y': None,
                    'page_number': None
                })
            
            # Validation information
            if include_validation:
                if validation_result:
                    row.update({
                        'validation_status': 'VALID' if validation_result.is_valid else 'INVALID',
                        'validation_issues': self._format_validation_issues(validation_result.issues)
                    })
                else:
                    row.update({
                        'validation_status': 'NOT_VALIDATED',
                        'validation_issues': ''
                    })
            
            # Handle missing data
            row = self.handle_missing_data(row)
            
            return row
            
        except Exception as e:
            self.logger.error(f"Failed to format component row for {component.id}: {str(e)}")
            # Return minimal row with error indication
            return {
                'component_id': component.id,
                'component_type': component.type.value if component.type else 'UNKNOWN',
                'quantity': component.quantity or 1,
                'validation_status': 'ERROR',
                'validation_issues': f'Formatting error: {str(e)}'
            }
    
    def get_csv_headers(self, include_validation: bool = True) -> List[str]:
        """
        Get CSV column headers.
        
        Args:
            include_validation: Whether to include validation columns
            
        Returns:
            List of column headers
        """
        headers = self.standard_headers.copy()
        
        if not include_validation:
            # Remove validation columns
            validation_columns = ['validation_status', 'validation_issues']
            headers = [h for h in headers if h not in validation_columns]
        
        # Add any additional headers
        headers.extend(self.additional_headers)
        
        return headers
    
    def handle_missing_data(self, row_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle missing data in CSV row with consistent formatting.
        
        Args:
            row_data: Dictionary representing CSV row
            
        Returns:
            Row data with missing values handled
        """
        # Define how to handle different types of missing data
        missing_value_handlers = {
            # Numeric fields - use None (will become empty in CSV)
            'width_mm': None,
            'height_mm': None,
            'length_mm': None,
            'thickness_mm': None,
            'diameter_mm': None,
            'yield_strength_psi': None,
            'tensile_strength_psi': None,
            'location_x': None,
            'location_y': None,
            'page_number': None,
            'confidence': None,
            'quantity': 1,  # Default quantity
            
            # String fields - use empty string
            'component_id': 'UNKNOWN',
            'component_type': 'UNKNOWN',
            'dimension_unit': '',
            'material_grade': '',
            'material_specification': '',
            'validation_status': 'NOT_VALIDATED',
            'validation_issues': ''
        }
        
        # Apply missing value handling
        for field, default_value in missing_value_handlers.items():
            if field in row_data and (row_data[field] is None or row_data[field] == ''):
                row_data[field] = default_value
        
        return row_data
    
    def add_custom_column(self, column_name: str, default_value: Any = '') -> None:
        """
        Add a custom column to the CSV output.
        
        Args:
            column_name: Name of the column to add
            default_value: Default value for the column
        """
        if column_name not in self.additional_headers:
            self.additional_headers.append(column_name)
            self.logger.info(f"Added custom column: {column_name}")
    
    def remove_custom_column(self, column_name: str) -> None:
        """
        Remove a custom column from the CSV output.
        
        Args:
            column_name: Name of the column to remove
        """
        if column_name in self.additional_headers:
            self.additional_headers.remove(column_name)
            self.logger.info(f"Removed custom column: {column_name}")
    
    def get_summary_statistics(self, components: List[Component]) -> Dict[str, Any]:
        """
        Generate summary statistics for the component list.
        
        Args:
            components: List of components to analyze
            
        Returns:
            Dictionary with summary statistics
        """
        if not components:
            return {
                'total_components': 0,
                'total_quantity': 0,
                'component_types': {},
                'average_confidence': 0.0,
                'components_with_dimensions': 0,
                'components_with_materials': 0,
                'components_with_locations': 0
            }
        
        # Count by type
        type_counts = {}
        total_quantity = 0
        confidences = []
        
        dims_count = 0
        materials_count = 0
        locations_count = 0
        
        for component in components:
            # Type counting
            comp_type = component.type.value
            type_counts[comp_type] = type_counts.get(comp_type, 0) + component.quantity
            total_quantity += component.quantity
            
            # Confidence tracking
            if component.confidence is not None:
                confidences.append(component.confidence)
            
            # Completeness tracking
            if component.dimensions:
                dims_count += 1
            if component.material:
                materials_count += 1
            if component.location:
                locations_count += 1
        
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        return {
            'total_components': len(components),
            'total_quantity': total_quantity,
            'component_types': type_counts,
            'average_confidence': round(avg_confidence, 3),
            'components_with_dimensions': dims_count,
            'components_with_materials': materials_count,
            'components_with_locations': locations_count,
            'completeness_percentage': {
                'dimensions': round((dims_count / len(components)) * 100, 1),
                'materials': round((materials_count / len(components)) * 100, 1),
                'locations': round((locations_count / len(components)) * 100, 1)
            }
        }
    
    def _format_dimension(self, value: Optional[float]) -> Optional[float]:
        """Format dimension value for CSV output."""
        if value is None:
            return None
        return round(value, 2)
    
    def _format_strength(self, value: Optional[float]) -> Optional[int]:
        """Format strength value for CSV output."""
        if value is None:
            return None
        return int(round(value))
    
    def _format_validation_issues(self, issues: List[Any]) -> str:
        """Format validation issues for CSV output."""
        if not issues:
            return ''
        
        # Extract issue descriptions and join with semicolons
        issue_descriptions = []
        for issue in issues:
            if hasattr(issue, 'description'):
                desc = issue.description
            elif isinstance(issue, dict) and 'description' in issue:
                desc = issue['description']
            else:
                desc = str(issue)
            
            # Escape special characters for CSV
            desc = self._escape_csv_content(desc)
            issue_descriptions.append(desc)
        
        return '; '.join(issue_descriptions)
    
    def _escape_csv_content(self, content: str) -> str:
        """
        Escape special characters in CSV content.
        
        Args:
            content: String content to escape
            
        Returns:
            Escaped content safe for CSV
        """
        if not isinstance(content, str):
            content = str(content)
        
        # Replace problematic characters
        content = content.replace('\n', ' ')  # Replace newlines with spaces
        content = content.replace('\r', ' ')  # Replace carriage returns
        content = content.replace('\t', ' ')  # Replace tabs with spaces
        
        # Remove or replace other control characters
        content = ''.join(char if ord(char) >= 32 or char in '\n\r\t' else ' ' for char in content)
        
        # Trim excessive whitespace
        content = ' '.join(content.split())
        
        return content