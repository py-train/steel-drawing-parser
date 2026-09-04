"""Tests for PDF processor."""

import pytest
import tempfile
import fitz
from pathlib import Path
from unittest.mock import Mock, patch

from src.processors.pdf_processor import PDFProcessor, PDFPage, PageMetadata


class TestPDFProcessor:
    """Test cases for PDF processor."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.processor = PDFProcessor()
    
    def create_test_pdf(self, num_pages: int = 1) -> str:
        """Create a temporary PDF file for testing."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        # Create a simple PDF with specified number of pages
        doc = fitz.open()  # Create new document
        for i in range(num_pages):
            page = doc.new_page()
            # Add some basic content
            page.insert_text((100, 100), f"Test page {i+1}")
        
        doc.save(temp_path)
        doc.close()
        
        # Verify the file was created properly
        if not Path(temp_path).exists() or Path(temp_path).stat().st_size == 0:
            raise RuntimeError(f"Failed to create test PDF: {temp_path}")
        
        return temp_path
    
    def test_validate_pdf_valid_file(self):
        """Test validation of a valid PDF file."""
        pdf_path = self.create_test_pdf(2)
        try:
            assert self.processor.validate_pdf(pdf_path) is True
        finally:
            Path(pdf_path).unlink()
    
    def test_validate_pdf_nonexistent_file(self):
        """Test validation of non-existent file."""
        assert self.processor.validate_pdf("nonexistent.pdf") is False
    
    def test_validate_pdf_wrong_extension(self):
        """Test validation of file with wrong extension."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.txt', delete=False)
        temp_path = temp_file.name
        temp_file.write(b"Not a PDF")
        temp_file.close()
        
        try:
            assert self.processor.validate_pdf(temp_path) is False
        finally:
            Path(temp_path).unlink()
    
    def test_validate_pdf_empty_file(self):
        """Test validation of empty PDF file."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()  # Creates empty file
        
        try:
            assert self.processor.validate_pdf(temp_path) is False
        finally:
            Path(temp_path).unlink()
    
    def test_extract_pages_valid_pdf(self):
        """Test page extraction from valid PDF."""
        pdf_path = self.create_test_pdf(3)
        try:
            pages = self.processor.extract_pages(pdf_path)
            assert len(pages) == 3
            assert all(isinstance(page, PDFPage) for page in pages)
            assert pages[0].page_number == 1
            assert pages[2].page_number == 3
        finally:
            Path(pdf_path).unlink()
    
    def test_extract_pages_invalid_pdf(self):
        """Test page extraction from invalid PDF."""
        with pytest.raises(ValueError, match="Invalid PDF file"):
            self.processor.extract_pages("nonexistent.pdf")
    
    def test_get_page_metadata(self):
        """Test page metadata extraction."""
        pdf_path = self.create_test_pdf(1)
        try:
            pages = self.processor.extract_pages(pdf_path)
            metadata = self.processor.get_page_metadata(pages[0])
            
            assert isinstance(metadata, PageMetadata)
            assert metadata.page_number == 1
            assert metadata.width > 0
            assert metadata.height > 0
            assert metadata.dpi > 0
            assert metadata.has_text is True  # We added text in create_test_pdf
        finally:
            Path(pdf_path).unlink()
    
    def test_get_descriptive_error_nonexistent(self):
        """Test descriptive error for non-existent file."""
        error = self.processor.get_descriptive_error("nonexistent.pdf")
        assert "File not found" in error
        assert "check the file path" in error
    
    def test_get_descriptive_error_wrong_type(self):
        """Test descriptive error for wrong file type."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.txt', delete=False)
        temp_path = temp_file.name
        temp_file.write(b"Not a PDF")
        temp_file.close()
        
        try:
            error = self.processor.get_descriptive_error(temp_path)
            assert "Invalid file type" in error
            assert "PDF file" in error
        finally:
            Path(temp_path).unlink()
    
    def test_get_descriptive_error_empty_file(self):
        """Test descriptive error for empty file."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        try:
            error = self.processor.get_descriptive_error(temp_path)
            assert "Empty file" in error
            assert "empty or corrupted" in error
        finally:
            Path(temp_path).unlink()


class TestPDFPageModel:
    """Test cases for PDFPage data model."""
    
    def test_pdf_page_creation(self):
        """Test PDFPage object creation."""
        mock_page = Mock()
        page = PDFPage(
            page_number=1,
            width=595.0,
            height=842.0,
            rotation=0,
            page_obj=mock_page
        )
        
        assert page.page_number == 1
        assert page.width == 595.0
        assert page.height == 842.0
        assert page.rotation == 0
        assert page.page_obj == mock_page


class TestPageMetadataModel:
    """Test cases for PageMetadata data model."""
    
    def test_page_metadata_creation(self):
        """Test PageMetadata object creation."""
        metadata = PageMetadata(
            page_number=1,
            width=595.0,
            height=842.0,
            rotation=0,
            dpi=300.0,
            has_images=True,
            has_text=False
        )
        
        assert metadata.page_number == 1
        assert metadata.width == 595.0
        assert metadata.dpi == 300.0
        assert metadata.has_images is True
        assert metadata.has_text is False