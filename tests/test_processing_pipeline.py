"""Integration tests for the complete processing pipeline."""

import tempfile
import fitz
import numpy as np
from pathlib import Path

from src.processors import PDFProcessor, ImageExtractor


class TestProcessingPipeline:
    """Integration tests for PDF and image processing pipeline."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.pdf_processor = PDFProcessor()
        self.image_extractor = ImageExtractor(dpi=150)  # Lower DPI for faster tests
    
    def create_technical_drawing_pdf(self) -> str:
        """Create a PDF that simulates a technical drawing."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        doc = fitz.open()
        
        # Page 1: Title block and drawing frame
        page1 = doc.new_page()
        
        # Title block
        page1.insert_text((50, 50), "STEEL STRUCTURE DRAWING", fontsize=16)
        page1.insert_text((50, 80), "Project: Test Building", fontsize=12)
        page1.insert_text((50, 100), "Drawing No: S-001", fontsize=12)
        
        # Drawing frame
        page1.draw_rect(fitz.Rect(40, 40, 550, 750))
        
        # Simulate steel beams (horizontal rectangles)
        page1.draw_rect(fitz.Rect(100, 200, 400, 210))  # Beam 1
        page1.draw_rect(fitz.Rect(100, 300, 400, 310))  # Beam 2
        page1.draw_rect(fitz.Rect(100, 400, 400, 410))  # Beam 3
        
        # Simulate columns (vertical rectangles)
        page1.draw_rect(fitz.Rect(95, 150, 105, 450))   # Column 1
        page1.draw_rect(fitz.Rect(395, 150, 405, 450))  # Column 2
        
        # Add dimension lines and text
        page1.draw_line(fitz.Point(100, 180), fitz.Point(400, 180))  # Dimension line
        page1.insert_text((220, 175), "300mm", fontsize=8)
        
        # Add material specifications
        page1.insert_text((420, 200), "W12x26", fontsize=8)
        page1.insert_text((420, 300), "W12x26", fontsize=8)
        page1.insert_text((420, 400), "W12x26", fontsize=8)
        
        # Page 2: Connection details
        page2 = doc.new_page()
        page2.insert_text((50, 50), "CONNECTION DETAILS", fontsize=14)
        
        # Simulate bolted connection
        page2.draw_rect(fitz.Rect(100, 150, 300, 200))  # Plate
        page2.draw_circle(fitz.Point(150, 175), 5)      # Bolt 1
        page2.draw_circle(fitz.Point(200, 175), 5)      # Bolt 2
        page2.draw_circle(fitz.Point(250, 175), 5)      # Bolt 3
        
        # Add bolt specifications
        page2.insert_text((320, 175), "3/4\" A325 BOLTS", fontsize=8)
        
        doc.save(temp_path)
        doc.close()
        return temp_path
    
    def test_complete_processing_pipeline(self):
        """Test the complete pipeline from PDF to processed images."""
        pdf_path = self.create_technical_drawing_pdf()
        
        try:
            # Step 1: Validate and extract PDF pages
            assert self.pdf_processor.validate_pdf(pdf_path) is True
            pages = self.pdf_processor.extract_pages(pdf_path)
            assert len(pages) == 2
            
            # Step 2: Process each page through the image pipeline
            processed_pages = []
            
            for page in pages:
                # Get page metadata
                metadata = self.pdf_processor.get_page_metadata(page)
                assert metadata.page_number > 0
                assert metadata.has_text is True  # Our test PDF has text
                
                # Convert to image
                image = self.image_extractor.pdf_page_to_image(page)
                assert isinstance(image, np.ndarray)
                assert image.size > 0
                
                # Validate image quality
                is_valid, quality_metrics = self.image_extractor.validate_image_quality(image)
                assert is_valid is True
                assert quality_metrics['contrast_ratio'] > 0.1  # Should have decent contrast
                
                # Preprocess image
                preprocessed = self.image_extractor.preprocess_image(image)
                assert isinstance(preprocessed, np.ndarray)
                assert len(preprocessed.shape) == 2  # Should be grayscale
                
                # Detect drawing regions
                regions = self.image_extractor.detect_drawing_regions(preprocessed)
                assert len(regions) >= 1
                
                # Extract and process each region
                for region in regions:
                    extracted_region = self.image_extractor.extract_region(preprocessed, region)
                    assert extracted_region.size > 0
                    
                    # Get statistics for the region
                    stats = self.image_extractor.get_image_stats(extracted_region)
                    assert 'mean_intensity' in stats
                    assert 'shape' in stats
                
                processed_pages.append({
                    'page_number': page.page_number,
                    'metadata': metadata,
                    'image': image,
                    'preprocessed': preprocessed,
                    'regions': regions,
                    'quality_metrics': quality_metrics
                })
            
            # Verify we processed all pages
            assert len(processed_pages) == 2
            
            # Verify page ordering
            page_numbers = [p['page_number'] for p in processed_pages]
            assert page_numbers == [1, 2]
            
            # Verify both pages have reasonable content
            for page_data in processed_pages:
                assert page_data['quality_metrics']['is_valid'] is True
                assert len(page_data['regions']) >= 1
                assert page_data['preprocessed'].size > 0
                
        finally:
            Path(pdf_path).unlink()
    
    def test_pipeline_error_handling(self):
        """Test pipeline behavior with problematic inputs."""
        # Test with non-existent file
        assert self.pdf_processor.validate_pdf("nonexistent.pdf") is False
        
        # Test with invalid file should raise appropriate errors
        try:
            self.pdf_processor.extract_pages("nonexistent.pdf")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Invalid PDF file" in str(e)
    
    def test_pipeline_with_low_quality_image(self):
        """Test pipeline with low quality image processing."""
        # Create a very simple PDF (might result in low quality image)
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((100, 100), "Simple text")
        doc.save(temp_path)
        doc.close()
        
        try:
            pages = self.pdf_processor.extract_pages(temp_path)
            image = self.image_extractor.pdf_page_to_image(pages[0])
            
            # Even if quality is low, pipeline should handle it
            is_valid, metrics = self.image_extractor.validate_image_quality(image)
            
            # If image is invalid, enhancement should still work
            if not is_valid:
                enhanced = self.image_extractor.enhance_image_quality(image)
                assert isinstance(enhanced, np.ndarray)
                assert enhanced.size > 0
            
            # Preprocessing should always work
            preprocessed = self.image_extractor.preprocess_image(image)
            assert isinstance(preprocessed, np.ndarray)
            
        finally:
            Path(temp_path).unlink()
    
    def test_pipeline_performance_characteristics(self):
        """Test pipeline performance and resource usage."""
        pdf_path = self.create_technical_drawing_pdf()
        
        try:
            import time
            
            start_time = time.time()
            
            # Process the PDF
            pages = self.pdf_processor.extract_pages(pdf_path)
            
            for page in pages:
                image = self.image_extractor.pdf_page_to_image(page)
                preprocessed = self.image_extractor.preprocess_image(image)
                regions = self.image_extractor.detect_drawing_regions(preprocessed)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Should complete in reasonable time (adjust threshold as needed)
            assert processing_time < 10.0, f"Processing took too long: {processing_time:.2f}s"
            
            # Memory usage should be reasonable (images should not be too large)
            for page in pages:
                image = self.image_extractor.pdf_page_to_image(page)
                # At 150 DPI, images shouldn't be excessively large
                assert image.nbytes < 50 * 1024 * 1024, "Image too large (>50MB)"
                
        finally:
            Path(pdf_path).unlink()