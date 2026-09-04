"""Integration tests for complete steel component recognition pipeline."""

import tempfile
import fitz
import numpy as np
from pathlib import Path

from src.processors import PDFProcessor, ImageExtractor
from src.extractors import PartExtractor
from src.models.component import ComponentType


class TestSteelComponentIntegration:
    """Integration tests for the complete steel component recognition system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.pdf_processor = PDFProcessor()
        self.image_extractor = ImageExtractor(dpi=150)
        self.part_extractor = PartExtractor(min_component_size=30, confidence_threshold=0.5)
    
    def create_comprehensive_steel_drawing_pdf(self) -> str:
        """Create a comprehensive PDF with various steel components."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        doc = fitz.open()
        
        # Page 1: Main structural layout
        page1 = doc.new_page()
        
        # Title and drawing info
        page1.insert_text((50, 50), "STEEL STRUCTURE - MAIN FRAME", fontsize=16)
        page1.insert_text((50, 80), "Drawing No: S-001", fontsize=12)
        page1.insert_text((50, 100), "Scale: 1/4\" = 1'-0\"", fontsize=10)
        
        # Main structural frame
        # Horizontal beams (multiple similar beams)
        beam_y_positions = [200, 300, 400]
        for y in beam_y_positions:
            # Draw I-beam representation (top flange, web, bottom flange)
            page1.draw_line(fitz.Point(100, y-5), fitz.Point(400, y-5))    # Top flange
            page1.draw_line(fitz.Point(250, y-5), fitz.Point(250, y+5))    # Web
            page1.draw_line(fitz.Point(100, y+5), fitz.Point(400, y+5))    # Bottom flange
            
            # Add dimension annotation
            page1.insert_text((420, y), "W12x26", fontsize=8)
            page1.insert_text((450, y), "300mm", fontsize=8)
        
        # Vertical columns (similar columns)
        column_x_positions = [95, 405]
        for x in column_x_positions:
            # Draw column representation
            page1.draw_line(fitz.Point(x-5, 150), fitz.Point(x-5, 450))    # Left flange
            page1.draw_line(fitz.Point(x-5, 300), fitz.Point(x+5, 300))    # Web
            page1.draw_line(fitz.Point(x+5, 150), fitz.Point(x+5, 450))    # Right flange
            
            # Add material specification
            page1.insert_text((x-20, 470), "W14x30", fontsize=8)
        
        # Base plates
        for x in column_x_positions:
            page1.draw_rect(fitz.Rect(x-15, 440, x+15, 460))  # Base plate
            page1.insert_text((x-10, 475), "PL 1\"", fontsize=7)
        
        # Page 2: Connection details
        page2 = doc.new_page()
        page2.insert_text((50, 50), "CONNECTION DETAILS", fontsize=14)
        page2.insert_text((50, 80), "Detail A: Beam-to-Column Connection", fontsize=12)
        
        # Connection detail with bolts
        # Draw connection plate
        page2.draw_rect(fitz.Rect(150, 200, 350, 300))
        page2.insert_text((360, 250), "Connection Plate", fontsize=10)
        page2.insert_text((360, 270), "PL 1/2\" x 8\" x 12\"", fontsize=8)
        page2.insert_text((360, 290), "A36", fontsize=8)
        
        # Draw bolts in a pattern
        bolt_positions = [
            (180, 220), (180, 250), (180, 280),
            (220, 220), (220, 250), (220, 280),
            (280, 220), (280, 250), (280, 280),
            (320, 220), (320, 250), (320, 280)
        ]
        
        for pos in bolt_positions:
            page2.draw_circle(fitz.Point(pos[0], pos[1]), 4)
        
        # Bolt specification
        page2.insert_text((360, 320), "12 - 3/4\" A325 Bolts", fontsize=10)
        page2.insert_text((360, 340), "Standard holes", fontsize=8)
        
        # Add some dimension lines
        page2.draw_line(fitz.Point(150, 180), fitz.Point(350, 180))  # Overall width
        page2.insert_text((230, 175), "200mm", fontsize=8)
        
        page2.draw_line(fitz.Point(130, 200), fitz.Point(130, 300))  # Overall height
        page2.insert_text((120, 245), "100mm", fontsize=8)
        
        doc.save(temp_path)
        doc.close()
        return temp_path
    
    def test_complete_steel_component_recognition_pipeline(self):
        """Test the complete pipeline from PDF to component recognition."""
        pdf_path = self.create_comprehensive_steel_drawing_pdf()
        
        try:
            # Step 1: Process PDF
            assert self.pdf_processor.validate_pdf(pdf_path) is True
            pages = self.pdf_processor.extract_pages(pdf_path)
            assert len(pages) == 2
            
            all_components = []
            
            # Step 2: Process each page
            for page in pages:
                # Convert to image
                image = self.image_extractor.pdf_page_to_image(page)
                assert image is not None
                
                # Validate image quality
                is_valid, quality_metrics = self.image_extractor.validate_image_quality(image)
                assert is_valid is True
                
                # Preprocess image
                preprocessed = self.image_extractor.preprocess_image(image)
                assert preprocessed is not None
                
                # Detect components
                components = self.part_extractor.detect_steel_components(preprocessed, page.page_number)
                all_components.extend(components)
            
            # Step 3: Analyze results
            assert len(all_components) > 0, "Should detect some components"
            
            # Check component types detected
            component_types = {c.type for c in all_components}
            print(f"Detected component types: {component_types}")
            
            # Should detect multiple types of components
            assert len(component_types) >= 2, f"Should detect multiple component types, got: {component_types}"
            
            # Check for quantity counting
            total_individual_parts = sum(c.quantity for c in all_components)
            assert total_individual_parts >= len(all_components), "Total parts should be >= unique components"
            
            # Check that some components have enhanced information
            components_with_dimensions = [c for c in all_components if c.dimensions and 
                                        (c.dimensions.width or c.dimensions.height)]
            components_with_materials = [c for c in all_components if c.material and 
                                       (c.material.grade or c.material.specification)]
            
            print(f"Components with dimensions: {len(components_with_dimensions)}")
            print(f"Components with materials: {len(components_with_materials)}")
            
            # Verify location tracking
            for component in all_components:
                assert component.location is not None
                assert component.location.page_number in [1, 2]
                assert component.location.x >= 0
                assert component.location.y >= 0
            
            # Test quantity statistics
            stats = self.part_extractor.get_quantity_statistics(all_components)
            assert stats['total_unique_components'] == len(all_components)
            assert stats['total_individual_parts'] >= len(all_components)
            assert 'by_type' in stats
            
            # Test location tracking
            locations = self.part_extractor.get_component_locations(all_components)
            assert len(locations) == len(all_components)
            
            # Print summary for verification
            print(f"\n=== COMPONENT RECOGNITION SUMMARY ===")
            print(f"Total unique components: {len(all_components)}")
            print(f"Total individual parts: {total_individual_parts}")
            print(f"Component types found: {list(component_types)}")
            print(f"Components with dimensions: {len(components_with_dimensions)}")
            print(f"Components with materials: {len(components_with_materials)}")
            
            for comp_type in component_types:
                type_components = [c for c in all_components if c.type == comp_type]
                print(f"{comp_type.value}: {len(type_components)} unique, "
                      f"{sum(c.quantity for c in type_components)} total")
            
        finally:
            Path(pdf_path).unlink()
    
    def test_component_similarity_and_grouping(self):
        """Test that similar components are properly grouped and counted."""
        pdf_path = self.create_comprehensive_steel_drawing_pdf()
        
        try:
            pages = self.pdf_processor.extract_pages(pdf_path)
            
            # Process first page (should have multiple similar beams and columns)
            page1_image = self.image_extractor.pdf_page_to_image(pages[0])
            preprocessed = self.image_extractor.preprocess_image(page1_image)
            components = self.part_extractor.detect_steel_components(preprocessed, 1)
            
            # Check for grouped components (quantity > 1)
            grouped_components = [c for c in components if c.quantity > 1]
            
            if grouped_components:
                print(f"Found {len(grouped_components)} grouped components:")
                for comp in grouped_components:
                    print(f"  {comp.type.value}: quantity {comp.quantity}")
                    
                    # Check that grouped components have location metadata
                    if 'quantity_group' in comp.extraction_metadata:
                        group_data = comp.extraction_metadata['quantity_group']
                        assert group_data['total_count'] == comp.quantity
                        assert len(group_data['individual_locations']) == comp.quantity
            
        finally:
            Path(pdf_path).unlink()
    
    def test_dimension_and_material_extraction_integration(self):
        """Test that dimensions and materials are properly extracted and associated."""
        pdf_path = self.create_comprehensive_steel_drawing_pdf()
        
        try:
            pages = self.pdf_processor.extract_pages(pdf_path)
            
            all_components = []
            for page in pages:
                image = self.image_extractor.pdf_page_to_image(page)
                preprocessed = self.image_extractor.preprocess_image(image)
                components = self.part_extractor.detect_steel_components(preprocessed, page.page_number)
                all_components.extend(components)
            
            # Check extraction metadata
            for component in all_components:
                metadata = component.extraction_metadata
                
                # Should have extraction flags
                assert 'dimension_extraction' in metadata
                assert 'material_extraction' in metadata
                
                # Should have original detection features
                assert 'detection_features' in metadata
                assert 'bbox' in metadata
            
            # Print component details for verification
            print(f"\n=== COMPONENT DETAILS ===")
            for i, comp in enumerate(all_components[:5]):  # Show first 5 components
                print(f"Component {i+1}: {comp.type.value} (ID: {comp.id})")
                print(f"  Quantity: {comp.quantity}")
                print(f"  Confidence: {comp.confidence:.2f}")
                print(f"  Location: ({comp.location.x:.1f}, {comp.location.y:.1f}) on page {comp.location.page_number}")
                
                if comp.dimensions:
                    dims = comp.dimensions
                    print(f"  Dimensions: {dims.width}x{dims.height} {dims.unit}")
                
                if comp.material:
                    mat = comp.material
                    print(f"  Material: {mat.grade} ({mat.specification})")
                
                print()
            
        finally:
            Path(pdf_path).unlink()
    
    def test_error_resilience_and_recovery(self):
        """Test that the system handles various error conditions gracefully."""
        # Test with minimal/problematic PDF
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        # Create very simple PDF
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((100, 100), "Minimal drawing")
        doc.save(temp_path)
        doc.close()
        
        try:
            # Should not crash even with minimal content
            pages = self.pdf_processor.extract_pages(temp_path)
            image = self.image_extractor.pdf_page_to_image(pages[0])
            preprocessed = self.image_extractor.preprocess_image(image)
            components = self.part_extractor.detect_steel_components(preprocessed, 1)
            
            # Should return empty list or minimal results without crashing
            assert isinstance(components, list)
            
        finally:
            Path(temp_path).unlink()
    
    def test_performance_characteristics(self):
        """Test performance characteristics of the complete pipeline."""
        pdf_path = self.create_comprehensive_steel_drawing_pdf()
        
        try:
            import time
            
            start_time = time.time()
            
            # Process complete pipeline
            pages = self.pdf_processor.extract_pages(pdf_path)
            
            total_components = 0
            for page in pages:
                image = self.image_extractor.pdf_page_to_image(page)
                preprocessed = self.image_extractor.preprocess_image(image)
                components = self.part_extractor.detect_steel_components(preprocessed, page.page_number)
                total_components += len(components)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            print(f"\n=== PERFORMANCE METRICS ===")
            print(f"Total processing time: {processing_time:.2f} seconds")
            print(f"Pages processed: {len(pages)}")
            print(f"Components detected: {total_components}")
            print(f"Time per page: {processing_time/len(pages):.2f} seconds")
            print(f"Time per component: {processing_time/max(1, total_components):.3f} seconds")
            
            # Should complete in reasonable time
            assert processing_time < 30.0, f"Processing took too long: {processing_time:.2f}s"
            
        finally:
            Path(pdf_path).unlink()