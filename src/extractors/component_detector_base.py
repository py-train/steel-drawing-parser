"""Base classes for extensible component detection."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import numpy as np
import logging

from ..models.component import Component, ComponentType
from ..models.part_type_config import ComponentTypeConfig, DetectionParameters
from ..processors.image_extractor import BoundingBox


class ComponentDetector(ABC):
    """Abstract base class for component detection algorithms."""
    
    def __init__(self, config: ComponentTypeConfig):
        """
        Initialize the component detector.
        
        Args:
            config: Configuration for this component type
        """
        self.config = config
        self.params = config.detection_params
        self.logger = logging.getLogger(f'steel_parser.detector.{config.name}')
    
    @abstractmethod
    def detect(self, image: np.ndarray, **kwargs) -> List[Dict[str, Any]]:
        """
        Detect components of this type in the image.
        
        Args:
            image: Preprocessed grayscale image
            **kwargs: Additional detection parameters
            
        Returns:
            List of detection results with bounding boxes and confidence scores
        """
        pass
    
    @abstractmethod
    def validate_detection(self, detection: Dict[str, Any]) -> bool:
        """
        Validate a detection result.
        
        Args:
            detection: Detection result to validate
            
        Returns:
            True if detection is valid, False otherwise
        """
        pass
    
    def get_component_type(self) -> str:
        """Get the component type name."""
        return self.config.name
    
    def get_confidence_threshold(self) -> float:
        """Get the confidence threshold for this detector."""
        return self.params.confidence_threshold
    
    def is_enabled(self) -> bool:
        """Check if this detector is enabled."""
        return self.config.enabled


class BeamDetector(ComponentDetector):
    """Detector for I-beams and H-beams."""
    
    def detect(self, image: np.ndarray, **kwargs) -> List[Dict[str, Any]]:
        """Detect beam components using line detection and grouping."""
        try:
            detections = []
            
            # Use Hough line detection
            edges = self._detect_edges(image)
            lines = self._detect_lines(edges)
            
            if not lines:
                return detections
            
            # Group horizontal lines that might represent beams
            horizontal_lines = self._filter_horizontal_lines(lines)
            beam_groups = self._group_parallel_lines(horizontal_lines)
            
            for group in beam_groups:
                if len(group) >= self.params.custom_params.get('min_parallel_lines', 2):
                    detection = self._create_beam_detection(group, image)
                    if detection and self.validate_detection(detection):
                        detections.append(detection)
            
            self.logger.debug(f"Found {len(detections)} beam detections")
            return detections
            
        except Exception as e:
            self.logger.error(f"Beam detection failed: {e}")
            return []
    
    def validate_detection(self, detection: Dict[str, Any]) -> bool:
        """Validate beam detection."""
        bbox = detection.get('bbox')
        if not bbox:
            return False
        
        # Check minimum size
        if bbox['width'] < self.params.min_size or bbox['height'] < self.params.min_size:
            return False
        
        # Check aspect ratio
        aspect_ratio = max(bbox['width'], bbox['height']) / min(bbox['width'], bbox['height'])
        min_ratio, max_ratio = self.params.aspect_ratio_range
        if not (min_ratio <= aspect_ratio <= max_ratio):
            return False
        
        # Check confidence
        if detection.get('confidence', 0) < self.params.confidence_threshold:
            return False
        
        return True
    
    def _detect_edges(self, image: np.ndarray) -> np.ndarray:
        """Detect edges in the image."""
        import cv2
        return cv2.Canny(image, 50, 150, apertureSize=3)
    
    def _detect_lines(self, edges: np.ndarray) -> List[List[int]]:
        """Detect lines using Hough transform."""
        import cv2
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, 
                               minLineLength=50, maxLineGap=10)
        return lines.tolist() if lines is not None else []
    
    def _filter_horizontal_lines(self, lines: List[List[int]]) -> List[Dict[str, Any]]:
        """Filter for horizontal lines."""
        horizontal_lines = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
            
            if angle < self.params.angle_tolerance or angle > (180 - self.params.angle_tolerance):
                length = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                horizontal_lines.append({
                    'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                    'length': length, 'angle': angle
                })
        
        return horizontal_lines
    
    def _group_parallel_lines(self, lines: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Group parallel lines that might form beam profiles."""
        if not lines:
            return []
        
        groups = []
        used = set()
        
        for i, line1 in enumerate(lines):
            if i in used:
                continue
            
            group = [line1]
            used.add(i)
            
            for j, line2 in enumerate(lines[i+1:], i+1):
                if j in used:
                    continue
                
                # Check if lines are parallel and close
                y_dist = abs(line1['y1'] - line2['y1'])
                if y_dist <= self.params.line_grouping_distance:
                    group.append(line2)
                    used.add(j)
            
            if len(group) >= 2:
                groups.append(group)
        
        return groups
    
    def _create_beam_detection(self, group: List[Dict[str, Any]], image: np.ndarray) -> Optional[Dict[str, Any]]:
        """Create a beam detection from a group of lines."""
        if not group:
            return None
        
        # Calculate bounding box
        all_x = [line['x1'] for line in group] + [line['x2'] for line in group]
        all_y = [line['y1'] for line in group] + [line['y2'] for line in group]
        
        x_min, x_max = min(all_x), max(all_x)
        y_min, y_max = min(all_y), max(all_y)
        
        bbox = {
            'x': x_min,
            'y': y_min,
            'width': x_max - x_min,
            'height': y_max - y_min
        }
        
        # Calculate confidence based on line quality and grouping
        avg_length = sum(line['length'] for line in group) / len(group)
        line_consistency = 1.0 - (max(all_y) - min(all_y)) / max(1, avg_length)
        confidence = min(0.9, 0.5 + 0.4 * line_consistency)
        
        return {
            'bbox': bbox,
            'confidence': confidence,
            'component_type': self.config.name,
            'features': {
                'line_count': len(group),
                'avg_line_length': avg_length,
                'beam_depth': y_max - y_min,
                'beam_length': x_max - x_min
            }
        }


