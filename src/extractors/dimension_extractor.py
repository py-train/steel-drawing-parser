"""Dimension and material specification extraction from technical drawings."""

import logging
import re
import numpy as np
import cv2
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass

from ..models.component import Component, ComponentDimensions, MaterialSpec
from ..processors.image_extractor import BoundingBox


@dataclass
class TextRegion:
    """Represents a text region found in the image."""
    bbox: BoundingBox
    text: str
    confidence: float
    font_size: Optional[float] = None


@dataclass
class DimensionAnnotation:
    """Represents a dimension annotation in the drawing."""
    value: float
    unit: str
    direction: str  # 'horizontal', 'vertical', 'diagonal'
    location: Tuple[int, int]
    confidence: float
    text_region: Optional[TextRegion] = None


class DimensionExtractor:
    """Extracts dimensions and material specifications from technical drawings."""
    
    def __init__(self):
        self.logger = logging.getLogger('steel_parser.dimension_extractor')
        
        # Common dimension patterns
        self.dimension_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:mm|MM)',  # Millimeters
            r'(\d+(?:\.\d+)?)\s*(?:in|IN|")',  # Inches
            r'(\d+(?:\.\d+)?)\s*(?:ft|FT|\')',  # Feet
            r'(\d+(?:\.\d+)?)\s*(?:m|M)(?!\w)',  # Meters (not followed by other letters)
            r'(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)',  # Dimensions like "100 x 50"
        ]
        
        # Material specification patterns
        self.material_patterns = [
            r'W(\d+)x(\d+)',  # Wide flange beams (W12x26)
            r'S(\d+)x(\d+)',  # Standard beams (S12x35)
            r'C(\d+)x(\d+)',  # Channels (C12x20.7)
            r'L(\d+)x(\d+)x(\d+)',  # Angles (L4x4x1/2)
            r'HSS(\d+)x(\d+)x(\d+)',  # Hollow structural sections
            r'A(\d+)',  # ASTM steel grades (A36, A572, etc.)
            r'Grade\s*(\d+)',  # Grade specifications
            r'Fy\s*=\s*(\d+)',  # Yield strength
        ]
    
    def extract_dimensions(self, component: Component, image: np.ndarray) -> ComponentDimensions:
        """
        Reads dimension annotations for a specific component.
        
        Args:
            component: Component to extract dimensions for
            image: Source image containing the component
            
        Returns:
            ComponentDimensions object with extracted values
        """
        try:
            # Get component region from image
            bbox = self._get_component_bbox(component)
            if not bbox:
                return component.dimensions or ComponentDimensions()
            
            # Expand search area around component
            search_bbox = self._expand_bbox(bbox, image.shape, expansion=50)
            search_region = self._extract_region(image, search_bbox)
            
            # Find text regions in the search area
            text_regions = self._find_text_regions(search_region)
            
            # Extract dimension annotations
            dimension_annotations = []
            for text_region in text_regions:
                annotations = self._parse_dimension_text(text_region)
                dimension_annotations.extend(annotations)
            
            # Match dimensions to component based on proximity and orientation
            matched_dimensions = self._match_dimensions_to_component(
                component, dimension_annotations, search_bbox
            )
            
            # Create ComponentDimensions object
            dimensions = self._create_component_dimensions(matched_dimensions, component.type)
            
            self.logger.debug(f"Extracted dimensions for {component.id}: {dimensions}")
            return dimensions
            
        except Exception as e:
            self.logger.error(f"Failed to extract dimensions for {component.id}: {str(e)}")
            return component.dimensions or ComponentDimensions()
    
    def extract_material_specs(self, component: Component, image: np.ndarray) -> MaterialSpec:
        """
        Identifies material grade markings for a component.
        
        Args:
            component: Component to extract material specs for
            image: Source image containing the component
            
        Returns:
            MaterialSpec object with extracted specifications
        """
        try:
            # Get component region
            bbox = self._get_component_bbox(component)
            if not bbox:
                return component.material or MaterialSpec()
            
            # Expand search area for material annotations
            search_bbox = self._expand_bbox(bbox, image.shape, expansion=100)
            search_region = self._extract_region(image, search_bbox)
            
            # Find text regions
            text_regions = self._find_text_regions(search_region)
            
            # Extract material specifications
            material_specs = []
            for text_region in text_regions:
                specs = self._parse_material_text(text_region)
                material_specs.extend(specs)
            
            # Create MaterialSpec object from found specifications
            material_spec = self._create_material_spec(material_specs)
            
            self.logger.debug(f"Extracted material specs for {component.id}: {material_spec}")
            return material_spec
            
        except Exception as e:
            self.logger.error(f"Failed to extract material specs for {component.id}: {str(e)}")
            return component.material or MaterialSpec()
    
    def _get_component_bbox(self, component: Component) -> Optional[BoundingBox]:
        """Extract bounding box from component metadata."""
        try:
            bbox_data = component.extraction_metadata.get('bbox')
            if bbox_data:
                return BoundingBox(
                    x=bbox_data['x'],
                    y=bbox_data['y'],
                    width=bbox_data['width'],
                    height=bbox_data['height']
                )
            return None
        except Exception:
            return None
    
    def _expand_bbox(self, bbox: BoundingBox, image_shape: Tuple[int, int], 
                    expansion: int) -> BoundingBox:
        """Expand bounding box by specified amount."""
        height, width = image_shape[:2]
        
        return BoundingBox(
            x=max(0, bbox.x - expansion),
            y=max(0, bbox.y - expansion),
            width=min(width - max(0, bbox.x - expansion), bbox.width + 2 * expansion),
            height=min(height - max(0, bbox.y - expansion), bbox.height + 2 * expansion)
        )
    
    def _extract_region(self, image: np.ndarray, bbox: BoundingBox) -> np.ndarray:
        """Extract image region defined by bounding box."""
        return image[bbox.y:bbox.y + bbox.height, bbox.x:bbox.x + bbox.width]
    
    def _find_text_regions(self, image: np.ndarray) -> List[TextRegion]:
        """
        Find text regions in the image using computer vision techniques.
        
        Args:
            image: Input image region
            
        Returns:
            List of detected text regions
        """
        try:
            text_regions = []
            
            # Convert to grayscale if needed
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()
            
            # Apply morphological operations to connect text characters
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            morph = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
            
            # Find contours that might contain text
            contours, _ = cv2.findContours(
                cv2.threshold(morph, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1],
                cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            for contour in contours:
                # Filter contours by size and aspect ratio
                x, y, w, h = cv2.boundingRect(contour)
                area = cv2.contourArea(contour)
                
                # Skip very small or very large regions
                if area < 50 or area > image.size * 0.1:
                    continue
                
                # Check aspect ratio (text usually has reasonable aspect ratios)
                aspect_ratio = w / h if h > 0 else 0
                if not (0.1 <= aspect_ratio <= 10.0):
                    continue
                
                # Extract text region
                text_bbox = BoundingBox(x=x, y=y, width=w, height=h)
                
                # Simple OCR simulation - in practice, you'd use Tesseract or similar
                text_content = self._simulate_ocr(gray[y:y+h, x:x+w])
                
                if text_content:
                    text_region = TextRegion(
                        bbox=text_bbox,
                        text=text_content,
                        confidence=0.8,  # Placeholder confidence
                        font_size=h  # Approximate font size from height
                    )
                    text_regions.append(text_region)
            
            return text_regions
            
        except Exception as e:
            self.logger.error(f"Failed to find text regions: {str(e)}")
            return []
    
    def _simulate_ocr(self, text_image: np.ndarray) -> str:
        """
        Simulate OCR for testing purposes.
        In production, this would use Tesseract or similar OCR engine.
        """
        # This is a placeholder that generates realistic text based on image characteristics
        height, width = text_image.shape[:2]
        
        # Generate plausible dimension or material text based on region characteristics
        if width > height * 2:  # Wide region, likely dimension
            return f"{np.random.randint(100, 500)}mm"
        elif height > width * 1.5:  # Tall region, might be material spec
            return f"W{np.random.randint(8, 24)}x{np.random.randint(20, 100)}"
        else:
            # Could be various text
            options = ["A36", "Grade 50", "12\"", "300mm", "W12x26"]
            return np.random.choice(options)
    
    def _parse_dimension_text(self, text_region: TextRegion) -> List[DimensionAnnotation]:
        """Parse dimension values from text region."""
        annotations = []
        text = text_region.text
        
        for pattern in self.dimension_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    if 'x' in pattern:  # Handle "width x height" format
                        groups = match.groups()
                        if len(groups) >= 2:
                            for i, group in enumerate(groups[:2]):
                                value = float(group)
                                direction = 'horizontal' if i == 0 else 'vertical'
                                
                                annotation = DimensionAnnotation(
                                    value=value,
                                    unit=self._extract_unit(text, match),
                                    direction=direction,
                                    location=text_region.bbox.center,
                                    confidence=text_region.confidence,
                                    text_region=text_region
                                )
                                annotations.append(annotation)
                    else:
                        value = float(match.group(1))
                        unit = self._extract_unit(text, match)
                        
                        # Determine direction based on text region shape
                        direction = self._infer_dimension_direction(text_region)
                        
                        annotation = DimensionAnnotation(
                            value=value,
                            unit=unit,
                            direction=direction,
                            location=text_region.bbox.center,
                            confidence=text_region.confidence,
                            text_region=text_region
                        )
                        annotations.append(annotation)
                        
                except (ValueError, IndexError) as e:
                    self.logger.debug(f"Failed to parse dimension from '{text}': {e}")
                    continue
        
        return annotations
    
    def _parse_material_text(self, text_region: TextRegion) -> List[Dict[str, Any]]:
        """Parse material specifications from text region."""
        specs = []
        text = text_region.text
        
        for pattern in self.material_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    spec = {
                        'pattern': pattern,
                        'match': match.group(0),
                        'groups': match.groups(),
                        'location': text_region.bbox.center,
                        'confidence': text_region.confidence
                    }
                    specs.append(spec)
                except Exception as e:
                    self.logger.debug(f"Failed to parse material from '{text}': {e}")
                    continue
        
        return specs
    
    def _extract_unit(self, text: str, match: re.Match) -> str:
        """Extract unit from matched text."""
        full_match = match.group(0)
        
        if 'mm' in full_match.lower():
            return 'mm'
        elif 'in' in full_match.lower() or '"' in full_match:
            return 'in'
        elif 'ft' in full_match.lower() or "'" in full_match:
            return 'ft'
        elif 'm' in full_match.lower():
            return 'm'
        else:
            return 'mm'  # Default unit
    
    def _infer_dimension_direction(self, text_region: TextRegion) -> str:
        """Infer dimension direction from text region characteristics."""
        bbox = text_region.bbox
        aspect_ratio = bbox.width / bbox.height if bbox.height > 0 else 1
        
        if aspect_ratio > 2:
            return 'horizontal'
        elif aspect_ratio < 0.5:
            return 'vertical'
        else:
            return 'diagonal'
    
    def _match_dimensions_to_component(self, component: Component, 
                                     annotations: List[DimensionAnnotation],
                                     search_bbox: BoundingBox) -> List[DimensionAnnotation]:
        """Match dimension annotations to component based on proximity and type."""
        matched = []
        
        component_center = (
            component.location.x if component.location else search_bbox.center[0],
            component.location.y if component.location else search_bbox.center[1]
        )
        
        for annotation in annotations:
            # Calculate distance from component center
            distance = np.sqrt(
                (annotation.location[0] - component_center[0])**2 +
                (annotation.location[1] - component_center[1])**2
            )
            
            # Accept dimensions within reasonable distance
            max_distance = max(search_bbox.width, search_bbox.height) * 0.5
            if distance <= max_distance:
                matched.append(annotation)
        
        return matched
    
    def _create_component_dimensions(self, annotations: List[DimensionAnnotation],
                                   component_type) -> ComponentDimensions:
        """Create ComponentDimensions from matched annotations."""
        dimensions = ComponentDimensions()
        
        if not annotations:
            return dimensions
        
        # Group annotations by direction
        horizontal_dims = [a for a in annotations if a.direction == 'horizontal']
        vertical_dims = [a for a in annotations if a.direction == 'vertical']
        
        # Assign dimensions based on component type and available annotations
        if horizontal_dims:
            # Use the most confident horizontal dimension
            best_horizontal = max(horizontal_dims, key=lambda x: x.confidence)
            dimensions.width = best_horizontal.value
            dimensions.unit = best_horizontal.unit
        
        if vertical_dims:
            # Use the most confident vertical dimension
            best_vertical = max(vertical_dims, key=lambda x: x.confidence)
            dimensions.height = best_vertical.value
            if not dimensions.unit:
                dimensions.unit = best_vertical.unit
        
        # For beams, width is typically the span, height is the depth
        # For columns, both width and height are cross-sectional dimensions
        # Additional logic could be added here for component-specific dimension assignment
        
        return dimensions
    
    def _create_material_spec(self, specs: List[Dict[str, Any]]) -> MaterialSpec:
        """Create MaterialSpec from parsed specifications."""
        material_spec = MaterialSpec()
        
        for spec in specs:
            pattern = spec['pattern']
            match_text = spec['match']
            groups = spec['groups']
            
            try:
                if 'W(' in pattern:  # Wide flange beam
                    material_spec.grade = match_text
                    material_spec.specification = "AISC"
                elif 'A(' in pattern:  # ASTM grade
                    material_spec.grade = match_text
                    material_spec.specification = "ASTM"
                elif 'Grade' in pattern:
                    grade_num = int(groups[0])
                    material_spec.grade = f"Grade {grade_num}"
                    if grade_num == 36:
                        material_spec.yield_strength = 36000  # psi
                    elif grade_num == 50:
                        material_spec.yield_strength = 50000  # psi
                elif 'Fy' in pattern:
                    material_spec.yield_strength = float(groups[0])
                    
            except (ValueError, IndexError) as e:
                self.logger.debug(f"Failed to process material spec {spec}: {e}")
                continue
        
        return material_spec