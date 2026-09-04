"""Gradio web interface for the steel drawing parser."""

import gradio as gr
import tempfile
import os
import time
import traceback
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
import pandas as pd

from ..processors.pdf_processor import PDFProcessor
from ..processors.image_extractor import ImageExtractor
from ..extractors.extensible_part_extractor import ExtensiblePartExtractor
from ..extractors.dimension_extractor import DimensionExtractor
from ..extractors.data_validator import DataValidator
from ..generators.csv_generator import CSVGenerator
from ..utils.logging_config import setup_logging, get_logger_instance
from ..utils.error_handling import resilient_operation, log_status_update, get_error_manager
from ..utils.performance_monitor import get_performance_monitor, monitor_performance
from ..models.configuration_manager import SystemConfig


class SteelDrawingParserInterface:
    """Gradio web interface for steel drawing parser."""
    
    def __init__(self, config: Optional[SystemConfig] = None):
        """Initialize the web interface."""
        # Store configuration
        self.config = config
        
        # Set up logging
        if config and config.logging:
            self.logger_config = setup_logging(
                log_dir=config.logging.log_dir, 
                log_level=config.logging.log_level
            )
        else:
            self.logger_config = setup_logging(log_level="INFO")
        
        self.logger = self.logger_config.get_logger('steel_parser.web_interface')
        
        # Initialize processing components with configuration
        extraction_config = config.extraction if config else None
        
        self.pdf_processor = PDFProcessor()
        self.image_extractor = ImageExtractor(config=extraction_config)
        self.part_extractor = ExtensiblePartExtractor()
        self.dimension_extractor = DimensionExtractor()
        self.data_validator = DataValidator()
        self.csv_generator = CSVGenerator()
        
        # Initialize performance monitoring
        self.performance_monitor = get_performance_monitor()
        self.performance_monitor.start_background_monitoring()
        
        # Interface state
        self.current_results = None
        self.processing_stats = {}
        
        self.logger.info("Steel Drawing Parser Interface initialized")
        if config:
            self.logger.info(f"Configuration loaded: extensibility={config.enable_extensibility}")
            self.logger.info("Performance monitoring enabled")
    
    def get_configuration_info(self) -> Dict[str, Any]:
        """Get current configuration information for display."""
        if not self.config:
            return {"status": "No configuration loaded"}
        
        return {
            "extraction": {
                "confidence_threshold": self.config.extraction.confidence_threshold,
                "min_component_size": self.config.extraction.min_component_size,
                "supported_units": self.config.extraction.supported_units,
                "material_standards": self.config.extraction.material_standards
            },
            "web_interface": {
                "host": self.config.web_interface.host,
                "port": self.config.web_interface.port,
                "max_file_size_mb": self.config.web_interface.max_file_size_mb,
                "component_management_enabled": self.config.web_interface.enable_component_management
            },
            "extensibility_enabled": self.config.enable_extensibility,
            "part_types_config": self.config.part_types_config_file
        }
    
    @resilient_operation('file_upload_processing', max_retries=2)
    def process_file_upload(self, file_path: str, 
                          confidence_threshold: float = 0.5,
                          include_validation: bool = True,
                          progress_callback=None) -> Tuple[str, str, str, Dict[str, Any]]:
        """
        Process uploaded PDF file and extract steel components.
        
        Args:
            file_path: Path to uploaded PDF file
            confidence_threshold: Minimum confidence threshold for components
            include_validation: Whether to include validation in results
            progress_callback: Optional progress callback function
            
        Returns:
            Tuple of (status_message, results_summary, csv_content, processing_stats)
        """
        # Start performance monitoring for the entire operation
        with self.performance_monitor.monitor_operation(
            "complete_file_processing",
            file_path=file_path,
            confidence_threshold=confidence_threshold,
            include_validation=include_validation
        ) as operation_id:
            
            try:
                start_time = time.time()
                self.logger.info(f"Starting processing of file: {file_path}")
                
                # Get file size for performance tracking
                file_size_mb = 0
                try:
                    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                except:
                    pass
                
                if progress_callback:
                    progress_callback(0.1, "Validating PDF file...")
                
                log_status_update('file_processing', 'validating_pdf', progress=0.1)
                
                # Step 1: Validate and extract PDF pages
                with self.performance_monitor.monitor_operation("pdf_validation", file_size_mb=file_size_mb):
                    if not self.pdf_processor.validate_pdf(file_path):
                        raise ValueError("Invalid PDF file format")
                
                with self.performance_monitor.monitor_operation("pdf_page_extraction", file_size_mb=file_size_mb):
                    pdf_pages = self.pdf_processor.extract_pages(file_path)
                    if not pdf_pages:
                        raise ValueError("No pages found in PDF")
                
                self.logger.info(f"Extracted {len(pdf_pages)} pages from PDF")
                
                if progress_callback:
                    progress_callback(0.2, f"Processing {len(pdf_pages)} pages...")
                
                log_status_update('file_processing', 'extracting_images', progress=0.2)
                
                # Step 2: Process each page
                all_components = []
                page_stats = []
                
                for page_idx, page in enumerate(pdf_pages):
                    page_start_time = time.time()
                    
                    if progress_callback:
                        progress = 0.2 + (page_idx / len(pdf_pages)) * 0.5
                        progress_callback(progress, f"Processing page {page_idx + 1}/{len(pdf_pages)}...")
                    else:
                        progress = 0.2 + (page_idx / len(pdf_pages)) * 0.5
                    
                    log_status_update('page_processing', f'processing_page_{page_idx + 1}', 
                                    progress=progress)
                    
                    # Convert page to image with performance monitoring
                    with self.performance_monitor.monitor_operation("image_conversion", page_number=page_idx + 1):
                        image = self.image_extractor.pdf_page_to_image(page)
                        if image is None:
                            self.logger.warning(f"Failed to convert page {page_idx + 1} to image")
                            continue
                    
                    # Preprocess image with performance monitoring
                    with self.performance_monitor.monitor_operation("image_preprocessing", page_number=page_idx + 1):
                        processed_image = self.image_extractor.preprocess_image(image)
                    
                    # Validate image quality
                    is_valid, quality_metrics = self.image_extractor.validate_image_quality(processed_image)
                    if not is_valid:
                        self.logger.warning(f"Page {page_idx + 1} has quality issues: {quality_metrics}")
                    
                    # Detect steel components with performance monitoring
                    with self.performance_monitor.monitor_operation(
                        "component_detection", 
                        page_number=page_idx + 1,
                        image_size=processed_image.shape if processed_image is not None else None
                    ):
                        components = self.part_extractor.detect_steel_components(
                            processed_image, 
                            page_number=page_idx + 1
                        )
                    
                    # Filter by confidence threshold
                    filtered_components = [
                        comp for comp in components 
                        if comp.confidence >= confidence_threshold
                    ]
                    
                    # Extract dimensions and materials for each component
                    with self.performance_monitor.monitor_operation(
                        "dimension_material_extraction",
                        page_number=page_idx + 1,
                        component_count=len(filtered_components)
                    ):
                        for component in filtered_components:
                            try:
                                # Extract dimensions
                                dimensions = self.dimension_extractor.extract_dimensions(component, processed_image)
                                if dimensions:
                                    component.dimensions = dimensions
                                
                                # Extract materials
                                materials = self.dimension_extractor.extract_material_specs(component, processed_image)
                                if materials:
                                    component.material = materials
                            except Exception as e:
                                self.logger.warning(f"Failed to extract details for component {component.id}: {e}")
                    
                    all_components.extend(filtered_components)
                    
                    page_processing_time = time.time() - page_start_time
                    page_stats.append({
                        'page': page_idx + 1,
                        'components_found': len(filtered_components),
                        'processing_time': page_processing_time,
                        'image_quality': quality_metrics
                    })
                    
                    self.logger.info(f"Page {page_idx + 1}: Found {len(filtered_components)} components "
                                   f"(filtered from {len(components)}) in {page_processing_time:.2f}s")
                
                if progress_callback:
                    progress_callback(0.8, "Validating extracted data...")
                
                log_status_update('file_processing', 'validating_data', progress=0.8)
                
                # Step 3: Validate extracted data with performance monitoring
                validation_results = {}
                inconsistencies = []
                
                if include_validation and all_components:
                    with self.performance_monitor.monitor_operation(
                        "data_validation",
                        component_count=len(all_components)
                    ):
                        for component in all_components:
                            validation_results[component.id] = self.data_validator.validate_dimensions(component)
                        
                        # Check for inconsistencies across all components
                        inconsistencies = self.data_validator.flag_inconsistencies(all_components)
                        
                        # Generate confidence report
                        confidence_report = self.data_validator.generate_confidence_report(all_components)
                else:
                    confidence_report = {'total_components': len(all_components)}
                
                if progress_callback:
                    progress_callback(0.9, "Generating results...")
                
                log_status_update('file_processing', 'generating_results', progress=0.9)
                
                # Step 4: Generate CSV output with performance monitoring
                with self.performance_monitor.monitor_operation(
                    "csv_generation",
                    component_count=len(all_components)
                ):
                    csv_content = self.csv_generator.generate_csv(
                        all_components,
                        validation_results=validation_results if include_validation else None,
                        include_validation=include_validation
                    )
                    
                    # Generate summary statistics
                    summary_stats = self.csv_generator.get_summary_statistics(all_components)
                
                total_processing_time = time.time() - start_time
                
                # Get performance report
                performance_report = self.performance_monitor.get_performance_report()
                
                # Compile processing statistics with performance data
                processing_stats = {
                    'total_processing_time': total_processing_time,
                    'pages_processed': len(pdf_pages),
                    'total_components': len(all_components),
                    'components_by_type': summary_stats['component_types'],
                    'average_confidence': summary_stats['average_confidence'],
                    'validation_issues': len(inconsistencies),
                    'page_statistics': page_stats,
                    'confidence_report': confidence_report,
                    'file_size_mb': file_size_mb,
                    'performance_metrics': {
                        'memory_usage_mb': performance_report['resource_usage'].get('memory_rss_mb', 0),
                        'cpu_percent': performance_report['resource_usage'].get('cpu_percent', 0),
                        'processing_rate_pages_per_second': len(pdf_pages) / total_processing_time if total_processing_time > 0 else 0,
                        'processing_rate_components_per_second': len(all_components) / total_processing_time if total_processing_time > 0 else 0,
                        'recommendations': performance_report.get('recommendations', [])
                    }
                }
                
                # Store results for download
                self.current_results = {
                    'components': all_components,
                    'csv_content': csv_content,
                    'processing_stats': processing_stats,
                    'validation_results': validation_results,
                    'inconsistencies': inconsistencies
                }
                
                if progress_callback:
                    progress_callback(1.0, "Processing complete!")
                
                log_status_update('file_processing', 'completed', progress=1.0)
                
                # Generate status message
                status_message = f"✅ Processing completed successfully!\n"
                status_message += f"📄 Processed {len(pdf_pages)} pages in {total_processing_time:.2f} seconds\n"
                status_message += f"🔧 Found {len(all_components)} steel components\n"
                status_message += f"⚡ Processing rate: {len(pdf_pages) / total_processing_time:.1f} pages/sec\n"
                status_message += f"💾 Memory usage: {performance_report['resource_usage'].get('memory_rss_mb', 0):.1f} MB\n"
                
                if include_validation:
                    valid_components = sum(1 for result in validation_results.values() if result.is_valid)
                    status_message += f"✓ {valid_components}/{len(all_components)} components passed validation\n"
                    if inconsistencies:
                        status_message += f"⚠️ {len(inconsistencies)} data quality issues detected\n"
                
                # Add performance recommendations if any
                if performance_report.get('recommendations'):
                    status_message += f"💡 {len(performance_report['recommendations'])} performance recommendations available\n"
                
                # Generate results summary
                results_summary = self._generate_results_summary(all_components, processing_stats)
                
                self.logger.info(f"Processing completed: {len(all_components)} components found in {total_processing_time:.2f}s")
                
                return status_message, results_summary, csv_content, processing_stats
                
            except Exception as e:
                error_message = f"❌ Processing failed: {str(e)}"
                self.logger.error(f"File processing failed: {e}", exc_info=True)
                
                # Log error statistics
                error_manager = get_error_manager()
                error_stats = error_manager.get_error_statistics()
                
                return error_message, f"Error details: {str(e)}", "", {'error': str(e), 'error_stats': error_stats}
    
    def _generate_results_summary(self, components: List, stats: Dict[str, Any]) -> str:
        """Generate a formatted summary of processing results."""
        if not components:
            return "No components detected in the uploaded file."
        
        summary = f"## Processing Results Summary\n\n"
        summary += f"**Total Components Found:** {len(components)}\n\n"
        
        # Component breakdown by type
        summary += "### Components by Type:\n"
        for comp_type, count in stats['components_by_type'].items():
            summary += f"- **{comp_type.title()}:** {count}\n"
        
        summary += f"\n**Average Confidence:** {stats['average_confidence']:.1%}\n"
        summary += f"**Processing Time:** {stats['total_processing_time']:.2f} seconds\n"
        summary += f"**Pages Processed:** {stats['pages_processed']}\n"
        
        if 'validation_issues' in stats and stats['validation_issues'] > 0:
            summary += f"\n⚠️ **Data Quality Issues:** {stats['validation_issues']} issues detected\n"
        
        # Page-by-page breakdown
        if 'page_statistics' in stats:
            summary += "\n### Page-by-Page Results:\n"
            for page_stat in stats['page_statistics']:
                summary += f"- **Page {page_stat['page']}:** {page_stat['components_found']} components "
                summary += f"({page_stat['processing_time']:.2f}s)\n"
        
        return summary
    
    def get_supported_component_types(self) -> List[str]:
        """Get list of supported component types."""
        return self.part_extractor.get_supported_types()
    
    def get_component_type_config(self, component_type: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a component type."""
        config = self.part_extractor.get_detector_config(component_type)
        if config:
            return {
                'name': config.name,
                'display_name': config.display_name,
                'description': config.description,
                'enabled': config.enabled,
                'min_size': config.detection_params.min_size,
                'confidence_threshold': config.detection_params.confidence_threshold,
                'aspect_ratio_range': config.detection_params.aspect_ratio_range,
                'csv_columns': config.csv_columns
            }
        return None
    
    def toggle_component_type(self, component_type: str, enabled: bool) -> str:
        """Enable or disable a component type."""
        try:
            if enabled:
                success = self.part_extractor.enable_component_type(component_type)
                action = "enabled"
            else:
                success = self.part_extractor.disable_component_type(component_type)
                action = "disabled"
            
            if success:
                self.logger.info(f"Component type '{component_type}' {action}")
                return f"✅ Component type '{component_type}' {action} successfully"
            else:
                return f"❌ Failed to {action.replace('d', '')} component type '{component_type}'"
        except Exception as e:
            self.logger.error(f"Failed to toggle component type {component_type}: {e}")
            return f"❌ Error: {str(e)}"

    def get_performance_report(self) -> Dict[str, Any]:
        """Get current performance report."""
        try:
            return self.performance_monitor.get_performance_report()
        except Exception as e:
            self.logger.error(f"Failed to get performance report: {e}")
            return {"error": str(e)}
    
    def get_performance_recommendations(self) -> str:
        """Get performance optimization recommendations."""
        try:
            report = self.performance_monitor.get_performance_report()
            recommendations = report.get('recommendations', [])
            
            if not recommendations:
                return "No performance recommendations at this time. System is operating within normal parameters."
            
            formatted_recommendations = []
            for i, rec in enumerate(recommendations, 1):
                formatted_recommendations.append(f"{i}. {rec}")
            
            return "\n".join(formatted_recommendations)
            
        except Exception as e:
            self.logger.error(f"Failed to get performance recommendations: {e}")
            return f"Error retrieving recommendations: {str(e)}"
    
    def get_performance_history(self) -> List[List[Any]]:
        """Get performance history for display in dataframe."""
        try:
            report = self.performance_monitor.get_performance_report()
            recent_ops = report.get('recent_operations', [])
            
            history = []
            for op in recent_ops:
                history.append([
                    op.get('operation', 'Unknown'),
                    f"{op.get('duration', 0):.2f}",
                    f"{op.get('memory_delta_mb', 0):.1f}",
                    "Success" if op.get('success', False) else "Failed",
                    op.get('timestamp', 'Unknown')
                ])
            
            return history
            
        except Exception as e:
            self.logger.error(f"Failed to get performance history: {e}")
            return [["Error", "N/A", "N/A", "Error", str(e)]]
    
    def reset_performance_metrics(self) -> str:
        """Reset performance metrics."""
        try:
            self.performance_monitor.reset_metrics()
            return "✅ Performance metrics have been reset successfully."
        except Exception as e:
            self.logger.error(f"Failed to reset performance metrics: {e}")
            return f"❌ Failed to reset metrics: {str(e)}"
    
    def export_performance_report(self) -> Optional[str]:
        """Export performance report to file."""
        try:
            import tempfile
            import json
            from datetime import datetime
            
            # Generate comprehensive report
            report = self.performance_monitor.get_performance_report()
            
            # Add timestamp and system info
            report['export_timestamp'] = datetime.now().isoformat()
            report['system_info'] = {
                'configuration': self.get_configuration_info(),
                'supported_components': self.get_supported_component_types()
            }
            
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(
                mode='w', 
                suffix='.json', 
                prefix='steel_parser_performance_', 
                delete=False
            )
            
            json.dump(report, temp_file, indent=2, default=str)
            temp_file.close()
            
            self.logger.info(f"Performance report exported to {temp_file.name}")
            return temp_file.name
            
        except Exception as e:
            self.logger.error(f"Failed to export performance report: {e}")
            return None

    def handle_download(self, download_type: str) -> Optional[str]:
        """
        Handle file downloads.
        
        Args:
            download_type: Type of download ('csv', 'report', 'logs')
            
        Returns:
            Path to downloadable file or None
        """
        try:
            if not self.current_results:
                return None
            
            if download_type == 'csv':
                # Create temporary CSV file
                temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
                temp_file.write(self.current_results['csv_content'])
                temp_file.close()
                return temp_file.name
            
            elif download_type == 'report':
                # Generate detailed processing report
                report_content = self._generate_detailed_report()
                temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                temp_file.write(report_content)
                temp_file.close()
                return temp_file.name
            
            elif download_type == 'logs':
                # Get log files information
                log_info = self.logger_config.get_log_files_info()
                if 'processing.log' in log_info and log_info['processing.log']['exists']:
                    return log_info['processing.log']['path']
            
            return None
            
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return None
    
    def _generate_detailed_report(self) -> str:
        """Generate a detailed processing report."""
        if not self.current_results:
            return "No processing results available."
        
        report = "# Steel Drawing Parser - Detailed Processing Report\n\n"
        report += f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        stats = self.current_results.get('processing_stats')
        if not stats:
            return "No processing statistics available."
        
        report += "## Processing Summary\n"
        report += f"- Total Processing Time: {stats.get('total_processing_time', 0):.2f} seconds\n"
        report += f"- Pages Processed: {stats.get('pages_processed', 0)}\n"
        report += f"- Components Found: {stats.get('total_components', 0)}\n"
        report += f"- Average Confidence: {stats.get('average_confidence', 0):.1%}\n\n"
        
        # Component details
        report += "## Component Breakdown\n"
        components_by_type = stats.get('components_by_type', {})
        for comp_type, count in components_by_type.items():
            report += f"- {comp_type.title()}: {count}\n"
        report += "\n"
        
        # Validation results
        if 'validation_results' in self.current_results:
            validation_results = self.current_results['validation_results']
            if validation_results:
                valid_count = sum(1 for result in validation_results.values() if result.is_valid)
                report += "## Validation Results\n"
                report += f"- Valid Components: {valid_count}/{len(validation_results)}\n"
                report += f"- Validation Issues: {stats.get('validation_issues', 0)}\n\n"
        
        # Inconsistencies
        if 'inconsistencies' in self.current_results and self.current_results['inconsistencies']:
            report += "## Data Quality Issues\n"
            for issue in self.current_results['inconsistencies'][:10]:  # Limit to first 10
                report += f"- {issue.issue_type}: {issue.description}\n"
            if len(self.current_results['inconsistencies']) > 10:
                report += f"... and {len(self.current_results['inconsistencies']) - 10} more issues\n"
            report += "\n"
        
        # Page statistics
        page_statistics = stats.get('page_statistics', [])
        if page_statistics:
            report += "## Page-by-Page Statistics\n"
            for page_stat in page_statistics:
                report += f"### Page {page_stat['page']}\n"
                report += f"- Components Found: {page_stat['components_found']}\n"
                report += f"- Processing Time: {page_stat['processing_time']:.2f}s\n"
                if 'image_quality' in page_stat:
                    report += f"- Image Quality: {page_stat['image_quality']}\n"
                report += "\n"
        
        return report
    
    def create_interface(self) -> gr.Blocks:
        """Create and configure the Gradio interface."""
        
        # Custom CSS for better styling
        custom_css = """
        .gradio-container {
            max-width: 1200px !important;
        }
        .status-box {
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 16px;
            margin: 8px 0;
        }
        .success-status {
            background-color: #f0f9ff;
            border-color: #0ea5e9;
        }
        .error-status {
            background-color: #fef2f2;
            border-color: #ef4444;
        }
        """
        
        with gr.Blocks(
            title="Steel Drawing Parser",
            css=custom_css
        ) as interface:
            
            # Header
            gr.Markdown("""
            # 🏗️ Steel Drawing Parser
            
            Upload PDF files containing steel detailing drawings to automatically extract component information.
            The system will identify beams, columns, plates, bolts, and other steel components with their dimensions and materials.
            """)
            
            # Main processing interface
            with gr.Row():
                with gr.Column(scale=1):
                    # Input section
                    gr.Markdown("## 📁 Upload & Settings")
                    
                    file_input = gr.File(
                        label="Upload PDF File",
                        file_types=[".pdf"],
                        type="filepath"
                    )
                    
                    confidence_threshold = gr.Slider(
                        minimum=0.1,
                        maximum=1.0,
                        value=0.5,
                        step=0.1,
                        label="Confidence Threshold",
                        info="Minimum confidence for component detection"
                    )
                    
                    include_validation = gr.Checkbox(
                        value=True,
                        label="Include Validation",
                        info="Validate extracted data for quality issues"
                    )
                    
                    process_btn = gr.Button(
                        "🚀 Process PDF",
                        variant="primary",
                        size="lg"
                    )
                
                with gr.Column(scale=2):
                    # Results section
                    gr.Markdown("## 📊 Results")
                    
                    status_output = gr.Textbox(
                        label="Processing Status",
                        lines=6,
                        interactive=False
                    )
                    
                    results_summary = gr.Markdown(
                        value="Upload a PDF file to see results here.",
                        label="Results Summary"
                    )
            
            # Download section
            gr.Markdown("## 💾 Downloads")
            
            with gr.Row():
                csv_download = gr.File(
                    label="📄 CSV Results",
                    interactive=False
                )
                
                report_download = gr.File(
                    label="📋 Detailed Report",
                    interactive=False
                )
            
            # Advanced results section (collapsible)
            with gr.Accordion("🔍 Advanced Results", open=False):
                
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Processing Statistics")
                        stats_json = gr.JSON(
                            label="Processing Stats",
                            value={}
                        )
                    
                    with gr.Column():
                        gr.Markdown("### CSV Preview")
                        csv_preview = gr.Dataframe(
                            label="CSV Data Preview"
                        )
            
            # Configuration section
            with gr.Accordion("⚙️ Configuration", open=False):
                gr.Markdown("### System Configuration")
                
                config_info = gr.JSON(
                    label="Current Configuration",
                    value=self.get_configuration_info()
                )
                
                refresh_config_btn = gr.Button(
                    "🔄 Refresh Configuration",
                    size="sm"
                )
            
            # Performance monitoring section
            with gr.Accordion("📊 Performance Monitor", open=False):
                gr.Markdown("### Performance Metrics")
                
                performance_metrics = gr.JSON(
                    label="Performance Report",
                    value={}
                )
                
                with gr.Row():
                    refresh_performance_btn = gr.Button(
                        "🔄 Refresh Performance Data",
                        size="sm"
                    )
                    
                    reset_metrics_btn = gr.Button(
                        "🗑️ Reset Metrics",
                        variant="secondary",
                        size="sm"
                    )
                
                performance_recommendations = gr.Textbox(
                    label="Optimization Recommendations",
                    lines=4,
                    interactive=False,
                    placeholder="Performance recommendations will appear here after processing operations..."
                )
            
            # Event handlers for main processing
            def process_with_progress(file_path, confidence_thresh, include_val, progress=gr.Progress()):
                """Process file with progress updates."""
                if not file_path:
                    return "Please upload a PDF file first.", "No file uploaded.", "", {}, None, None, None
                
                def progress_callback(value, description):
                    progress(value, desc=description)
                
                try:
                    status, summary, csv_content, stats = self.process_file_upload(
                        file_path, confidence_thresh, include_val, progress_callback
                    )
                    
                    # Prepare downloads
                    csv_file = None
                    report_file = None
                    csv_df = None
                    
                    if csv_content:
                        # Create CSV file for download
                        csv_temp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
                        csv_temp.write(csv_content)
                        csv_temp.close()
                        csv_file = csv_temp.name
                        
                        # Create DataFrame for preview
                        try:
                            import io
                            csv_df = pd.read_csv(io.StringIO(csv_content)).head(10)
                        except Exception:
                            csv_df = None
                        
                        # Create detailed report
                        report_content = self._generate_detailed_report()
                        report_temp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                        report_temp.write(report_content)
                        report_temp.close()
                        report_file = report_temp.name
                    
                    return status, summary, csv_content, stats, csv_file, report_file, csv_df
                    
                except Exception as e:
                    error_msg = f"Processing failed: {str(e)}"
                    return error_msg, f"Error: {str(e)}", "", {'error': str(e)}, None, None, None
            
            def refresh_configuration():
                """Refresh configuration display."""
                return self.get_configuration_info()
            
            def refresh_performance_data():
                """Refresh performance metrics display."""
                return self.get_performance_report()
            
            def refresh_performance_recommendations():
                """Refresh performance recommendations."""
                return self.get_performance_recommendations()
            
            def reset_performance_metrics():
                """Reset performance metrics."""
                return self.reset_performance_metrics()
            
            # Connect the process button
            process_btn.click(
                fn=process_with_progress,
                inputs=[file_input, confidence_threshold, include_validation],
                outputs=[
                    status_output,
                    results_summary,
                    gr.Textbox(visible=False),  # Hidden CSV content
                    stats_json,
                    csv_download,
                    report_download,
                    csv_preview
                ]
            )
            
            # Connect configuration events
            refresh_config_btn.click(
                fn=refresh_configuration,
                outputs=[config_info]
            )
            
            # Connect performance monitoring events
            refresh_performance_btn.click(
                fn=refresh_performance_data,
                outputs=[performance_metrics]
            )
            
            refresh_performance_btn.click(
                fn=refresh_performance_recommendations,
                outputs=[performance_recommendations]
            )
            
            reset_metrics_btn.click(
                fn=reset_performance_metrics,
                outputs=[performance_recommendations]  # Show result in recommendations area
            )
            
            # Footer
            gr.Markdown("""
            ---
            
            ### 📖 How to Use
            1. **Upload** a PDF file containing steel detailing drawings
            2. **Adjust** confidence threshold and validation settings as needed
            3. **Click** "Process PDF" to analyze the drawings
            4. **Review** the results and download CSV data or detailed reports
            
            ### 🔧 Supported Components
            - **Beams** (W-shapes, I-beams)
            - **Columns** (HSS, W-shapes)
            - **Plates** (connection plates, gussets)
            - **Bolts** (various sizes and grades)
            - **Welds** (fillet, groove)
            
            ### 📊 Output Information
            - Component dimensions and locations
            - Material specifications and grades
            - Quantity counts and groupings
            - Data validation and quality checks
            """)
        
        return interface
    
    def launch(self, **kwargs):
        """Launch the Gradio interface."""
        interface = self.create_interface()
        
        # Default launch parameters
        launch_params = {
            'server_name': '0.0.0.0',
            'server_port': 7860,
            'share': False,
            'debug': False,
            'show_error': True
        }
        
        # Override with user parameters
        launch_params.update(kwargs)
        
        self.logger.info(f"Launching Steel Drawing Parser interface on {launch_params['server_name']}:{launch_params['server_port']}")
        
        return interface.launch(**launch_params)


def create_interface(config: Optional[SystemConfig] = None) -> SteelDrawingParserInterface:
    """Create a new interface instance."""
    return SteelDrawingParserInterface(config)


def launch_interface(config: Optional[SystemConfig] = None, **kwargs):
    """Launch the steel drawing parser interface."""
    interface = create_interface(config)
    return interface.launch(**kwargs)


if __name__ == "__main__":
    # Launch the interface when run directly
    launch_interface(share=True, debug=True)