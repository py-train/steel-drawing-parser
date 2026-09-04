"""PDF processing component for steel drawing parser."""

import logging
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass

from ..models.processing import ProcessingError
from ..utils.performance_monitor import get_performance_monitor, monitor_performance


@dataclass
class PDFPage:
    """Represents a single page from a PDF document."""
    page_number: int
    width: float
    height: float
    rotation: int
    page_obj: fitz.Page


@dataclass
class PageMetadata:
    """Metadata for a PDF page."""
    page_number: int
    width: float
    height: float
    rotation: int
    dpi: float
    has_images: bool
    has_text: bool


class PDFProcessor:
    """Handles PDF file input and page extraction."""
    
    def __init__(self):
        self.logger = logging.getLogger('steel_parser.pdf_processor')
        self.performance_monitor = get_performance_monitor()
    
    @monitor_performance("pdf_validation")
    def validate_pdf(self, file_path: str) -> bool:
        """
        Validates PDF file format and readability.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            True if PDF is valid and readable, False otherwise
        """
        try:
            path = Path(file_path)
            
            # Check if file exists
            if not path.exists():
                self.logger.error(f"PDF file does not exist: {file_path}")
                return False
            
            # Check file extension
            if path.suffix.lower() != '.pdf':
                self.logger.error(f"File is not a PDF: {file_path}")
                return False
            
            # Check if file is readable and not empty
            if path.stat().st_size == 0:
                self.logger.error(f"PDF file is empty: {file_path}")
                return False
            
            # Try to open with PyMuPDF
            try:
                doc = fitz.open(file_path)
                
                # Check if PDF is encrypted/password protected
                if doc.needs_pass:
                    self.logger.error(f"PDF is password protected: {file_path}")
                    doc.close()
                    return False
                
                # Check if PDF has pages
                page_count = doc.page_count
                if page_count == 0:
                    self.logger.error(f"PDF has no pages: {file_path}")
                    doc.close()
                    return False
                
                # Try to access first page to ensure PDF is not corrupted
                first_page = doc[0]
                _ = first_page.get_pixmap()  # This will fail if page is corrupted
                
                self.logger.info(f"PDF validation successful: {file_path} ({page_count} pages)")
                doc.close()
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to open PDF {file_path}: {str(e)}")
                try:
                    doc.close()
                except:
                    pass
                return False
                
        except Exception as e:
            self.logger.error(f"Unexpected error validating PDF {file_path}: {str(e)}")
            return False
    
    @monitor_performance("pdf_page_extraction")
    def extract_pages(self, pdf_path: str) -> List[PDFPage]:
        """
        Extracts individual pages as processable objects.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of PDFPage objects
            
        Raises:
            ValueError: If PDF is invalid or cannot be processed
        """
        if not self.validate_pdf(pdf_path):
            raise ValueError(f"Invalid PDF file: {pdf_path}")
        
        try:
            with self.performance_monitor.monitor_operation(
                "pdf_document_processing",
                file_path=pdf_path
            ):
                doc = fitz.open(pdf_path)
                pages = []
                
                for page_num in range(doc.page_count):
                    page = doc[page_num]
                    rect = page.rect
                    
                    pdf_page = PDFPage(
                        page_number=page_num + 1,  # 1-based numbering
                        width=rect.width,
                        height=rect.height,
                        rotation=page.rotation,
                        page_obj=page
                    )
                    pages.append(pdf_page)
                
                self.logger.info(f"Extracted {len(pages)} pages from {pdf_path}")
                return pages
            
        except Exception as e:
            error_msg = f"Failed to extract pages from {pdf_path}: {str(e)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
    
    def get_page_metadata(self, page: PDFPage) -> PageMetadata:
        """
        Retrieves page dimensions and properties.
        
        Args:
            page: PDFPage object
            
        Returns:
            PageMetadata with page information
        """
        try:
            # Check for images and text
            has_images = len(page.page_obj.get_images()) > 0
            has_text = len(page.page_obj.get_text().strip()) > 0
            
            # Calculate effective DPI (assuming standard page sizes)
            # Standard A4 is 210x297mm, Letter is 216x279mm
            # Most technical drawings use these or larger formats
            dpi = min(page.width / 8.27, page.height / 11.69) * 72  # Rough DPI estimate
            
            metadata = PageMetadata(
                page_number=page.page_number,
                width=page.width,
                height=page.height,
                rotation=page.rotation,
                dpi=dpi,
                has_images=has_images,
                has_text=has_text
            )
            
            self.logger.debug(f"Page {page.page_number} metadata: {metadata}")
            return metadata
            
        except Exception as e:
            error_msg = f"Failed to get metadata for page {page.page_number}: {str(e)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
    
    def get_descriptive_error(self, file_path: str) -> str:
        """
        Provides descriptive error messages for invalid files.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Descriptive error message with suggestions
        """
        path = Path(file_path)
        
        if not path.exists():
            return f"File not found: {file_path}. Please check the file path and ensure the file exists."
        
        if path.suffix.lower() != '.pdf':
            return f"Invalid file type: {path.suffix}. Please provide a PDF file (.pdf extension)."
        
        if path.stat().st_size == 0:
            return f"Empty file: {file_path}. The PDF file appears to be empty or corrupted."
        
        try:
            doc = fitz.open(file_path)
            if doc.needs_pass:
                doc.close()
                return f"Password protected PDF: {file_path}. Please provide an unprotected PDF file."
            
            if doc.page_count == 0:
                doc.close()
                return f"No pages found: {file_path}. The PDF file contains no pages."
            
            doc.close()
            
        except Exception as e:
            return f"Corrupted PDF: {file_path}. Error: {str(e)}. Please try with a different PDF file."
        
        return f"Unknown error with PDF: {file_path}. Please verify the file is a valid PDF."