"""Extensible part extractor using plugin-style architecture."""

import logging
import numpy as np
from typing import List, Dict, Any, Optional, Type
import uuid

from ..models.component import Component, ComponentType, ComponentDimensions, MaterialSpec, Coordinates
from ..models.part_type_config import PartTypeConfigLoader, ComponentTypeConfig
from ..processors.image_extractor import BoundingBox
from .component_detector_base import ComponentDetector, BeamDetector, ColumnDetector, PlateDetector
from .dimension_extractor import DimensionExtractor
from ..utils.performance_monitor import get_performance_monitor, monitor_performance


class DetectorRegistry:
    """Registry for component detector classes."""
    
    def __init__(self):
        self._detectors: Dict[str, Type[ComponentDetector]] = {}
        self._register_default_detectors()
    
    def _register_default_detectors(self):
        """Register default detector classes."""
        self._detectors['beam'] = BeamDetector
        self._detectors['column'] = ColumnDetector
        self._detectors['plate'] = PlateDetector
    
    def register_detector(self, component_type: str, detector_class: Type[ComponentDetector]):
        """Register a new detector class for a component type."""
        self._detectors[component_type] = detector_class
    
    def get_detector_class(self, component_type: str) -> Optional[Type[ComponentDetector]]:
        """Get the detector class for a component type."""
        return self._detectors.get(component_type)
    
    def list_registered_types(self) -> List[str]:
        """Get list of registered component types."""
        return list(self._detectors.keys())


