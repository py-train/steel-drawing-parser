"""Steel component extraction from processed images."""

import logging
import numpy as np
import cv2
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
import uuid

from ..models.component import Component, ComponentType, ComponentDimensions, MaterialSpec, Coordinates
from ..processors.image_extractor import BoundingBox
from .dimension_extractor import DimensionExtractor


@dataclass
class DetectionCandidate:
    """Represents a potential steel component detected in an image."""
    bbox: BoundingBox
    component_type: ComponentType
    confidence: float
    features: Dict[str, Any]
    contour: Optional[np.ndarray] = None


class PartExtractor:
    """Identifies and extracts steel components from processed images."""
    
    def __init__(self, min_component_size: int = 50, confidence_threshold: float = 0.7):
        """
        Initialize the part extractor.
        
        Args:
            min_component_size: Minimum size in pixels for a component
            confidence_threshold: Minimum confidence for component detection
        """
        self.min_component_size = min_component_size
        self.confidence_threshold = confidence_threshold
        self.logger = logging.getLogger('steel_parser.part_extractor')
        self.dimension_extractor = DimensionExtractor()
    
    def detect_steel_components(self, image: np.ndarray, 
                              page_number: int = 1) -> List[Component]:
        """
        Main detection pipeline for steel components.
        
        Args:
            image: Preprocessed grayscale image
            page_number: Page number for coordinate reference
            
        Returns:
            List of detected Component objects
        """
        try:
            self.logger.info(f"Starting component detection on page {page_number}")
            
            # Detect different types of components
            beam_candidates = self.extract_beams(image)
            column_candidates = self.extract_columns(image)
            plate_candidates = self.extract_plates(image)
            connection_candidates = self.extract_connections(image)
            
            # Combine all candidates
            all_candidates = (beam_candidates + column_candidates + 
                            plate_candidates + connection_candidates)
            
            # Filter by confidence threshold
            filtered_candidates = [
                c for c in all_candidates 
                if c.confidence >= self.confidence_threshold
            ]
            
            # Remove overlapping detections (non-maximum suppression)
            final_candidates = self._apply_non_maximum_suppression(filtered_candidates)
            
            # Convert candidates to Component objects
            components = []
            for candidate in final_candidates:
                component = self._candidate_to_component(candidate, page_number)
                if component:
                    # Extract dimensions and materials for the component
                    component = self._enhance_component_with_details(component, image)
                    components.append(component)
            
            # Count quantities and update locations for similar components
            components = self._count_quantities_and_update_locations(components)
            
            self.logger.info(f"Detected {len(components)} components on page {page_number}")
            return components
            
        except Exception as e:
            error_msg = f"Failed to detect steel components: {str(e)}"
            self.logger.error(error_msg)
            return []
    
    def extract_beams(self, image: np.ndarray) -> List[DetectionCandidate]:
        """
        Identifies I-beams and H-beams in the image.
        
        Args:
            image: Preprocessed grayscale image
            
        Returns:
            List of beam detection candidates
        """
        try:
            candidates = []
            
            # Apply edge detection to find structural lines
            edges = cv2.Canny(image, 50, 150)
            
            # Use HoughLinesP to detect line segments
            lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50, 
                                   minLineLength=self.min_component_size, 
                                   maxLineGap=10)
            
            if lines is None:
                return candidates
            
            # Group horizontal lines that might represent beams
            horizontal_lines = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
                
                # Consider lines within 15 degrees of horizontal as potential beams
                if angle < 15 or angle > 165:
                    length = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                    horizontal_lines.append({
                        'line': line[0],
                        'length': length,
                        'midpoint': ((x1 + x2) // 2, (y1 + y2) // 2)
                    })
            
            # Group nearby horizontal lines into beam candidates
            beam_groups = self._group_parallel_lines(horizontal_lines, max_distance=20)
            
            for group in beam_groups:
                if len(group) >= 2:  # Need at least 2 lines for a beam profile
                    # Calculate bounding box for the beam group
                    all_points = []
                    for line_info in group:
                        x1, y1, x2, y2 = line_info['line']
                        all_points.extend([(x1, y1), (x2, y2)])
                    
                    if all_points:
                        xs, ys = zip(*all_points)
                        x_min, x_max = min(xs), max(xs)
                        y_min, y_max = min(ys), max(ys)
                        
                        # Create bounding box with some padding
                        padding = 5
                        bbox = BoundingBox(
                            x=max(0, x_min - padding),
                            y=max(0, y_min - padding),
                            width=min(image.shape[1], x_max - x_min + 2*padding),
                            height=min(image.shape[0], y_max - y_min + 2*padding)
                        )
                        
                        # Calculate confidence based on line characteristics
                        avg_length = np.mean([line_info['length'] for line_info in group])
                        line_count = len(group)
                        confidence = min(1.0, (avg_length / 100) * (line_count / 3) * 0.8)
                        
                        features = {
                            'line_count': line_count,
                            'avg_length': avg_length,
                            'orientation': 'horizontal'
                        }
                        
                        candidate = DetectionCandidate(
                            bbox=bbox,
                            component_type=ComponentType.BEAM,
                            confidence=confidence,
                            features=features
                        )
                        candidates.append(candidate)
            
            self.logger.debug(f"Found {len(candidates)} beam candidates")
            return candidates
            
        except Exception as e:
            self.logger.error(f"Failed to extract beams: {str(e)}")
            return []
    
    def extract_columns(self, image: np.ndarray) -> List[DetectionCandidate]:
        """
        Identifies structural columns in the image.
        
        Args:
            image: Preprocessed grayscale image
            
        Returns:
            List of column detection candidates
        """
        try:
            candidates = []
            
            # Apply edge detection
            edges = cv2.Canny(image, 50, 150)
            
            # Detect line segments
            lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50,
                                   minLineLength=self.min_component_size,
                                   maxLineGap=10)
            
            if lines is None:
                return candidates
            
            # Group vertical lines that might represent columns
            vertical_lines = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
                
                # Consider lines within 15 degrees of vertical as potential columns
                if 75 < angle < 105:
                    length = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                    vertical_lines.append({
                        'line': line[0],
                        'length': length,
                        'midpoint': ((x1 + x2) // 2, (y1 + y2) // 2)
                    })
            
            # Group nearby vertical lines into column candidates
            column_groups = self._group_parallel_lines(vertical_lines, max_distance=15)
            
            for group in column_groups:
                if len(group) >= 2:  # Need at least 2 lines for a column profile
                    # Calculate bounding box
                    all_points = []
                    for line_info in group:
                        x1, y1, x2, y2 = line_info['line']
                        all_points.extend([(x1, y1), (x2, y2)])
                    
                    if all_points:
                        xs, ys = zip(*all_points)
                        x_min, x_max = min(xs), max(xs)
                        y_min, y_max = min(ys), max(ys)
                        
                        padding = 5
                        bbox = BoundingBox(
                            x=max(0, x_min - padding),
                            y=max(0, y_min - padding),
                            width=min(image.shape[1], x_max - x_min + 2*padding),
                            height=min(image.shape[0], y_max - y_min + 2*padding)
                        )
                        
                        # Calculate confidence
                        avg_length = np.mean([line_info['length'] for line_info in group])
                        line_count = len(group)
                        confidence = min(1.0, (avg_length / 100) * (line_count / 3) * 0.8)
                        
                        features = {
                            'line_count': line_count,
                            'avg_length': avg_length,
                            'orientation': 'vertical'
                        }
                        
                        candidate = DetectionCandidate(
                            bbox=bbox,
                            component_type=ComponentType.COLUMN,
                            confidence=confidence,
                            features=features
                        )
                        candidates.append(candidate)
            
            self.logger.debug(f"Found {len(candidates)} column candidates")
            return candidates
            
        except Exception as e:
            self.logger.error(f"Failed to extract columns: {str(e)}")
            return []
    
    def extract_plates(self, image: np.ndarray) -> List[DetectionCandidate]:
        """
        Identifies steel plates in the image.
        
        Args:
            image: Preprocessed grayscale image
            
        Returns:
            List of plate detection candidates
        """
        try:
            candidates = []
            
            # Apply threshold to create binary image
            _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # Find contours for rectangular shapes
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < self.min_component_size * self.min_component_size:
                    continue
                
                # Approximate contour to polygon
                epsilon = 0.02 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                
                # Look for rectangular shapes (4 corners)
                if len(approx) == 4:
                    # Calculate bounding rectangle
                    x, y, w, h = cv2.boundingRect(contour)
                    
                    # Skip if bounding box is too close to image edges (likely image border)
                    margin = 10
                    if (x < margin or y < margin or 
                        x + w > image.shape[1] - margin or 
                        y + h > image.shape[0] - margin):
                        continue
                    
                    # Check aspect ratio to distinguish plates from beams/columns
                    aspect_ratio = max(w, h) / min(w, h)
                    
                    # Plates typically have moderate aspect ratios (not too long/thin)
                    if 1.2 <= aspect_ratio <= 5.0:
                        bbox = BoundingBox(x=x, y=y, width=w, height=h)
                        
                        # Calculate confidence based on shape regularity
                        rect_area = w * h
                        fill_ratio = area / rect_area if rect_area > 0 else 0
                        confidence = min(1.0, fill_ratio * 0.9)
                        
                        features = {
                            'area': area,
                            'aspect_ratio': aspect_ratio,
                            'fill_ratio': fill_ratio,
                            'corners': len(approx)
                        }
                        
                        candidate = DetectionCandidate(
                            bbox=bbox,
                            component_type=ComponentType.PLATE,
                            confidence=confidence,
                            features=features,
                            contour=contour
                        )
                        candidates.append(candidate)
            
            self.logger.debug(f"Found {len(candidates)} plate candidates")
            return candidates
            
        except Exception as e:
            self.logger.error(f"Failed to extract plates: {str(e)}")
            return []
    
    def extract_connections(self, image: np.ndarray) -> List[DetectionCandidate]:
        """
        Identifies bolts and welds in the image.
        
        Args:
            image: Preprocessed grayscale image
            
        Returns:
            List of connection detection candidates
        """
        try:
            candidates = []
            
            # Detect circular shapes (bolts)
            # Try multiple parameter sets for better detection
            param_sets = [
                {'param1': 100, 'param2': 20, 'minRadius': 4, 'maxRadius': 25},
                {'param1': 50, 'param2': 15, 'minRadius': 6, 'maxRadius': 30},
                {'param1': 80, 'param2': 25, 'minRadius': 8, 'maxRadius': 20}
            ]
            
            all_circles = []
            for params in param_sets:
                circles = cv2.HoughCircles(
                    image, cv2.HOUGH_GRADIENT, dp=1, minDist=15,
                    **params
                )
                if circles is not None:
                    all_circles.extend(circles[0, :])
            
            if all_circles:
                # Remove duplicate circles
                unique_circles = []
                for circle in all_circles:
                    x, y, r = np.round(circle).astype("int")
                    
                    # Check if this circle is too close to existing ones
                    is_duplicate = False
                    for existing in unique_circles:
                        ex, ey, er = existing
                        dist = np.sqrt((x - ex)**2 + (y - ey)**2)
                        if dist < max(r, er):
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        unique_circles.append((x, y, r))
                
                for (x, y, r) in unique_circles:
                    # Ensure circle is within image bounds
                    if (r < x < image.shape[1] - r and 
                        r < y < image.shape[0] - r):
                        
                        # Check minimum size requirement
                        diameter = 2 * r
                        if diameter < self.min_component_size:
                            continue
                        
                        # Create bounding box around the circle
                        bbox = BoundingBox(
                            x=max(0, x - r),
                            y=max(0, y - r),
                            width=2 * r,
                            height=2 * r
                        )
                        
                        # Confidence based on circle detection parameters
                        confidence = 0.8  # Hough circles are generally reliable
                        
                        features = {
                            'radius': r,
                            'center': (x, y),
                            'connection_type': 'bolt'
                        }
                        
                        candidate = DetectionCandidate(
                            bbox=bbox,
                            component_type=ComponentType.BOLT,
                            confidence=confidence,
                            features=features
                        )
                        candidates.append(candidate)
            
            # TODO: Add weld detection (look for specific weld symbols)
            # This would require more sophisticated pattern matching
            
            self.logger.debug(f"Found {len(candidates)} connection candidates")
            return candidates
            
        except Exception as e:
            self.logger.error(f"Failed to extract connections: {str(e)}")
            return []
    
    def _group_parallel_lines(self, lines: List[Dict], max_distance: int = 20) -> List[List[Dict]]:
        """
        Group parallel lines that are close to each other.
        
        Args:
            lines: List of line information dictionaries
            max_distance: Maximum distance between lines to group them
            
        Returns:
            List of line groups
        """
        if not lines:
            return []
        
        groups = []
        used = set()
        
        for i, line1 in enumerate(lines):
            if i in used:
                continue
                
            group = [line1]
            used.add(i)
            
            for j, line2 in enumerate(lines):
                if j in used or i == j:
                    continue
                
                # Calculate distance between line midpoints
                dist = np.sqrt(
                    (line1['midpoint'][0] - line2['midpoint'][0])**2 +
                    (line1['midpoint'][1] - line2['midpoint'][1])**2
                )
                
                if dist <= max_distance:
                    group.append(line2)
                    used.add(j)
            
            if len(group) >= 1:
                groups.append(group)
        
        return groups
    
    def _apply_non_maximum_suppression(self, candidates: List[DetectionCandidate], 
                                     overlap_threshold: float = 0.5) -> List[DetectionCandidate]:
        """
        Remove overlapping detections using non-maximum suppression.
        
        Args:
            candidates: List of detection candidates
            overlap_threshold: Minimum overlap ratio to suppress
            
        Returns:
            Filtered list of candidates
        """
        if not candidates:
            return []
        
        # Sort by confidence (highest first)
        sorted_candidates = sorted(candidates, key=lambda x: x.confidence, reverse=True)
        
        keep = []
        suppress = set()
        
        for i, candidate1 in enumerate(sorted_candidates):
            if i in suppress:
                continue
                
            keep.append(candidate1)
            
            # Check overlap with remaining candidates
            for j, candidate2 in enumerate(sorted_candidates[i+1:], i+1):
                if j in suppress:
                    continue
                
                overlap = self._calculate_bbox_overlap(candidate1.bbox, candidate2.bbox)
                if overlap > overlap_threshold:
                    suppress.add(j)
        
        return keep
    
    def _calculate_bbox_overlap(self, bbox1: BoundingBox, bbox2: BoundingBox) -> float:
        """
        Calculate overlap ratio between two bounding boxes.
        
        Args:
            bbox1: First bounding box
            bbox2: Second bounding box
            
        Returns:
            Overlap ratio (0.0 to 1.0)
        """
        # Calculate intersection
        x1 = max(bbox1.x, bbox2.x)
        y1 = max(bbox1.y, bbox2.y)
        x2 = min(bbox1.x + bbox1.width, bbox2.x + bbox2.width)
        y2 = min(bbox1.y + bbox1.height, bbox2.y + bbox2.height)
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        intersection = (x2 - x1) * (y2 - y1)
        
        # Calculate union
        area1 = bbox1.width * bbox1.height
        area2 = bbox2.width * bbox2.height
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    def _candidate_to_component(self, candidate: DetectionCandidate, 
                              page_number: int) -> Optional[Component]:
        """
        Convert a detection candidate to a Component object.
        
        Args:
            candidate: Detection candidate
            page_number: Page number for coordinates
            
        Returns:
            Component object or None if conversion fails
        """
        try:
            # Generate unique ID
            component_id = f"{candidate.component_type.value}_{uuid.uuid4().hex[:8]}"
            
            # Create coordinates
            coordinates = Coordinates(
                x=float(candidate.bbox.center[0]),
                y=float(candidate.bbox.center[1]),
                page_number=page_number
            )
            
            # Create basic dimensions from bounding box
            dimensions = ComponentDimensions(
                width=float(candidate.bbox.width),
                height=float(candidate.bbox.height),
                unit="pixels"  # Will be converted to real units later
            )
            
            component = Component(
                id=component_id,
                type=candidate.component_type,
                dimensions=dimensions,
                location=coordinates,
                confidence=candidate.confidence,
                extraction_metadata={
                    'detection_features': candidate.features,
                    'bbox': {
                        'x': candidate.bbox.x,
                        'y': candidate.bbox.y,
                        'width': candidate.bbox.width,
                        'height': candidate.bbox.height
                    }
                }
            )
            
            return component
            
        except Exception as e:
            self.logger.error(f"Failed to convert candidate to component: {str(e)}")
            return None
    
    def _enhance_component_with_details(self, component: Component, image: np.ndarray) -> Component:
        """
        Enhance component with extracted dimensions and material specifications.
        
        Args:
            component: Base component to enhance
            image: Source image for extraction
            
        Returns:
            Enhanced component with dimensions and materials
        """
        try:
            # Extract dimensions
            enhanced_dimensions = self.dimension_extractor.extract_dimensions(component, image)
            if enhanced_dimensions and (enhanced_dimensions.width or enhanced_dimensions.height):
                component.dimensions = enhanced_dimensions
            
            # Extract material specifications
            material_spec = self.dimension_extractor.extract_material_specs(component, image)
            if material_spec and (material_spec.grade or material_spec.specification):
                component.material = material_spec
            
            # Update extraction metadata
            component.extraction_metadata['dimension_extraction'] = True
            component.extraction_metadata['material_extraction'] = True
            
            return component
            
        except Exception as e:
            self.logger.error(f"Failed to enhance component {component.id}: {str(e)}")
            return component
    
    def _count_quantities_and_update_locations(self, components: List[Component]) -> List[Component]:
        """
        Count quantities of similar components and update their locations.
        
        Args:
            components: List of detected components
            
        Returns:
            List of components with updated quantities and representative locations
        """
        try:
            if not components:
                return components
            
            # Group similar components
            component_groups = self._group_similar_components(components)
            
            # Create final component list with quantities
            final_components = []
            
            for group in component_groups:
                if len(group) == 1:
                    # Single component, no quantity update needed
                    final_components.append(group[0])
                else:
                    # Multiple similar components, create representative component
                    representative = self._create_representative_component(group)
                    final_components.append(representative)
            
            return final_components
            
        except Exception as e:
            self.logger.error(f"Failed to count quantities: {str(e)}")
            return components
    
    def _group_similar_components(self, components: List[Component]) -> List[List[Component]]:
        """
        Group components that are similar in type, size, and material.
        
        Args:
            components: List of components to group
            
        Returns:
            List of component groups
        """
        groups = []
        used_indices = set()
        
        for i, component1 in enumerate(components):
            if i in used_indices:
                continue
            
            # Start a new group with this component
            group = [component1]
            used_indices.add(i)
            
            # Find similar components
            for j, component2 in enumerate(components):
                if j in used_indices or i == j:
                    continue
                
                if self._are_components_similar(component1, component2):
                    group.append(component2)
                    used_indices.add(j)
            
            groups.append(group)
        
        return groups
    
    def _are_components_similar(self, comp1: Component, comp2: Component) -> bool:
        """
        Determine if two components are similar enough to be counted as the same type.
        
        Args:
            comp1: First component
            comp2: Second component
            
        Returns:
            True if components are similar
        """
        # Must be same component type
        if comp1.type != comp2.type:
            return False
        
        # Compare dimensions if available
        if comp1.dimensions and comp2.dimensions:
            if not self._are_dimensions_similar(comp1.dimensions, comp2.dimensions):
                return False
        
        # Compare materials if available
        if comp1.material and comp2.material:
            if not self._are_materials_similar(comp1.material, comp2.material):
                return False
        
        # Compare sizes from bounding boxes
        bbox1_data = comp1.extraction_metadata.get('bbox', {})
        bbox2_data = comp2.extraction_metadata.get('bbox', {})
        
        if bbox1_data and bbox2_data:
            if not self._are_sizes_similar(bbox1_data, bbox2_data):
                return False
        
        return True
    
    def _are_dimensions_similar(self, dim1: ComponentDimensions, dim2: ComponentDimensions, 
                              tolerance: float = 0.1) -> bool:
        """Check if two dimension sets are similar within tolerance."""
        # Compare width
        if dim1.width is not None and dim2.width is not None:
            if abs(dim1.width - dim2.width) / max(dim1.width, dim2.width) > tolerance:
                return False
        
        # Compare height
        if dim1.height is not None and dim2.height is not None:
            if abs(dim1.height - dim2.height) / max(dim1.height, dim2.height) > tolerance:
                return False
        
        # Compare thickness if available
        if dim1.thickness is not None and dim2.thickness is not None:
            if abs(dim1.thickness - dim2.thickness) / max(dim1.thickness, dim2.thickness) > tolerance:
                return False
        
        return True
    
    def _are_materials_similar(self, mat1: MaterialSpec, mat2: MaterialSpec) -> bool:
        """Check if two material specifications are similar."""
        # Compare grade
        if mat1.grade and mat2.grade:
            if mat1.grade != mat2.grade:
                return False
        
        # Compare specification
        if mat1.specification and mat2.specification:
            if mat1.specification != mat2.specification:
                return False
        
        return True
    
    def _are_sizes_similar(self, bbox1: Dict, bbox2: Dict, tolerance: float = 0.2) -> bool:
        """Check if two bounding box sizes are similar."""
        width1, height1 = bbox1.get('width', 0), bbox1.get('height', 0)
        width2, height2 = bbox2.get('width', 0), bbox2.get('height', 0)
        
        if width1 == 0 or height1 == 0 or width2 == 0 or height2 == 0:
            return True  # Can't compare, assume similar
        
        # Compare areas
        area1 = width1 * height1
        area2 = width2 * height2
        
        if abs(area1 - area2) / max(area1, area2) > tolerance:
            return False
        
        # Compare aspect ratios
        aspect1 = width1 / height1
        aspect2 = width2 / height2
        
        if abs(aspect1 - aspect2) / max(aspect1, aspect2) > tolerance:
            return False
        
        return True
    
    def _create_representative_component(self, group: List[Component]) -> Component:
        """
        Create a representative component from a group of similar components.
        
        Args:
            group: List of similar components
            
        Returns:
            Representative component with updated quantity and location
        """
        # Use the component with highest confidence as base
        representative = max(group, key=lambda c: c.confidence)
        
        # Update quantity
        representative.quantity = len(group)
        
        # Calculate centroid location
        if all(c.location for c in group):
            avg_x = sum(c.location.x for c in group) / len(group)
            avg_y = sum(c.location.y for c in group) / len(group)
            
            representative.location.x = avg_x
            representative.location.y = avg_y
        
        # Update extraction metadata with group information
        representative.extraction_metadata['quantity_group'] = {
            'total_count': len(group),
            'individual_locations': [
                {'x': c.location.x, 'y': c.location.y} if c.location else None
                for c in group
            ],
            'confidence_range': {
                'min': min(c.confidence for c in group),
                'max': max(c.confidence for c in group),
                'avg': sum(c.confidence for c in group) / len(group)
            }
        }
        
        # Update confidence to average of group
        representative.confidence = sum(c.confidence for c in group) / len(group)
        
        self.logger.debug(f"Created representative component {representative.id} "
                         f"from {len(group)} similar components")
        
        return representative
    
    def get_component_locations(self, components: List[Component]) -> Dict[str, List[Tuple[float, float]]]:
        """
        Get all locations for components, including individual locations for grouped components.
        
        Args:
            components: List of components
            
        Returns:
            Dictionary mapping component IDs to lists of (x, y) coordinates
        """
        locations = {}
        
        for component in components:
            component_locations = []
            
            # Add main location
            if component.location:
                component_locations.append((component.location.x, component.location.y))
            
            # Add individual locations from quantity group if available
            group_data = component.extraction_metadata.get('quantity_group', {})
            individual_locations = group_data.get('individual_locations', [])
            
            for loc in individual_locations:
                if loc and 'x' in loc and 'y' in loc:
                    component_locations.append((loc['x'], loc['y']))
            
            locations[component.id] = component_locations
        
        return locations
    
    def get_quantity_statistics(self, components: List[Component]) -> Dict[str, Any]:
        """
        Get statistics about component quantities.
        
        Args:
            components: List of components
            
        Returns:
            Dictionary with quantity statistics
        """
        stats = {
            'total_unique_components': len(components),
            'total_individual_parts': sum(c.quantity for c in components),
            'by_type': {},
            'grouped_components': 0,
            'single_components': 0
        }
        
        for component in components:
            # Count by type
            type_name = component.type.value
            if type_name not in stats['by_type']:
                stats['by_type'][type_name] = {'unique': 0, 'total': 0}
            
            stats['by_type'][type_name]['unique'] += 1
            stats['by_type'][type_name]['total'] += component.quantity
            
            # Count grouped vs single
            if component.quantity > 1:
                stats['grouped_components'] += 1
            else:
                stats['single_components'] += 1
        
        return stats