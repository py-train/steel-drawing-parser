"""Tests for image extractor."""

import pytest
import numpy as np
import cv2
import tempfile
import fitz
from pathlib import Path

from src.processors.pdf_processor import PDFProcessor
from src.processors.image_extractor import ImageExtractor, BoundingBox


class TestBoundingBox:
    """Test cases for BoundingBox data model."""
    
    def test_bounding_box_creation(self):
        """Test BoundingBox object creation."""
        bbox = BoundingBox(10, 20, 100, 50, 0.8)
        assert bbox.x == 10
        assert bbox.y == 20
        assert bbox.width == 100
        assert bbox.height == 50
        assert bbox.confidence == 0.8
    
    def test_bounding_box_area(self):
        """Test area calculation."""
        bbox = BoundingBox(0, 0, 100, 50)
        assert bbox.area == 5000
    
    def test_bounding_box_center(self):
        """Test center point calculation."""
        bbox = BoundingBox(10, 20, 100, 50)
        center = bbox.center
        assert center == (60, 45)  # (10 + 100//2, 20 + 50//2)


class TestImageExtractor:
    """Test cases for image extractor."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.extractor = ImageExtractor(dpi=150)  # Lower DPI for faster tests
        self.pdf_processor = PDFProcessor()
    
    def create_test_pdf_with_content(self) -> str:
        """Create a test PDF with some visual content."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        doc = fitz.open()
        page = doc.new_page()
        
        # Add text
        page.insert_text((100, 100), "Test Drawing")
        
        # Add some shapes to simulate drawing content
        page.draw_rect(fitz.Rect(50, 150, 200, 200))  # Rectangle
        page.draw_circle(fitz.Point(300, 300), 30)    # Circle
        page.draw_line(fitz.Point(100, 400), fitz.Point(400, 400))  # Line
        
        doc.save(temp_path)
        doc.close()
        return temp_path
    
    def test_pdf_page_to_image_conversion(self):
        """Test PDF page to image conversion."""
        pdf_path = self.create_test_pdf_with_content()
        
        try:
            pages = self.pdf_processor.extract_pages(pdf_path)
            image = self.extractor.pdf_page_to_image(pages[0])
            
            # Check that we got a valid image
            assert isinstance(image, np.ndarray)
            assert len(image.shape) in [2, 3]  # Grayscale or color
            assert image.size > 0
            
            # Check image dimensions are reasonable
            height, width = image.shape[:2]
            assert height > 100
            assert width > 100
            
        finally:
            Path(pdf_path).unlink()
    
    def test_pdf_page_to_image_custom_dpi(self):
        """Test PDF page to image conversion with custom DPI."""
        pdf_path = self.create_test_pdf_with_content()
        
        try:
            pages = self.pdf_processor.extract_pages(pdf_path)
            
            # Convert with different DPIs
            image_low = self.extractor.pdf_page_to_image(pages[0], dpi=72)
            image_high = self.extractor.pdf_page_to_image(pages[0], dpi=300)
            
            # Higher DPI should produce larger image
            assert image_high.shape[0] > image_low.shape[0]
            assert image_high.shape[1] > image_low.shape[1]
            
        finally:
            Path(pdf_path).unlink()
    
    def test_preprocess_image(self):
        """Test image preprocessing."""
        # Create a test image with some noise
        test_image = np.random.randint(0, 255, (200, 300, 3), dtype=np.uint8)
        
        # Add some structure (lines and rectangles)
        cv2.rectangle(test_image, (50, 50), (150, 100), (0, 0, 0), 2)
        cv2.line(test_image, (0, 150), (300, 150), (0, 0, 0), 1)
        
        processed = self.extractor.preprocess_image(test_image)
        
        # Check that preprocessing returns a valid image
        assert isinstance(processed, np.ndarray)
        assert len(processed.shape) == 2  # Should be grayscale
        assert processed.shape[0] == test_image.shape[0]
        assert processed.shape[1] == test_image.shape[1]
    
    def test_preprocess_grayscale_image(self):
        """Test preprocessing of already grayscale image."""
        # Create grayscale test image
        test_image = np.random.randint(0, 255, (200, 300), dtype=np.uint8)
        
        processed = self.extractor.preprocess_image(test_image)
        
        assert isinstance(processed, np.ndarray)
        assert len(processed.shape) == 2
        assert processed.shape == test_image.shape
    
    def test_detect_drawing_regions(self):
        """Test drawing region detection."""
        # Create a test image with distinct regions
        test_image = np.ones((400, 600), dtype=np.uint8) * 255  # White background
        
        # Add some "drawing" regions (black rectangles)
        cv2.rectangle(test_image, (50, 50), (200, 150), 0, -1)    # Filled rectangle
        cv2.rectangle(test_image, (300, 200), (500, 350), 0, -1)  # Another rectangle
        
        regions = self.extractor.detect_drawing_regions(test_image, min_area=5000)
        
        # Should detect at least the regions we created
        assert len(regions) >= 1
        assert all(isinstance(region, BoundingBox) for region in regions)
        assert all(region.area >= 5000 for region in regions)
    
    def test_detect_drawing_regions_empty_image(self):
        """Test region detection on empty image."""
        # Create empty (white) image
        test_image = np.ones((400, 600), dtype=np.uint8) * 255
        
        regions = self.extractor.detect_drawing_regions(test_image)
        
        # Should return at least one region (the entire image)
        assert len(regions) >= 1
        
        # If no specific regions found, should return full image
        if len(regions) == 1:
            region = regions[0]
            assert region.x == 0
            assert region.y == 0
            assert region.width == test_image.shape[1]
            assert region.height == test_image.shape[0]
    
    def test_extract_region(self):
        """Test region extraction from image."""
        # Create test image
        test_image = np.random.randint(0, 255, (200, 300, 3), dtype=np.uint8)
        
        # Define a region to extract
        bbox = BoundingBox(50, 30, 100, 80)
        
        extracted = self.extractor.extract_region(test_image, bbox)
        
        # Check extracted region dimensions
        assert extracted.shape[0] == bbox.height
        assert extracted.shape[1] == bbox.width
        assert extracted.shape[2] == test_image.shape[2]  # Same number of channels
    
    def test_extract_region_bounds_checking(self):
        """Test region extraction with out-of-bounds coordinates."""
        test_image = np.random.randint(0, 255, (100, 150), dtype=np.uint8)
        
        # Define region that extends beyond image bounds
        bbox = BoundingBox(120, 80, 100, 50)  # Starts outside image
        
        extracted = self.extractor.extract_region(test_image, bbox)
        
        # Should extract only the valid portion
        assert extracted.shape[0] > 0
        assert extracted.shape[1] > 0
    
    def test_get_image_stats(self):
        """Test image statistics calculation."""
        # Create test image with known properties
        test_image = np.ones((100, 150, 3), dtype=np.uint8) * 128  # Gray image
        
        stats = self.extractor.get_image_stats(test_image)
        
        assert 'shape' in stats
        assert 'mean_intensity' in stats
        assert 'std_intensity' in stats
        assert 'min_intensity' in stats
        assert 'max_intensity' in stats
        
        assert stats['shape'] == (100, 150, 3)
        assert abs(stats['mean_intensity'] - 128) < 1  # Should be close to 128
    
    def test_get_image_stats_grayscale(self):
        """Test image statistics for grayscale image."""
        test_image = np.ones((100, 150), dtype=np.uint8) * 64
        
        stats = self.extractor.get_image_stats(test_image)
        
        assert stats['shape'] == (100, 150)
        assert abs(stats['mean_intensity'] - 64) < 1
    
    def test_validate_image_quality_good_image(self):
        """Test quality validation on good image."""
        # Create image with good characteristics
        test_image = np.random.randint(50, 200, (300, 400), dtype=np.uint8)
        
        is_valid, metrics = self.extractor.validate_image_quality(test_image)
        
        assert is_valid is True
        assert 'dimensions' in metrics
        assert 'mean_intensity' in metrics
        assert 'contrast_ratio' in metrics
        assert 'sharpness' in metrics
        assert metrics['dimensions'] == (300, 400)
    
    def test_validate_image_quality_small_image(self):
        """Test quality validation on too-small image."""
        # Create very small image
        test_image = np.ones((50, 50), dtype=np.uint8) * 128
        
        is_valid, metrics = self.extractor.validate_image_quality(test_image)
        
        assert is_valid is False
        assert 'issues' in metrics
        assert any('too small' in issue for issue in metrics['issues'])
    
    def test_validate_image_quality_blank_image(self):
        """Test quality validation on blank image."""
        # Create blank (uniform) image
        test_image = np.ones((200, 300), dtype=np.uint8) * 128
        
        is_valid, metrics = self.extractor.validate_image_quality(test_image)
        
        assert is_valid is False
        assert 'issues' in metrics
        assert any('blank' in issue for issue in metrics['issues'])
    
    def test_validate_image_quality_low_contrast(self):
        """Test quality validation on low contrast image."""
        # Create low contrast image (values between 120-130)
        test_image = np.random.randint(120, 130, (200, 300), dtype=np.uint8)
        
        is_valid, metrics = self.extractor.validate_image_quality(test_image)
        
        # Should still be valid but with contrast warning
        assert 'contrast_ratio' in metrics
        assert metrics['contrast_ratio'] < 0.1
        assert 'issues' in metrics
    
    def test_enhance_image_quality(self):
        """Test image quality enhancement."""
        # Create a low-quality image
        test_image = np.ones((200, 300), dtype=np.uint8) * 100
        # Add some noise and structure
        noise = np.random.randint(-20, 20, test_image.shape)
        test_image = np.clip(test_image.astype(int) + noise, 0, 255).astype(np.uint8)
        
        enhanced = self.extractor.enhance_image_quality(test_image)
        
        assert isinstance(enhanced, np.ndarray)
        assert enhanced.shape[:2] == test_image.shape[:2]
        assert len(enhanced.shape) == 2  # Should be grayscale
    
    def test_handle_conversion_failure(self):
        """Test conversion failure handling."""
        pdf_path = self.create_test_pdf_with_content()
        
        try:
            pages = self.pdf_processor.extract_pages(pdf_path)
            page = pages[0]
            
            # Simulate a conversion error
            test_error = ValueError("Simulated conversion error")
            
            fallback_image = self.extractor.handle_conversion_failure(page, test_error)
            
            # Should return some kind of image (placeholder or fallback)
            assert fallback_image is not None
            assert isinstance(fallback_image, np.ndarray)
            assert len(fallback_image.shape) in [2, 3]
            
        finally:
            Path(pdf_path).unlink()