class ExtensiblePartExtractor:
    """Extensible part extractor using configuration-driven detection."""
    
    def __init__(self, config_dir: str = "config", config_file: str = "part_types.json"):
        """
        Initialize the extensible part extractor.
        
        Args:
            config_dir: Directory containing configuration files
            config_file: Configuration file name
        """
        self.logger = logging.getLogger('steel_parser.extensible_part_extractor')
        self.performance_monitor = get_performance_monitor()
        
        # Load configuration
        self.config_loader = PartTypeConfigLoader(config_dir)
        self.config_loader.load_from_file(config_file)
        self.registry = self.config_loader.get_registry()
        
        # Initialize detector registry
        self.detector_registry = DetectorRegistry()
        
        # Initialize detectors for enabled component types
        self.detectors: Dict[str, ComponentDetector] = {}
        self._initialize_detectors()
        
        # Initialize dimension extractor
        self.dimension_extractor = DimensionExtractor()
        
        self.logger.info(f"Initialized extensible part extractor with {len(self.detectors)} detectors")
    
    def _initialize_detectors(self):
        """Initialize detector instances for all enabled component types."""
        for config in self.registry.get_enabled_types():
            detector_class = self.detector_registry.get_detector_class(config.name)
            if detector_class:
                try:
                    detector = detector_class(config)
                    self.detectors[config.name] = detector
                    self.logger.debug(f"Initialized {config.name} detector")
                except Exception as e:
                    self.logger.error(f"Failed to initialize {config.name} detector: {e}")
            else:
                self.logger.warning(f"No detector class found for component type: {config.name}")
    
    @monitor_performance("steel_component_detection")
    def detect_steel_components(self, image: np.ndarray, page_number: int = 1) -> List[Component]:
        """
        Main detection pipeline for steel components using extensible architecture.
        
        Args:
            image: Preprocessed grayscale image
            page_number: Page number for coordinate reference
            
        Returns:
            List of detected Component objects
        """
        try:
            self.logger.info(f"Starting extensible component detection on page {page_number}")
            
            all_detections = []
            
            # Run each enabled detector with performance monitoring
            with self.performance_monitor.monitor_operation(
                "component_detector_execution",
                page_number=page_number,
                enabled_detectors=list(self.detectors.keys())
            ):
                for component_type, detector in self.detectors.items():
                    if not detector.is_enabled():
                        continue
                    
                    try:
                        with self.performance_monitor.monitor_operation(
                            f"{component_type}_detection",
                            page_number=page_number
                        ):
                            detections = detector.detect(image, page_number=page_number)
                            self.logger.debug(f"{component_type} detector found {len(detections)} candidates")
                            all_detections.extend(detections)
                    except Exception as e:
                        self.logger.error(f"Error in {component_type} detector: {e}")
            
            # Filter by confidence and apply non-maximum suppression
            with self.performance_monitor.monitor_operation(
                "detection_filtering_and_suppression",
                detection_count=len(all_detections)
            ):
                filtered_detections = self._filter_and_suppress(all_detections)
            
            # Convert detections to Component objects
            components = []
            with self.performance_monitor.monitor_operation(
                "detection_to_component_conversion",
                filtered_detection_count=len(filtered_detections)
            ):
                for detection in filtered_detections:
                    component = self._detection_to_component(detection, page_number)
                    if component:
                        # Enhance with dimensions and materials
                        component = self._enhance_component_with_details(component, image)
                        components.append(component)
            
            # Count quantities and update locations
            with self.performance_monitor.monitor_operation(
                "quantity_counting_and_location_update",
                component_count=len(components)
            ):
                components = self._count_quantities_and_update_locations(components)
            
            self.logger.info(f"Detected {len(components)} components on page {page_number}")
            return components
            
        except Exception as e:
            self.logger.error(f"Failed to detect steel components: {e}")
            return []
    
    def _filter_and_suppress(self, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter detections by confidence and apply non-maximum suppression."""
        if not detections:
            return []
        
        # Filter by confidence
        filtered = []
        for detection in detections:
            component_type = detection.get('component_type')
            if component_type in self.detectors:
                detector = self.detectors[component_type]
                if detection.get('confidence', 0) >= detector.get_confidence_threshold():
                    filtered.append(detection)
        
        # Apply non-maximum suppression
        return self._apply_non_maximum_suppression(filtered)
    
    def _apply_non_maximum_suppression(self, detections: List[Dict[str, Any]], 
                                     overlap_threshold: float = 0.5) -> List[Dict[str, Any]]:
        """Apply non-maximum suppression to remove overlapping detections."""
        if not detections:
            return []
        
        # Sort by confidence (descending)
        sorted_detections = sorted(detections, key=lambda x: x.get('confidence', 0), reverse=True)
        
        suppressed = []
        used = set()
        
        for i, detection1 in enumerate(sorted_detections):
            if i in used:
                continue
            
            suppressed.append(detection1)
            bbox1 = detection1.get('bbox', {})
            
            for j, detection2 in enumerate(sorted_detections[i+1:], i+1):
                if j in used:
                    continue
                
                bbox2 = detection2.get('bbox', {})
                
                # Calculate overlap
                overlap = self._calculate_bbox_overlap(bbox1, bbox2)
                if overlap > overlap_threshold:
                    used.add(j)
        
        return suppressed
    
    def _calculate_bbox_overlap(self, bbox1: Dict[str, Any], bbox2: Dict[str, Any]) -> float:
        """Calculate overlap ratio between two bounding boxes."""
        if not bbox1 or not bbox2:
            return 0.0
        
        # Extract coordinates
        x1_1, y1_1 = bbox1.get('x', 0), bbox1.get('y', 0)
        x2_1, y2_1 = x1_1 + bbox1.get('width', 0), y1_1 + bbox1.get('height', 0)
        
        x1_2, y1_2 = bbox2.get('x', 0), bbox2.get('y', 0)
        x2_2, y2_2 = x1_2 + bbox2.get('width', 0), y1_2 + bbox2.get('height', 0)
        
        # Calculate intersection
        x_left = max(x1_1, x1_2)
        y_top = max(y1_1, y1_2)
        x_right = min(x2_1, x2_2)
        y_bottom = min(y2_1, y2_2)
        
        if x_right < x_left or y_bottom < y_top:
            return 0.0
        
        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        
        # Calculate union
        area1 = bbox1.get('width', 0) * bbox1.get('height', 0)
        area2 = bbox2.get('width', 0) * bbox2.get('height', 0)
        union_area = area1 + area2 - intersection_area
        
        if union_area == 0:
            return 0.0
        
        return intersection_area / union_area
    
    def _detection_to_component(self, detection: Dict[str, Any], page_number: int) -> Optional[Component]:
        """Convert a detection result to a Component object."""
        try:
            bbox = detection.get('bbox', {})
            component_type_name = detection.get('component_type')
            
            if not bbox or not component_type_name:
                return None
            
            # Map component type name to enum
            component_type = self._get_component_type_enum(component_type_name)
            if not component_type:
                return None
            
            # Create component
            component_id = f"{component_type_name}_{uuid.uuid4().hex[:8]}"
            
            coordinates = Coordinates(
                x=bbox.get('x', 0),
                y=bbox.get('y', 0),
                page_number=page_number
            )
            
            component = Component(
                id=component_id,
                type=component_type,
                dimensions=ComponentDimensions(),
                material=MaterialSpec(),
                location=coordinates,
                confidence=detection.get('confidence', 0.0),
                quantity=1,
                extraction_metadata=detection.get('features', {})
            )
            
            return component
            
        except Exception as e:
            self.logger.error(f"Failed to convert detection to component: {e}")
            return None
    
    def _get_component_type_enum(self, type_name: str) -> Optional[ComponentType]:
        """Map component type name to ComponentType enum."""
        type_mapping = {
            'beam': ComponentType.BEAM,
            'column': ComponentType.COLUMN,
            'plate': ComponentType.PLATE,
            'bolt': ComponentType.BOLT,
            'weld': ComponentType.WELD
        }
        return type_mapping.get(type_name.lower())
    
    def _enhance_component_with_details(self, component: Component, image: np.ndarray) -> Component:
        """Enhance component with dimensions and material information."""
        try:
            # Extract dimensions
            dimensions = self.dimension_extractor.extract_dimensions(component, image)
            if dimensions:
                component.dimensions = dimensions
            
            # Extract materials
            materials = self.dimension_extractor.extract_material_specs(component, image)
            if materials:
                component.material = materials
            
            return component
            
        except Exception as e:
            self.logger.warning(f"Failed to enhance component {component.id}: {e}")
            return component
    
    def _count_quantities_and_update_locations(self, components: List[Component]) -> List[Component]:
        """Count quantities for similar components and update locations."""
        if not components:
            return components
        
        # Group similar components
        component_groups = {}
        
        for component in components:
            # Create a key based on type and approximate dimensions
            key = self._create_component_key(component)
            
            if key not in component_groups:
                component_groups[key] = []
            component_groups[key].append(component)
        
        # Update quantities and keep representative components
        final_components = []
        
        for group in component_groups.values():
            if not group:
                continue
            
            # Use the first component as representative
            representative = group[0]
            representative.quantity = len(group)
            
            # Collect all locations
            locations = [comp.location for comp in group]
            representative.extraction_metadata['all_locations'] = locations
            
            final_components.append(representative)
        
        return final_components
    
    def _create_component_key(self, component: Component) -> str:
        """Create a key for grouping similar components."""
        # Use type and rounded dimensions for grouping
        dims = component.dimensions
        key_parts = [component.type.value]
        
        if dims.length:
            key_parts.append(f"L{round(dims.length, -1)}")  # Round to nearest 10
        if dims.width:
            key_parts.append(f"W{round(dims.width, -1)}")
        if dims.height:
            key_parts.append(f"H{round(dims.height, -1)}")
        
        return "_".join(key_parts)
    
    def add_custom_detector(self, component_type: str, detector_class: Type[ComponentDetector], 
                          config: ComponentTypeConfig):
        """
        Add a custom detector for a new component type.
        
        Args:
            component_type: Name of the component type
            detector_class: Detector class implementing ComponentDetector
            config: Configuration for the component type
        """
        try:
            # Register the detector class
            self.detector_registry.register_detector(component_type, detector_class)
            
            # Register the component type configuration
            self.registry.register_type(config)
            
            # Initialize the detector
            detector = detector_class(config)
            self.detectors[component_type] = detector
            
            self.logger.info(f"Added custom detector for component type: {component_type}")
            
        except Exception as e:
            self.logger.error(f"Failed to add custom detector for {component_type}: {e}")
    
    def get_supported_types(self) -> List[str]:
        """Get list of supported component types."""
        return list(self.detectors.keys())
    
    def get_detector_config(self, component_type: str) -> Optional[ComponentTypeConfig]:
        """Get configuration for a component type."""
        return self.registry.get_type(component_type)
    
    def enable_component_type(self, component_type: str) -> bool:
        """Enable detection for a component type."""
        if self.registry.enable_type(component_type):
            # Reinitialize detectors
            self._initialize_detectors()
            return True
        return False
    
    def disable_component_type(self, component_type: str) -> bool:
        """Disable detection for a component type."""
        if self.registry.disable_type(component_type):
            # Remove from active detectors
            if component_type in self.detectors:
                del self.detectors[component_type]
            return True
        return False