"""Image processing component for steel drawing parser."""

import io
import logging
import numpy as np
import cv2
from PIL import Image
from typing import List, Tuple, Optional
from dataclasses import dataclass

from .pdf_processor import PDFPage
from ..utils.performance_monitor import get_performance_monitor, monitor_performance


@dataclass
class BoundingBox:
    """Represents a rectangular region in an image."""
    x: int
    y: int
    width: int
    height: int
    confidence: float = 1.0
    
    @property
    def area(self) -> int:
        """Calculate the area of the bounding box."""
        return self.width * self.height
    
    @property
    def center(self) -> Tuple[int, int]:
        """Get the center point of the bounding box."""
        return (self.x + self.width // 2, self.y + self.height // 2)


class ImageExtractor:
    """Converts PDF pages to processable images and performs preprocessing."""
    
    def __init__(self, dpi: int = 300, config=None):
        """
        Initialize the image extractor.
        
        Args:
            dpi: Resolution for PDF to image conversion
            config: ExtractionConfig instance for additional parameters
        """
        self.dpi = dpi
        if config and hasattr(config, 'dpi'):
            self.dpi = config.dpi
        
        self.logger = logging.getLogger('steel_parser.image_extractor')
        self.performance_monitor = get_performance_monitor()
    
    @monitor_performance("pdf_to_image_conversion")
    def pdf_page_to_image(self, page: PDFPage, dpi: Optional[int] = None) -> np.ndarray:
        """
        Converts PDF page to high-resolution image.
        
        Args:
            page: PDFPage object to convert
            dpi: Override DPI for this conversion (optional)
            
        Returns:
            numpy array representing the image in BGR format
            
        Raises:
            ValueError: If conversion fails
        """
        try:
            conversion_dpi = dpi or self.dpi
            
            # Create transformation matrix for the desired DPI
            # PyMuPDF uses 72 DPI as base, so we scale accordingly
            scale = conversion_dpi / 72.0
            mat = page.page_obj.transformation_matrix * scale
            
            # Convert to pixmap
            pixmap = page.page_obj.get_pixmap(matrix=mat)
            
            # Convert to PIL Image
            img_data = pixmap.tobytes("ppm")
            pil_image = Image.open(io.BytesIO(img_data))
            
            # Convert PIL to numpy array (RGB)
            img_array = np.array(pil_image)
            
            # Convert RGB to BGR for OpenCV compatibility
            if len(img_array.shape) == 3 and img_array.shape[2] == 3:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            self.logger.info(f"Converted page {page.page_number} to image: "
                           f"{img_array.shape} at {conversion_dpi} DPI")
            
            return img_array
            
        except Exception as e:
            error_msg = f"Failed to convert page {page.page_number} to image: {str(e)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
    
    @monitor_performance("image_preprocessing")
    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Applies noise reduction and contrast enhancement.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Preprocessed image as numpy array
        """
        try:
            # Convert to grayscale if needed
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()
            
            # Apply Gaussian blur to reduce noise
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
            # This enhances contrast while preventing over-amplification
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(blurred)
            
            # Apply bilateral filter to reduce noise while preserving edges
            # This is important for technical drawings with sharp lines
            filtered = cv2.bilateralFilter(enhanced, 9, 75, 75)
            
            # Apply morphological operations to clean up the image
            kernel = np.ones((2, 2), np.uint8)
            cleaned = cv2.morphologyEx(filtered, cv2.MORPH_CLOSE, kernel)
            
            self.logger.debug(f"Preprocessed image: {image.shape} -> {cleaned.shape}")
            
            return cleaned
            
        except Exception as e:
            error_msg = f"Failed to preprocess image: {str(e)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
    
    @monitor_performance("drawing_region_detection")
    def detect_drawing_regions(self, image: np.ndarray, 
                             min_area: int = 10000) -> List[BoundingBox]:
        """
        Identifies distinct drawing areas within page.
        
        Args:
            image: Input image as numpy array
            min_area: Minimum area for a region to be considered a drawing
            
        Returns:
            List of BoundingBox objects representing drawing regions
        """
        try:
            # Convert to grayscale if needed
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()
            
            # Apply threshold to create binary image
            # Use adaptive threshold to handle varying lighting conditions
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY_INV, 11, 2
            )
            
            # Apply morphological operations to connect nearby elements
            kernel = np.ones((5, 5), np.uint8)
            dilated = cv2.dilate(binary, kernel, iterations=2)
            eroded = cv2.erode(dilated, kernel, iterations=1)
            
            # Find contours
            contours, _ = cv2.findContours(
                eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            # Filter contours by area and convert to bounding boxes
            regions = []
            for contour in contours:
                area = cv2.contourArea(contour)
                if area >= min_area:
                    x, y, w, h = cv2.boundingRect(contour)
                    
                    # Calculate confidence based on area and aspect ratio
                    aspect_ratio = w / h if h > 0 else 0
                    confidence = min(1.0, area / (image.shape[0] * image.shape[1]))
                    
                    # Prefer regions with reasonable aspect ratios for technical drawings
                    if 0.1 <= aspect_ratio <= 10.0:
                        bbox = BoundingBox(x, y, w, h, confidence)
                        regions.append(bbox)
            
            # Sort regions by area (largest first)
            regions.sort(key=lambda r: r.area, reverse=True)
            
            self.logger.info(f"Detected {len(regions)} drawing regions")
            
            # If no regions found, return the entire image as one region
            if not regions:
                full_region = BoundingBox(
                    0, 0, image.shape[1], image.shape[0], 1.0
                )
                regions = [full_region]
                self.logger.info("No specific regions found, using entire image")
            
            return regions
            
        except Exception as e:
            error_msg = f"Failed to detect drawing regions: {str(e)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
    
    def extract_region(self, image: np.ndarray, bbox: BoundingBox) -> np.ndarray:
        """
        Extract a specific region from an image.
        
        Args:
            image: Source image
            bbox: Bounding box defining the region to extract
            
        Returns:
            Extracted image region
        """
        try:
            # Ensure coordinates are within image bounds
            height, width = image.shape[:2]
            x1 = max(0, bbox.x)
            y1 = max(0, bbox.y)
            x2 = min(width, bbox.x + bbox.width)
            y2 = min(height, bbox.y + bbox.height)
            
            # Extract the region
            region = image[y1:y2, x1:x2]
            
            if region.size == 0:
                raise ValueError("Extracted region is empty")
            
            return region
            
        except Exception as e:
            error_msg = f"Failed to extract region {bbox}: {str(e)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
    
    def get_image_stats(self, image: np.ndarray) -> dict:
        """
        Get statistical information about an image.
        
        Args:
            image: Input image
            
        Returns:
            Dictionary with image statistics
        """
        try:
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()
            
            stats = {
                'shape': image.shape,
                'dtype': str(image.dtype),
                'mean_intensity': float(np.mean(gray)),
                'std_intensity': float(np.std(gray)),
                'min_intensity': int(np.min(gray)),
                'max_intensity': int(np.max(gray)),
                'total_pixels': int(image.size),
                'non_zero_pixels': int(np.count_nonzero(gray))
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Failed to get image stats: {str(e)}")
            return {}
    
    def validate_image_quality(self, image: np.ndarray) -> Tuple[bool, dict]:
        """
        Validate image quality for processing.
        
        Args:
            image: Input image to validate
            
        Returns:
            Tuple of (is_valid, quality_metrics)
        """
        try:
            quality_metrics = {}
            is_valid = True
            issues = []
            
            # Basic dimension checks
            if len(image.shape) < 2:
                issues.append("Image has insufficient dimensions")
                is_valid = False
                return is_valid, {'issues': issues}
            
            height, width = image.shape[:2]
            quality_metrics['dimensions'] = (height, width)
            
            # Check minimum size requirements
            min_size = 100  # Minimum 100x100 pixels
            if height < min_size or width < min_size:
                issues.append(f"Image too small: {width}x{height} (minimum {min_size}x{min_size})")
                is_valid = False
            
            # Convert to grayscale for analysis
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()
            
            # Check for blank/empty images
            mean_intensity = np.mean(gray)
            std_intensity = np.std(gray)
            quality_metrics['mean_intensity'] = float(mean_intensity)
            quality_metrics['std_intensity'] = float(std_intensity)
            
            # Very low standard deviation indicates blank image
            if std_intensity < 5.0:
                issues.append(f"Image appears blank (std: {std_intensity:.2f})")
                is_valid = False
            
            # Check contrast
            contrast_ratio = (np.max(gray) - np.min(gray)) / 255.0
            quality_metrics['contrast_ratio'] = float(contrast_ratio)
            
            if contrast_ratio < 0.1:
                issues.append(f"Very low contrast: {contrast_ratio:.3f}")
                # Don't mark as invalid, just warn
            
            # Check for excessive noise using Laplacian variance
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            quality_metrics['sharpness'] = float(laplacian_var)
            
            if laplacian_var < 10:
                issues.append(f"Image may be too blurry (sharpness: {laplacian_var:.2f})")
                # Don't mark as invalid, preprocessing might help
            
            # Check for oversaturation (too many pure white/black pixels)
            white_pixels = np.sum(gray >= 250)
            black_pixels = np.sum(gray <= 5)
            total_pixels = gray.size
            
            white_ratio = white_pixels / total_pixels
            black_ratio = black_pixels / total_pixels
            
            quality_metrics['white_ratio'] = float(white_ratio)
            quality_metrics['black_ratio'] = float(black_ratio)
            
            if white_ratio > 0.9:
                issues.append(f"Image mostly white ({white_ratio:.1%})")
            elif black_ratio > 0.9:
                issues.append(f"Image mostly black ({black_ratio:.1%})")
            
            # Check aspect ratio for reasonableness
            aspect_ratio = width / height
            quality_metrics['aspect_ratio'] = float(aspect_ratio)
            
            if aspect_ratio > 10 or aspect_ratio < 0.1:
                issues.append(f"Unusual aspect ratio: {aspect_ratio:.2f}")
            
            quality_metrics['issues'] = issues
            quality_metrics['is_valid'] = is_valid
            
            if issues:
                self.logger.warning(f"Image quality issues: {', '.join(issues)}")
            else:
                self.logger.debug("Image quality validation passed")
            
            return is_valid, quality_metrics
            
        except Exception as e:
            error_msg = f"Failed to validate image quality: {str(e)}"
            self.logger.error(error_msg)
            return False, {'error': error_msg, 'issues': [error_msg]}
    
    def enhance_image_quality(self, image: np.ndarray) -> np.ndarray:
        """
        Apply enhancement algorithms to improve image quality.
        
        Args:
            image: Input image to enhance
            
        Returns:
            Enhanced image
        """
        try:
            # Start with preprocessing
            enhanced = self.preprocess_image(image)
            
            # Apply additional enhancements based on image characteristics
            is_valid, metrics = self.validate_image_quality(image)
            
            # If contrast is low, apply histogram equalization
            if metrics.get('contrast_ratio', 1.0) < 0.3:
                enhanced = cv2.equalizeHist(enhanced)
                self.logger.debug("Applied histogram equalization for low contrast")
            
            # If image is blurry, apply sharpening
            if metrics.get('sharpness', 100) < 50:
                kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
                enhanced = cv2.filter2D(enhanced, -1, kernel)
                self.logger.debug("Applied sharpening filter for blurry image")
            
            # Apply edge enhancement for technical drawings
            # This helps with line detection later
            edges = cv2.Canny(enhanced, 50, 150)
            enhanced = cv2.addWeighted(enhanced, 0.8, edges, 0.2, 0)
            
            return enhanced
            
        except Exception as e:
            error_msg = f"Failed to enhance image quality: {str(e)}"
            self.logger.error(error_msg)
            # Return original image if enhancement fails
            return image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    def handle_conversion_failure(self, page: PDFPage, error: Exception) -> Optional[np.ndarray]:
        """
        Handle PDF to image conversion failures with fallback strategies.
        
        Args:
            page: PDFPage that failed to convert
            error: The exception that occurred
            
        Returns:
            Fallback image or None if all strategies fail
        """
        try:
            self.logger.warning(f"Primary conversion failed for page {page.page_number}: {error}")
            
            # Strategy 1: Try lower DPI
            try:
                self.logger.info("Attempting conversion with lower DPI (72)")
                fallback_image = self.pdf_page_to_image(page, dpi=72)
                self.logger.info("Lower DPI conversion successful")
                return fallback_image
            except Exception as e:
                self.logger.warning(f"Lower DPI conversion failed: {e}")
            
            # Strategy 2: Try different rendering mode
            try:
                self.logger.info("Attempting conversion with different rendering parameters")
                # Use simpler rendering without anti-aliasing
                pixmap = page.page_obj.get_pixmap(alpha=False)
                img_data = pixmap.tobytes("ppm")
                pil_image = Image.open(io.BytesIO(img_data))
                img_array = np.array(pil_image)
                
                if len(img_array.shape) == 3:
                    img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                
                self.logger.info("Alternative rendering successful")
                return img_array
                
            except Exception as e:
                self.logger.warning(f"Alternative rendering failed: {e}")
            
            # Strategy 3: Create placeholder image with error message
            self.logger.info("Creating placeholder image for failed conversion")
            placeholder = np.ones((400, 600), dtype=np.uint8) * 255
            cv2.putText(placeholder, f"Page {page.page_number}", (50, 200), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2)
            cv2.putText(placeholder, "Conversion Failed", (50, 250), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2)
            
            return placeholder
            
        except Exception as e:
            self.logger.error(f"All fallback strategies failed: {e}")
            return None