class ColumnDetector(ComponentDetector):
    """Detector for structural columns."""
    
    def detect(self, image: np.ndarray, **kwargs) -> List[Dict[str, Any]]:
        """Detect column components using vertical line detection."""
        try:
            detections = []
            
            # Use Hough line detection
            edges = self._detect_edges(image)
            lines = self._detect_lines(edges)
            
            if not lines:
                return detections
            
            # Group vertical lines that might represent columns
            vertical_lines = self._filter_vertical_lines(lines)
            column_groups = self._group_parallel_lines(vertical_lines)
            
            for group in column_groups:
                if len(group) >= self.params.custom_params.get('min_parallel_lines', 2):
                    detection = self._create_column_detection(group, image)
                    if detection and self.validate_detection(detection):
                        detections.append(detection)
            
            self.logger.debug(f"Found {len(detections)} column detections")
            return detections
            
        except Exception as e:
            self.logger.error(f"Column detection failed: {e}")
            return []
    
    def validate_detection(self, detection: Dict[str, Any]) -> bool:
        """Validate column detection."""
        bbox = detection.get('bbox')
        if not bbox:
            return False
        
        # Check minimum size
        if bbox['width'] < self.params.min_size or bbox['height'] < self.params.min_size:
            return False
        
        # Check aspect ratio (columns are typically taller than wide)
        aspect_ratio = bbox['height'] / max(bbox['width'], 1)
        min_ratio, max_ratio = self.params.aspect_ratio_range
        if not (min_ratio <= aspect_ratio <= max_ratio):
            return False
        
        # Check confidence
        if detection.get('confidence', 0) < self.params.confidence_threshold:
            return False
        
        return True
    
    def _detect_edges(self, image: np.ndarray) -> np.ndarray:
        """Detect edges in the image."""
        import cv2
        return cv2.Canny(image, 50, 150, apertureSize=3)
    
    def _detect_lines(self, edges: np.ndarray) -> List[List[int]]:
        """Detect lines using Hough transform."""
        import cv2
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80, 
                               minLineLength=40, maxLineGap=8)
        return lines.tolist() if lines is not None else []
    
    def _filter_vertical_lines(self, lines: List[List[int]]) -> List[Dict[str, Any]]:
        """Filter for vertical lines."""
        vertical_lines = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
            
            if 75 < angle < 105:  # Vertical lines
                length = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                vertical_lines.append({
                    'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                    'length': length, 'angle': angle
                })
        
        return vertical_lines
    
    def _group_parallel_lines(self, lines: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Group parallel lines that might form column profiles."""
        if not lines:
            return []
        
        groups = []
        used = set()
        
        for i, line1 in enumerate(lines):
            if i in used:
                continue
            
            group = [line1]
            used.add(i)
            
            for j, line2 in enumerate(lines[i+1:], i+1):
                if j in used:
                    continue
                
                # Check if lines are parallel and close
                x_dist = abs(line1['x1'] - line2['x1'])
                if x_dist <= self.params.line_grouping_distance:
                    group.append(line2)
                    used.add(j)
            
            if len(group) >= 2:
                groups.append(group)
        
        return groups
    
    def _create_column_detection(self, group: List[Dict[str, Any]], image: np.ndarray) -> Optional[Dict[str, Any]]:
        """Create a column detection from a group of lines."""
        if not group:
            return None
        
        # Calculate bounding box
        all_x = [line['x1'] for line in group] + [line['x2'] for line in group]
        all_y = [line['y1'] for line in group] + [line['y2'] for line in group]
        
        x_min, x_max = min(all_x), max(all_x)
        y_min, y_max = min(all_y), max(all_y)
        
        bbox = {
            'x': x_min,
            'y': y_min,
            'width': x_max - x_min,
            'height': y_max - y_min
        }
        
        # Calculate confidence based on line quality and grouping
        avg_length = sum(line['length'] for line in group) / len(group)
        line_consistency = 1.0 - (max(all_x) - min(all_x)) / max(1, avg_length)
        confidence = min(0.9, 0.5 + 0.4 * line_consistency)
        
        return {
            'bbox': bbox,
            'confidence': confidence,
            'component_type': self.config.name,
            'features': {
                'line_count': len(group),
                'avg_line_length': avg_length,
                'column_width': x_max - x_min,
                'column_height': y_max - y_min
            }
        }


class PlateDetector(ComponentDetector):
    """Detector for steel plates using contour detection."""
    
    def detect(self, image: np.ndarray, **kwargs) -> List[Dict[str, Any]]:
        """Detect plate components using contour analysis."""
        try:
            import cv2
            detections = []
            
            # Find contours
            edges = cv2.Canny(image, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                detection = self._create_plate_detection(contour, image)
                if detection and self.validate_detection(detection):
                    detections.append(detection)
            
            self.logger.debug(f"Found {len(detections)} plate detections")
            return detections
            
        except Exception as e:
            self.logger.error(f"Plate detection failed: {e}")
            return []
    
    def validate_detection(self, detection: Dict[str, Any]) -> bool:
        """Validate plate detection."""
        bbox = detection.get('bbox')
        if not bbox:
            return False
        
        # Check minimum size
        area = bbox['width'] * bbox['height']
        if area < self.params.min_size * self.params.min_size:
            return False
        
        # Check aspect ratio
        aspect_ratio = max(bbox['width'], bbox['height']) / min(bbox['width'], bbox['height'])
        min_ratio, max_ratio = self.params.aspect_ratio_range
        if not (min_ratio <= aspect_ratio <= max_ratio):
            return False
        
        # Check confidence
        if detection.get('confidence', 0) < self.params.confidence_threshold:
            return False
        
        return True
    
    def _create_plate_detection(self, contour: np.ndarray, image: np.ndarray) -> Optional[Dict[str, Any]]:
        """Create a plate detection from a contour."""
        import cv2
        
        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        
        if area < self.params.min_size:
            return None
        
        bbox = {'x': x, 'y': y, 'width': w, 'height': h}
        
        # Calculate confidence based on contour properties
        perimeter = cv2.arcLength(contour, True)
        if perimeter > 0:
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            rectangularity = area / (w * h)
            confidence = min(0.9, 0.3 + 0.3 * rectangularity + 0.3 * (1 - circularity))
        else:
            confidence = 0.3
        
        return {
            'bbox': bbox,
            'confidence': confidence,
            'component_type': self.config.name,
            'features': {
                'area': area,
                'perimeter': perimeter,
                'plate_length': max(w, h),
                'plate_width': min(w, h)
            }
        }