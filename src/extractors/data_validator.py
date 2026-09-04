"""Data validation and quality assurance for extracted steel components."""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..models.component import Component, ComponentType, ComponentDimensions, MaterialSpec
from ..models.processing import ValidationResult, ValidationIssue


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class DimensionRange:
    """Valid range for a dimension."""
    min_value: float
    max_value: float
    unit: str
    description: str


@dataclass
class MaterialStandard:
    """Standard material specification."""
    grade: str
    specification: str
    yield_strength_range: Optional[Tuple[float, float]] = None
    tensile_strength_range: Optional[Tuple[float, float]] = None
    common_applications: List[str] = None


class DataValidator:
    """Validates extracted component data for consistency and reasonableness."""
    
    def __init__(self):
        self.logger = logging.getLogger('steel_parser.data_validator')
        
        # Define reasonable dimension ranges for steel components (in mm)
        self.dimension_ranges = {
            ComponentType.BEAM: {
                'width': DimensionRange(100, 1000, 'mm', 'Beam width (flange width)'),
                'height': DimensionRange(150, 1500, 'mm', 'Beam depth'),
                'thickness': DimensionRange(5, 50, 'mm', 'Flange/web thickness'),
                'length': DimensionRange(1000, 20000, 'mm', 'Beam span')
            },
            ComponentType.COLUMN: {
                'width': DimensionRange(100, 800, 'mm', 'Column width'),
                'height': DimensionRange(100, 800, 'mm', 'Column depth'),
                'thickness': DimensionRange(5, 50, 'mm', 'Flange/web thickness'),
                'length': DimensionRange(2000, 15000, 'mm', 'Column height')
            },
            ComponentType.PLATE: {
                'width': DimensionRange(50, 3000, 'mm', 'Plate width'),
                'height': DimensionRange(50, 3000, 'mm', 'Plate height'),
                'thickness': DimensionRange(3, 100, 'mm', 'Plate thickness')
            },
            ComponentType.BOLT: {
                'diameter': DimensionRange(6, 50, 'mm', 'Bolt diameter'),
                'length': DimensionRange(20, 300, 'mm', 'Bolt length')
            },
            ComponentType.WELD: {
                'thickness': DimensionRange(3, 25, 'mm', 'Weld size')
            }
        }
        
        # Define standard steel grades and their properties
        self.material_standards = {
            'A36': MaterialStandard(
                grade='A36',
                specification='ASTM',
                yield_strength_range=(36000, 36000),  # psi
                tensile_strength_range=(58000, 80000),
                common_applications=['General construction', 'Buildings', 'Bridges']
            ),
            'A572': MaterialStandard(
                grade='A572',
                specification='ASTM',
                yield_strength_range=(42000, 65000),  # Varies by grade
                tensile_strength_range=(60000, 80000),
                common_applications=['High-strength construction', 'Buildings']
            ),
            'A992': MaterialStandard(
                grade='A992',
                specification='ASTM',
                yield_strength_range=(50000, 65000),
                tensile_strength_range=(65000, 80000),
                common_applications=['Wide flange beams', 'Building frames']
            ),
            'Grade 50': MaterialStandard(
                grade='Grade 50',
                specification='AISC',
                yield_strength_range=(50000, 50000),
                tensile_strength_range=(65000, 65000),
                common_applications=['Structural steel', 'High-strength applications']
            )
        }
        
        # Common steel section patterns
        self.section_patterns = {
            'wide_flange': re.compile(r'W(\d+)x(\d+)', re.IGNORECASE),
            'standard_beam': re.compile(r'S(\d+)x(\d+)', re.IGNORECASE),
            'channel': re.compile(r'C(\d+)x(\d+)', re.IGNORECASE),
            'angle': re.compile(r'L(\d+)x(\d+)x(\d+)', re.IGNORECASE),
            'hss': re.compile(r'HSS(\d+)x(\d+)x(\d+)', re.IGNORECASE)
        }
    
    def validate_dimensions(self, component: Component) -> ValidationResult:
        """
        Checks dimension ranges and consistency for a component.
        
        Args:
            component: Component to validate
            
        Returns:
            ValidationResult with validation status and issues
        """
        try:
            issues = []
            confidence = 1.0
            
            if not component.dimensions:
                issues.append(ValidationIssue(
                    component_id=component.id,
                    issue_type="missing_dimensions",
                    description="Component has no dimension information",
                    severity=ValidationSeverity.WARNING.value
                ))
                confidence = 0.5
                return ValidationResult(is_valid=True, confidence=confidence, issues=issues)
            
            dimensions = component.dimensions
            component_type = component.type
            
            # Get valid ranges for this component type
            if component_type not in self.dimension_ranges:
                issues.append(ValidationIssue(
                    component_id=component.id,
                    issue_type="unknown_component_type",
                    description=f"No validation rules for component type: {component_type.value}",
                    severity=ValidationSeverity.INFO.value
                ))
                return ValidationResult(is_valid=True, confidence=0.8, issues=issues)
            
            ranges = self.dimension_ranges[component_type]
            
            # Convert dimensions to mm for validation
            dimensions_mm = self._convert_dimensions_to_mm(dimensions)
            
            # Validate each dimension
            for dim_name, value in dimensions_mm.items():
                if value is None:
                    continue
                
                if dim_name in ranges:
                    range_def = ranges[dim_name]
                    
                    if value < range_def.min_value:
                        issues.append(ValidationIssue(
                            component_id=component.id,
                            issue_type="dimension_too_small",
                            description=f"{dim_name.title()} {value:.1f}mm is below minimum {range_def.min_value}mm for {component_type.value}",
                            severity=ValidationSeverity.WARNING.value,
                            suggested_fix=f"Check if {dim_name} should be at least {range_def.min_value}mm"
                        ))
                        confidence *= 0.8
                    
                    elif value > range_def.max_value:
                        issues.append(ValidationIssue(
                            component_id=component.id,
                            issue_type="dimension_too_large",
                            description=f"{dim_name.title()} {value:.1f}mm exceeds maximum {range_def.max_value}mm for {component_type.value}",
                            severity=ValidationSeverity.WARNING.value,
                            suggested_fix=f"Check if {dim_name} should be at most {range_def.max_value}mm"
                        ))
                        confidence *= 0.8
            
            # Check dimension consistency
            consistency_issues = self._check_dimension_consistency(component, dimensions_mm)
            issues.extend(consistency_issues)
            if consistency_issues:
                confidence *= 0.9
            
            is_valid = not any(issue.severity == ValidationSeverity.ERROR.value for issue in issues)
            
            self.logger.debug(f"Validated dimensions for {component.id}: {len(issues)} issues, confidence {confidence:.2f}")
            
            return ValidationResult(
                is_valid=is_valid,
                confidence=confidence,
                issues=issues
            )
            
        except Exception as e:
            self.logger.error(f"Failed to validate dimensions for {component.id}: {str(e)}")
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                issues=[ValidationIssue(
                    component_id=component.id,
                    issue_type="validation_error",
                    description=f"Dimension validation failed: {str(e)}",
                    severity=ValidationSeverity.ERROR.value
                )]
            )
    
    def validate_materials(self, material_spec: MaterialSpec) -> ValidationResult:
        """
        Validates material specifications against steel grade standards.
        
        Args:
            material_spec: Material specification to validate
            
        Returns:
            ValidationResult with validation status and issues
        """
        try:
            issues = []
            confidence = 1.0
            
            if not material_spec:
                return ValidationResult(
                    is_valid=True,
                    confidence=0.5,
                    issues=[ValidationIssue(
                        component_id="unknown",
                        issue_type="missing_material",
                        description="No material specification provided",
                        severity=ValidationSeverity.INFO.value
                    )]
                )
            
            # Validate grade
            if material_spec.grade:
                grade_validation = self._validate_material_grade(material_spec.grade)
                issues.extend(grade_validation['issues'])
                confidence *= grade_validation['confidence']
            
            # Validate specification
            if material_spec.specification:
                spec_validation = self._validate_material_specification(material_spec.specification)
                issues.extend(spec_validation['issues'])
                confidence *= spec_validation['confidence']
            
            # Validate strength values
            if material_spec.yield_strength or material_spec.tensile_strength:
                strength_validation = self._validate_strength_values(material_spec)
                issues.extend(strength_validation['issues'])
                confidence *= strength_validation['confidence']
            
            # Cross-validate grade and strength consistency
            if material_spec.grade and material_spec.yield_strength:
                consistency_validation = self._validate_grade_strength_consistency(material_spec)
                issues.extend(consistency_validation['issues'])
                confidence *= consistency_validation['confidence']
            
            is_valid = not any(issue.severity == ValidationSeverity.ERROR.value for issue in issues)
            
            return ValidationResult(
                is_valid=is_valid,
                confidence=confidence,
                issues=issues
            )
            
        except Exception as e:
            self.logger.error(f"Failed to validate material: {str(e)}")
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                issues=[ValidationIssue(
                    component_id="unknown",
                    issue_type="validation_error",
                    description=f"Material validation failed: {str(e)}",
                    severity=ValidationSeverity.ERROR.value
                )]
            )
    
    def calculate_confidence(self, component: Component) -> float:
        """
        Assigns confidence score to extracted data based on multiple factors.
        
        Args:
            component: Component to calculate confidence for
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        try:
            confidence_factors = []
            
            # Base confidence from detection
            base_confidence = component.confidence
            confidence_factors.append(('detection', base_confidence))
            
            # Dimension completeness factor
            if component.dimensions:
                dim_completeness = self._calculate_dimension_completeness(component.dimensions)
                confidence_factors.append(('dimensions', dim_completeness))
            else:
                confidence_factors.append(('dimensions', 0.3))  # Low confidence without dimensions
            
            # Material completeness factor
            if component.material:
                mat_completeness = self._calculate_material_completeness(component.material)
                confidence_factors.append(('material', mat_completeness))
            else:
                confidence_factors.append(('material', 0.5))  # Neutral without material
            
            # Validation results factor
            dim_validation = self.validate_dimensions(component)
            mat_validation = self.validate_materials(component.material)
            
            validation_confidence = (dim_validation.confidence + mat_validation.confidence) / 2
            confidence_factors.append(('validation', validation_confidence))
            
            # Quantity factor (higher confidence for grouped components)
            quantity_factor = min(1.0, 0.7 + (component.quantity - 1) * 0.1)
            confidence_factors.append(('quantity', quantity_factor))
            
            # Calculate weighted average
            weights = {
                'detection': 0.3,
                'dimensions': 0.2,
                'material': 0.2,
                'validation': 0.2,
                'quantity': 0.1
            }
            
            weighted_confidence = sum(
                weights[factor] * confidence 
                for factor, confidence in confidence_factors
            )
            
            # Ensure confidence is within valid range
            final_confidence = max(0.0, min(1.0, weighted_confidence))
            
            self.logger.debug(f"Calculated confidence for {component.id}: {final_confidence:.3f} "
                            f"(factors: {dict(confidence_factors)})")
            
            return final_confidence
            
        except Exception as e:
            self.logger.error(f"Failed to calculate confidence for {component.id}: {str(e)}")
            return 0.5  # Default confidence on error
    
    def _convert_dimensions_to_mm(self, dimensions: ComponentDimensions) -> Dict[str, Optional[float]]:
        """Convert dimensions to millimeters for validation."""
        conversion_factors = {
            'mm': 1.0,
            'in': 25.4,
            'ft': 304.8,
            'm': 1000.0,
            'pixels': 1.0  # Assume 1:1 for pixel dimensions (will be flagged as unusual)
        }
        
        unit = dimensions.unit or 'mm'
        factor = conversion_factors.get(unit.lower(), 1.0)
        
        return {
            'width': dimensions.width * factor if dimensions.width else None,
            'height': dimensions.height * factor if dimensions.height else None,
            'length': dimensions.length * factor if dimensions.length else None,
            'thickness': dimensions.thickness * factor if dimensions.thickness else None,
            'diameter': dimensions.diameter * factor if dimensions.diameter else None
        }
    
    def _check_dimension_consistency(self, component: Component, 
                                   dimensions_mm: Dict[str, Optional[float]]) -> List[ValidationIssue]:
        """Check for dimension consistency issues."""
        issues = []
        
        # Check aspect ratios
        width = dimensions_mm.get('width')
        height = dimensions_mm.get('height')
        
        if width and height and width > 0 and height > 0:
            aspect_ratio = max(width, height) / min(width, height)
            
            # Flag unusual aspect ratios
            if component.type in [ComponentType.BEAM, ComponentType.COLUMN]:
                if aspect_ratio > 50:  # Very long/thin
                    issues.append(ValidationIssue(
                        component_id=component.id,
                        issue_type="unusual_aspect_ratio",
                        description=f"Unusual aspect ratio {aspect_ratio:.1f}:1 for {component.type.value}",
                        severity=ValidationSeverity.WARNING.value,
                        suggested_fix="Verify dimensions are correct"
                    ))
            elif component.type == ComponentType.PLATE:
                if aspect_ratio > 20:  # Very long/thin plate
                    issues.append(ValidationIssue(
                        component_id=component.id,
                        issue_type="unusual_aspect_ratio",
                        description=f"Unusual aspect ratio {aspect_ratio:.1f}:1 for plate",
                        severity=ValidationSeverity.INFO.value
                    ))
        
        return issues
    
    def _validate_material_grade(self, grade: str) -> Dict[str, Any]:
        """Validate material grade against known standards."""
        issues = []
        confidence = 1.0
        
        # Check if grade matches known standards
        grade_upper = grade.upper()
        
        # Check for exact matches
        if grade_upper in self.material_standards:
            return {'issues': issues, 'confidence': confidence}
        
        # Check for pattern matches
        recognized = False
        for pattern_name, pattern in self.section_patterns.items():
            if pattern.match(grade):
                recognized = True
                break
        
        if not recognized:
            # Check for common grade patterns
            common_patterns = [
                r'A\d+',  # ASTM grades
                r'Grade\s*\d+',  # Grade specifications
                r'S\d+',  # Standard sections
                r'W\d+x\d+',  # Wide flanges
            ]
            
            for pattern_str in common_patterns:
                if re.match(pattern_str, grade, re.IGNORECASE):
                    recognized = True
                    break
        
        if not recognized:
            issues.append(ValidationIssue(
                component_id="unknown",
                issue_type="unrecognized_grade",
                description=f"Material grade '{grade}' not recognized in standard databases",
                severity=ValidationSeverity.WARNING.value,
                suggested_fix="Verify grade specification is correct"
            ))
            confidence = 0.7
        
        return {'issues': issues, 'confidence': confidence}
    
    def _validate_material_specification(self, specification: str) -> Dict[str, Any]:
        """Validate material specification standard."""
        issues = []
        confidence = 1.0
        
        known_specs = ['ASTM', 'AISC', 'EN', 'ISO', 'JIS', 'BS']
        
        if specification.upper() not in known_specs:
            issues.append(ValidationIssue(
                component_id="unknown",
                issue_type="unknown_specification",
                description=f"Material specification '{specification}' not in common standards",
                severity=ValidationSeverity.INFO.value,
                suggested_fix=f"Common specifications: {', '.join(known_specs)}"
            ))
            confidence = 0.8
        
        return {'issues': issues, 'confidence': confidence}
    
    def _validate_strength_values(self, material_spec: MaterialSpec) -> Dict[str, Any]:
        """Validate strength values are reasonable."""
        issues = []
        confidence = 1.0
        
        # Reasonable ranges for steel (in psi)
        yield_range = (20000, 100000)
        tensile_range = (40000, 150000)
        
        if material_spec.yield_strength:
            if not (yield_range[0] <= material_spec.yield_strength <= yield_range[1]):
                issues.append(ValidationIssue(
                    component_id="unknown",
                    issue_type="unusual_yield_strength",
                    description=f"Yield strength {material_spec.yield_strength} psi outside typical range {yield_range}",
                    severity=ValidationSeverity.WARNING.value
                ))
                confidence *= 0.8
        
        if material_spec.tensile_strength:
            if not (tensile_range[0] <= material_spec.tensile_strength <= tensile_range[1]):
                issues.append(ValidationIssue(
                    component_id="unknown",
                    issue_type="unusual_tensile_strength",
                    description=f"Tensile strength {material_spec.tensile_strength} psi outside typical range {tensile_range}",
                    severity=ValidationSeverity.WARNING.value
                ))
                confidence *= 0.8
        
        # Check yield vs tensile relationship
        if (material_spec.yield_strength and material_spec.tensile_strength and
            material_spec.yield_strength >= material_spec.tensile_strength):
            issues.append(ValidationIssue(
                component_id="unknown",
                issue_type="strength_relationship_error",
                description="Yield strength should be less than tensile strength",
                severity=ValidationSeverity.ERROR.value,
                suggested_fix="Verify strength values are correct"
            ))
            confidence *= 0.5
        
        return {'issues': issues, 'confidence': confidence}
    
    def _validate_grade_strength_consistency(self, material_spec: MaterialSpec) -> Dict[str, Any]:
        """Validate consistency between grade and strength values."""
        issues = []
        confidence = 1.0
        
        grade_upper = material_spec.grade.upper()
        
        if grade_upper in self.material_standards:
            standard = self.material_standards[grade_upper]
            
            if (material_spec.yield_strength and standard.yield_strength_range):
                min_yield, max_yield = standard.yield_strength_range
                if not (min_yield <= material_spec.yield_strength <= max_yield):
                    issues.append(ValidationIssue(
                        component_id="unknown",
                        issue_type="grade_strength_mismatch",
                        description=f"Yield strength {material_spec.yield_strength} psi inconsistent with {grade_upper} range {standard.yield_strength_range}",
                        severity=ValidationSeverity.WARNING.value,
                        suggested_fix="Verify grade and strength values match"
                    ))
                    confidence *= 0.8
        
        return {'issues': issues, 'confidence': confidence}
    
    def _calculate_dimension_completeness(self, dimensions: ComponentDimensions) -> float:
        """Calculate completeness score for dimensions."""
        total_fields = 5  # width, height, length, thickness, diameter
        filled_fields = sum(1 for field in [
            dimensions.width, dimensions.height, dimensions.length,
            dimensions.thickness, dimensions.diameter
        ] if field is not None)
        
        base_completeness = filled_fields / total_fields
        
        # Bonus for having unit specified
        if dimensions.unit and dimensions.unit != 'pixels':
            base_completeness = min(1.0, base_completeness + 0.1)
        
        return base_completeness
    
    def _calculate_material_completeness(self, material: MaterialSpec) -> float:
        """Calculate completeness score for material specification."""
        total_fields = 4  # grade, specification, yield_strength, tensile_strength
        filled_fields = sum(1 for field in [
            material.grade, material.specification,
            material.yield_strength, material.tensile_strength
        ] if field is not None)
        
        return filled_fields / total_fields
    
    def flag_inconsistencies(self, components: List[Component]) -> List[ValidationIssue]:
        """
        Identify potential data quality issues across multiple components.
        
        Args:
            components: List of components to analyze for inconsistencies
            
        Returns:
            List of validation issues found
        """
        try:
            issues = []
            
            if not components:
                return issues
            
            # Check for duplicate component IDs
            duplicate_issues = self._check_duplicate_ids(components)
            issues.extend(duplicate_issues)
            
            # Check for inconsistent similar components
            similarity_issues = self._check_similar_component_consistency(components)
            issues.extend(similarity_issues)
            
            # Check for unrealistic component distributions
            distribution_issues = self._check_component_distribution(components)
            issues.extend(distribution_issues)
            
            # Check for location inconsistencies
            location_issues = self._check_location_consistency(components)
            issues.extend(location_issues)
            
            # Check for material/dimension mismatches
            mismatch_issues = self._check_material_dimension_mismatches(components)
            issues.extend(mismatch_issues)
            
            # Check for confidence anomalies
            confidence_issues = self._check_confidence_anomalies(components)
            issues.extend(confidence_issues)
            
            self.logger.info(f"Found {len(issues)} inconsistency issues across {len(components)} components")
            
            return issues
            
        except Exception as e:
            self.logger.error(f"Failed to flag inconsistencies: {str(e)}")
            return [ValidationIssue(
                component_id="system",
                issue_type="inconsistency_check_error",
                description=f"Inconsistency detection failed: {str(e)}",
                severity=ValidationSeverity.ERROR.value
            )]
    
    def generate_confidence_report(self, components: List[Component]) -> Dict[str, Any]:
        """
        Generate comprehensive confidence reporting for components.
        
        Args:
            components: List of components to analyze
            
        Returns:
            Dictionary with confidence statistics and analysis
        """
        try:
            if not components:
                return {
                    'total_components': 0,
                    'average_confidence': 0.0,
                    'confidence_distribution': {},
                    'low_confidence_components': [],
                    'high_confidence_components': [],
                    'confidence_by_type': {},
                    'recommendations': []
                }
            
            # Calculate updated confidence scores
            updated_confidences = []
            for component in components:
                confidence = self.calculate_confidence(component)
                updated_confidences.append(confidence)
            
            # Basic statistics
            avg_confidence = sum(updated_confidences) / len(updated_confidences)
            min_confidence = min(updated_confidences)
            max_confidence = max(updated_confidences)
            
            # Confidence distribution
            confidence_ranges = {
                'very_low': (0.0, 0.3),
                'low': (0.3, 0.5),
                'medium': (0.5, 0.7),
                'high': (0.7, 0.9),
                'very_high': (0.9, 1.0)
            }
            
            distribution = {}
            for range_name, (min_val, max_val) in confidence_ranges.items():
                count = sum(1 for conf in updated_confidences 
                           if min_val <= conf < max_val or (range_name == 'very_high' and conf == 1.0))
                distribution[range_name] = {
                    'count': count,
                    'percentage': (count / len(components)) * 100
                }
            
            # Identify low and high confidence components
            low_confidence_threshold = 0.5
            high_confidence_threshold = 0.8
            
            low_confidence_components = [
                {
                    'id': comp.id,
                    'type': comp.type.value,
                    'confidence': conf,
                    'issues': self._identify_confidence_issues(comp)
                }
                for comp, conf in zip(components, updated_confidences)
                if conf < low_confidence_threshold
            ]
            
            high_confidence_components = [
                {
                    'id': comp.id,
                    'type': comp.type.value,
                    'confidence': conf
                }
                for comp, conf in zip(components, updated_confidences)
                if conf >= high_confidence_threshold
            ]
            
            # Confidence by component type
            confidence_by_type = {}
            for comp, conf in zip(components, updated_confidences):
                comp_type = comp.type.value
                if comp_type not in confidence_by_type:
                    confidence_by_type[comp_type] = []
                confidence_by_type[comp_type].append(conf)
            
            # Calculate averages by type
            for comp_type in confidence_by_type:
                confidences = confidence_by_type[comp_type]
                confidence_by_type[comp_type] = {
                    'count': len(confidences),
                    'average': sum(confidences) / len(confidences),
                    'min': min(confidences),
                    'max': max(confidences)
                }
            
            # Generate recommendations
            recommendations = self._generate_confidence_recommendations(
                components, updated_confidences, distribution
            )
            
            return {
                'total_components': len(components),
                'average_confidence': avg_confidence,
                'min_confidence': min_confidence,
                'max_confidence': max_confidence,
                'confidence_distribution': distribution,
                'low_confidence_components': low_confidence_components,
                'high_confidence_components': high_confidence_components,
                'confidence_by_type': confidence_by_type,
                'recommendations': recommendations
            }
            
        except Exception as e:
            self.logger.error(f"Failed to generate confidence report: {str(e)}")
            return {'error': str(e)}
    
    def _check_duplicate_ids(self, components: List[Component]) -> List[ValidationIssue]:
        """Check for duplicate component IDs."""
        issues = []
        seen_ids = set()
        
        for component in components:
            if component.id in seen_ids:
                issues.append(ValidationIssue(
                    component_id=component.id,
                    issue_type="duplicate_id",
                    description=f"Duplicate component ID: {component.id}",
                    severity=ValidationSeverity.ERROR.value,
                    suggested_fix="Ensure all component IDs are unique"
                ))
            else:
                seen_ids.add(component.id)
        
        return issues
    
    def _check_similar_component_consistency(self, components: List[Component]) -> List[ValidationIssue]:
        """Check for inconsistencies in similar components."""
        issues = []
        
        # Group components by type
        by_type = {}
        for comp in components:
            comp_type = comp.type
            if comp_type not in by_type:
                by_type[comp_type] = []
            by_type[comp_type].append(comp)
        
        # Check consistency within each type
        for comp_type, type_components in by_type.items():
            if len(type_components) < 2:
                continue
            
            # Check for unusual variation in dimensions
            dimensions_list = [comp.dimensions for comp in type_components if comp.dimensions]
            if len(dimensions_list) > 1:
                dim_issues = self._check_dimension_variation(comp_type, dimensions_list)
                issues.extend(dim_issues)
            
            # Check for material inconsistencies
            materials_list = [comp.material for comp in type_components if comp.material]
            if len(materials_list) > 1:
                mat_issues = self._check_material_variation(comp_type, materials_list)
                issues.extend(mat_issues)
        
        return issues
    
    def _check_component_distribution(self, components: List[Component]) -> List[ValidationIssue]:
        """Check for unrealistic component distributions."""
        issues = []
        
        # Count components by type
        type_counts = {}
        for comp in components:
            comp_type = comp.type.value
            type_counts[comp_type] = type_counts.get(comp_type, 0) + comp.quantity
        
        total_components = sum(type_counts.values())
        
        # Check for unusual distributions
        if total_components > 10:  # Only check for larger sets
            bolt_ratio = type_counts.get('bolt', 0) / total_components
            beam_ratio = type_counts.get('beam', 0) / total_components
            
            # Unusual ratios that might indicate detection issues
            if bolt_ratio > 0.8:  # Too many bolts
                issues.append(ValidationIssue(
                    component_id="distribution",
                    issue_type="unusual_distribution",
                    description=f"Unusually high bolt ratio: {bolt_ratio:.1%} of components",
                    severity=ValidationSeverity.WARNING.value,
                    suggested_fix="Verify bolt detection is not over-sensitive"
                ))
            
            if beam_ratio > 0.7:  # Too many beams
                issues.append(ValidationIssue(
                    component_id="distribution",
                    issue_type="unusual_distribution",
                    description=f"Unusually high beam ratio: {beam_ratio:.1%} of components",
                    severity=ValidationSeverity.WARNING.value,
                    suggested_fix="Verify beam detection is not over-sensitive"
                ))
        
        return issues
    
    def _check_location_consistency(self, components: List[Component]) -> List[ValidationIssue]:
        """Check for location-related inconsistencies."""
        issues = []
        
        # Check for components with missing locations
        missing_location_count = sum(1 for comp in components if not comp.location)
        if missing_location_count > 0:
            issues.append(ValidationIssue(
                component_id="location",
                issue_type="missing_locations",
                description=f"{missing_location_count} components missing location information",
                severity=ValidationSeverity.WARNING.value,
                suggested_fix="Ensure all components have location coordinates"
            ))
        
        # Check for components clustered at same location (potential detection error)
        located_components = [comp for comp in components if comp.location]
        if len(located_components) > 1:
            location_clusters = self._find_location_clusters(located_components)
            for cluster in location_clusters:
                if len(cluster) > 5:  # Many components at same location
                    issues.append(ValidationIssue(
                        component_id="location",
                        issue_type="location_clustering",
                        description=f"{len(cluster)} components clustered at similar location",
                        severity=ValidationSeverity.WARNING.value,
                        suggested_fix="Verify components are not incorrectly grouped"
                    ))
        
        return issues
    
    def _check_material_dimension_mismatches(self, components: List[Component]) -> List[ValidationIssue]:
        """Check for mismatches between materials and dimensions."""
        issues = []
        
        for component in components:
            if not (component.material and component.dimensions):
                continue
            
            # Check if material grade matches typical dimensions
            if component.material.grade and component.dimensions.width:
                # Example: W12x26 should have dimensions roughly matching 12" depth
                grade = component.material.grade
                width_mm = component.dimensions.width
                
                # Convert to inches for comparison with US steel sections
                width_inches = width_mm / 25.4 if component.dimensions.unit == 'mm' else width_mm
                
                # Check wide flange beam naming convention
                if grade.startswith('W') and component.type == ComponentType.BEAM:
                    try:
                        # Extract nominal depth from grade (e.g., W12x26 -> 12)
                        import re
                        match = re.match(r'W(\d+)x(\d+)', grade)
                        if match:
                            nominal_depth = int(match.group(1))
                            
                            # Allow reasonable tolerance (±20%)
                            if abs(width_inches - nominal_depth) > nominal_depth * 0.3:
                                issues.append(ValidationIssue(
                                    component_id=component.id,
                                    issue_type="material_dimension_mismatch",
                                    description=f"Material {grade} suggests {nominal_depth}\" depth but measured {width_inches:.1f}\"",
                                    severity=ValidationSeverity.WARNING.value,
                                    suggested_fix="Verify material grade or dimensions are correct"
                                ))
                    except (ValueError, AttributeError):
                        pass  # Skip if grade format is unexpected
        
        return issues
    
    def _check_confidence_anomalies(self, components: List[Component]) -> List[ValidationIssue]:
        """Check for confidence-related anomalies."""
        issues = []
        
        if not components:
            return issues
        
        confidences = [comp.confidence for comp in components]
        avg_confidence = sum(confidences) / len(confidences)
        
        # Check for components with unusually low confidence
        low_confidence_threshold = max(0.3, avg_confidence - 0.3)
        low_confidence_components = [
            comp for comp in components 
            if comp.confidence < low_confidence_threshold
        ]
        
        if len(low_confidence_components) > len(components) * 0.3:  # More than 30% low confidence
            issues.append(ValidationIssue(
                component_id="confidence",
                issue_type="low_confidence_pattern",
                description=f"{len(low_confidence_components)} components have unusually low confidence",
                severity=ValidationSeverity.WARNING.value,
                suggested_fix="Review detection parameters or image quality"
            ))
        
        return issues
    
    def _check_dimension_variation(self, comp_type: ComponentType, 
                                 dimensions_list: List[ComponentDimensions]) -> List[ValidationIssue]:
        """Check for unusual variation in dimensions for similar components."""
        issues = []
        
        # Extract width values for comparison
        widths = [d.width for d in dimensions_list if d.width is not None]
        heights = [d.height for d in dimensions_list if d.height is not None]
        
        # Check width variation
        if len(widths) > 2:
            width_variation = (max(widths) - min(widths)) / max(widths) if max(widths) > 0 else 0
            if width_variation > 0.5:  # More than 50% variation
                issues.append(ValidationIssue(
                    component_id=f"{comp_type.value}_group",
                    issue_type="high_dimension_variation",
                    description=f"High width variation ({width_variation:.1%}) in {comp_type.value} components",
                    severity=ValidationSeverity.INFO.value,
                    suggested_fix="Verify components are actually similar"
                ))
        
        # Check height variation
        if len(heights) > 2:
            height_variation = (max(heights) - min(heights)) / max(heights) if max(heights) > 0 else 0
            if height_variation > 0.5:  # More than 50% variation
                issues.append(ValidationIssue(
                    component_id=f"{comp_type.value}_group",
                    issue_type="high_dimension_variation",
                    description=f"High height variation ({height_variation:.1%}) in {comp_type.value} components",
                    severity=ValidationSeverity.INFO.value,
                    suggested_fix="Verify components are actually similar"
                ))
        
        return issues
    
    def _check_material_variation(self, comp_type: ComponentType, 
                                materials_list: List[MaterialSpec]) -> List[ValidationIssue]:
        """Check for unusual variation in materials for similar components."""
        issues = []
        
        # Extract grades for comparison
        grades = [m.grade for m in materials_list if m.grade]
        specifications = [m.specification for m in materials_list if m.specification]
        
        # Check grade consistency
        if len(set(grades)) > len(grades) * 0.5:  # More than 50% different grades
            issues.append(ValidationIssue(
                component_id=f"{comp_type.value}_group",
                issue_type="material_inconsistency",
                description=f"Multiple different material grades in {comp_type.value} components: {set(grades)}",
                severity=ValidationSeverity.INFO.value,
                suggested_fix="Verify materials are correctly identified"
            ))
        
        return issues
    
    def _find_location_clusters(self, components: List[Component], 
                              cluster_distance: float = 50.0) -> List[List[Component]]:
        """Find clusters of components at similar locations."""
        clusters = []
        used_components = set()
        
        for i, comp1 in enumerate(components):
            if i in used_components or not comp1.location:
                continue
            
            cluster = [comp1]
            used_components.add(i)
            
            for j, comp2 in enumerate(components):
                if j in used_components or not comp2.location or i == j:
                    continue
                
                # Calculate distance
                distance = ((comp1.location.x - comp2.location.x) ** 2 + 
                           (comp1.location.y - comp2.location.y) ** 2) ** 0.5
                
                if distance <= cluster_distance:
                    cluster.append(comp2)
                    used_components.add(j)
            
            if len(cluster) > 1:
                clusters.append(cluster)
        
        return clusters
    
    def _identify_confidence_issues(self, component: Component) -> List[str]:
        """Identify specific issues affecting component confidence."""
        issues = []
        
        if not component.dimensions:
            issues.append("Missing dimensions")
        elif not (component.dimensions.width or component.dimensions.height):
            issues.append("Incomplete dimensions")
        
        if not component.material:
            issues.append("Missing material specification")
        elif not (component.material.grade or component.material.specification):
            issues.append("Incomplete material specification")
        
        if component.confidence < 0.5:
            issues.append("Low detection confidence")
        
        if not component.location:
            issues.append("Missing location information")
        
        return issues
    
    def _generate_confidence_recommendations(self, components: List[Component], 
                                           confidences: List[float],
                                           distribution: Dict[str, Dict]) -> List[str]:
        """Generate recommendations for improving confidence."""
        recommendations = []
        
        avg_confidence = sum(confidences) / len(confidences)
        
        if avg_confidence < 0.6:
            recommendations.append("Overall confidence is low. Consider improving image quality or detection parameters.")
        
        if distribution['very_low']['percentage'] > 20:
            recommendations.append("Many components have very low confidence. Review detection thresholds.")
        
        if distribution['high']['percentage'] + distribution['very_high']['percentage'] < 30:
            recommendations.append("Few components have high confidence. Consider manual verification of results.")
        
        # Check for missing information
        missing_dims = sum(1 for comp in components if not comp.dimensions)
        missing_materials = sum(1 for comp in components if not comp.material)
        
        if missing_dims > len(components) * 0.3:
            recommendations.append("Many components missing dimensions. Improve dimension extraction.")
        
        if missing_materials > len(components) * 0.3:
            recommendations.append("Many components missing materials. Improve material specification extraction.")
        
        return recommendations