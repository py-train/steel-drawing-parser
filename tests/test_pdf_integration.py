"""Integration tests for PDF processing."""

import tempfile
import fitz
from pathlib import Path

from src.processors import PDFProcessor


class TestPDFIntegration:
    """Integration tests for PDF processing workflow."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.processor = PDFProcessor()
    
    def create_complex_test_pdf(self) -> str:
        """Create a more complex PDF for integration testing."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        doc = fitz.open()
        
        # Page 1: Title page with text
        page1 = doc.new_page()
        page1.insert_text((100, 100), "Steel Drawing Set")
        page1.insert_text((100, 150), "Project: Test Building")
        
        # Page 2: Drawing page with shapes (simulating steel components)
        page2 = doc.new_page()
        page2.insert_text((50, 50), "Drawing 1: Floor Plan")
        # Add some rectangles to simulate steel beams
        page2.draw_rect(fitz.Rect(100, 200, 400, 220))
        page2.draw_rect(fitz.Rect(100, 300, 400, 320))
        
        # Page 3: Detail page
        page3 = doc.new_page()
        page3.insert_text((50, 50), "Detail A: Connection")
        page3.draw_circle(fitz.Point(200, 200), 20)  # Simulate bolt
        
        doc.save(temp_path)
        doc.close()
        return temp_path
    
    def test_complete_pdf_processing_workflow(self):
        """Test complete PDF processing from validation to metadata extraction."""
        pdf_path = self.create_complex_test_pdf()
        
        try:
            # Step 1: Validate PDF
            assert self.processor.validate_pdf(pdf_path) is True
            
            # Step 2: Extract pages
            pages = self.processor.extract_pages(pdf_path)
            assert len(pages) == 3
            
            # Step 3: Get metadata for each page
            metadata_list = []
            for page in pages:
                metadata = self.processor.get_page_metadata(page)
                metadata_list.append(metadata)
                
                # Verify metadata structure
                assert metadata.page_number > 0
                assert metadata.width > 0
                assert metadata.height > 0
                assert metadata.dpi > 0
            
            # Verify page numbering is correct
            page_numbers = [m.page_number for m in metadata_list]
            assert page_numbers == [1, 2, 3]
            
            # Verify all pages have text (we added text to all pages)
            assert all(m.has_text for m in metadata_list)
            
        finally:
            Path(pdf_path).unlink()
    
    def test_error_handling_workflow(self):
        """Test error handling throughout the workflow."""
        # Test with non-existent file
        assert self.processor.validate_pdf("nonexistent.pdf") is False
        
        # Test descriptive error messages
        error_msg = self.processor.get_descriptive_error("nonexistent.pdf")
        assert "File not found" in error_msg
        assert "check the file path" in error_msg
        
        # Test with invalid file should raise ValueError
        try:
            self.processor.extract_pages("nonexistent.pdf")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Invalid PDF file" in str(e)
    
    def test_single_page_pdf(self):
        """Test processing of single-page PDF."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((100, 100), "Single page document")
        doc.save(temp_path)
        doc.close()
        
        try:
            assert self.processor.validate_pdf(temp_path) is True
            pages = self.processor.extract_pages(temp_path)
            assert len(pages) == 1
            assert pages[0].page_number == 1
            
            metadata = self.processor.get_page_metadata(pages[0])
            assert metadata.page_number == 1
            assert metadata.has_text is True
            
        finally:
            Path(temp_path).unlink()