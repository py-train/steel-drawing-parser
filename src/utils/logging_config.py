"""Comprehensive logging configuration for the steel drawing parser."""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from typing import Dict, Optional, Any
import json
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'component_id'):
            log_entry['component_id'] = record.component_id
        if hasattr(record, 'processing_time'):
            log_entry['processing_time'] = record.processing_time
        if hasattr(record, 'file_path'):
            log_entry['file_path'] = record.file_path
        if hasattr(record, 'operation'):
            log_entry['operation'] = record.operation
        
        return json.dumps(log_entry)


class PerformanceFormatter(logging.Formatter):
    """Custom formatter for performance logs."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format performance log record."""
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # Extract performance metrics
        operation = getattr(record, 'operation', 'unknown')
        processing_time = getattr(record, 'processing_time', 0.0)
        memory_usage = getattr(record, 'memory_usage', 0)
        components_processed = getattr(record, 'components_processed', 0)
        
        return f"{timestamp} | {operation:20} | {processing_time:8.3f}s | {memory_usage:8}MB | {components_processed:5} components | {record.getMessage()}"


class SteelParserLogger:
    """Centralized logging configuration for the steel drawing parser."""
    
    def __init__(self, log_dir: str = "logs", log_level: str = "INFO"):
        """
        Initialize logging configuration.
        
        Args:
            log_dir: Directory for log files
            log_level: Default logging level
        """
        self.log_dir = Path(log_dir)
        self.log_level = getattr(logging, log_level.upper())
        self.loggers: Dict[str, logging.Logger] = {}
        
        # Ensure log directory exists
        self.log_dir.mkdir(exist_ok=True)
        
        # Configure logging
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up comprehensive logging infrastructure."""
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # Console handler for development
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # Set up specialized loggers
        self._setup_error_logging()
        self._setup_processing_logging()
        self._setup_performance_logging()
    
    def _setup_error_logging(self):
        """Set up error-specific logging."""
        error_logger = logging.getLogger('steel_parser.errors')
        error_logger.setLevel(logging.WARNING)
        
        # Error file handler with rotation
        error_file = self.log_dir / 'errors.log'
        error_handler = logging.handlers.RotatingFileHandler(
            error_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        error_handler.setLevel(logging.WARNING)
        
        # JSON formatter for structured error logs
        error_formatter = JSONFormatter()
        error_handler.setFormatter(error_formatter)
        
        error_logger.addHandler(error_handler)
        error_logger.propagate = False  # Don't propagate to root logger
        
        self.loggers['errors'] = error_logger
    
    def _setup_processing_logging(self):
        """Set up processing-specific logging."""
        processing_logger = logging.getLogger('steel_parser.processing')
        processing_logger.setLevel(logging.INFO)
        
        # Processing file handler with rotation
        processing_file = self.log_dir / 'processing.log'
        processing_handler = logging.handlers.RotatingFileHandler(
            processing_file,
            maxBytes=50*1024*1024,  # 50MB
            backupCount=10
        )
        processing_handler.setLevel(logging.INFO)
        
        # Standard formatter for processing logs
        processing_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        processing_handler.setFormatter(processing_formatter)
        
        processing_logger.addHandler(processing_handler)
        processing_logger.propagate = False
        
        self.loggers['processing'] = processing_logger
    
    def _setup_performance_logging(self):
        """Set up performance-specific logging."""
        performance_logger = logging.getLogger('steel_parser.performance')
        performance_logger.setLevel(logging.INFO)
        
        # Performance file handler with rotation
        performance_file = self.log_dir / 'performance.log'
        performance_handler = logging.handlers.RotatingFileHandler(
            performance_file,
            maxBytes=20*1024*1024,  # 20MB
            backupCount=5
        )
        performance_handler.setLevel(logging.INFO)
        
        # Custom performance formatter
        performance_formatter = PerformanceFormatter()
        performance_handler.setFormatter(performance_formatter)
        
        performance_logger.addHandler(performance_handler)
        performance_logger.propagate = False
        
        self.loggers['performance'] = performance_logger
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Get a logger instance.
        
        Args:
            name: Logger name
            
        Returns:
            Logger instance
        """
        return logging.getLogger(name)
    
    def log_error(self, logger_name: str, message: str, 
                  exception: Optional[Exception] = None,
                  **kwargs):
        """
        Log an error with context information.
        
        Args:
            logger_name: Name of the logger
            message: Error message
            exception: Optional exception object
            **kwargs: Additional context information
        """
        # Use the error logger specifically
        logger = self.loggers['errors']
        
        # Create log record with extra context
        extra = kwargs.copy()
        
        if exception:
            logger.error(message, exc_info=exception, extra=extra)
        else:
            logger.error(message, extra=extra)
    
    def log_processing_step(self, operation: str, message: str,
                          processing_time: Optional[float] = None,
                          components_count: Optional[int] = None,
                          **kwargs):
        """
        Log a processing step with performance metrics.
        
        Args:
            operation: Name of the operation
            message: Log message
            processing_time: Time taken for the operation
            components_count: Number of components processed
            **kwargs: Additional context information
        """
        logger = self.loggers['processing']
        
        extra = {
            'operation': operation,
            **kwargs
        }
        
        if processing_time is not None:
            extra['processing_time'] = processing_time
        if components_count is not None:
            extra['components_processed'] = components_count
        
        logger.info(message, extra=extra)
    
    def log_performance(self, operation: str, processing_time: float,
                       memory_usage: Optional[int] = None,
                       components_processed: Optional[int] = None,
                       **kwargs):
        """
        Log performance metrics.
        
        Args:
            operation: Name of the operation
            processing_time: Time taken in seconds
            memory_usage: Memory usage in MB
            components_processed: Number of components processed
            **kwargs: Additional metrics
        """
        logger = self.loggers['performance']
        
        extra = {
            'operation': operation,
            'processing_time': processing_time,
            'memory_usage': memory_usage or 0,
            'components_processed': components_processed or 0,
            **kwargs
        }
        
        message = f"Operation completed: {operation}"
        logger.info(message, extra=extra)
    
    def log_summary_statistics(self, operation: str, statistics: Dict[str, Any]):
        """
        Log summary statistics for completed operations.
        
        Args:
            operation: Name of the operation
            statistics: Dictionary of statistics
        """
        logger = self.loggers['processing']
        
        message = f"Summary for {operation}: {json.dumps(statistics, indent=2)}"
        logger.info(message, extra={'operation': operation, 'statistics': statistics})
    
    def configure_module_logger(self, module_name: str, 
                              level: Optional[str] = None) -> logging.Logger:
        """
        Configure a logger for a specific module.
        
        Args:
            module_name: Name of the module
            level: Optional logging level override
            
        Returns:
            Configured logger
        """
        logger = logging.getLogger(module_name)
        
        if level:
            logger.setLevel(getattr(logging, level.upper()))
        
        return logger
    
    def get_log_files_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about log files.
        
        Returns:
            Dictionary with log file information
        """
        log_files = {}
        
        for log_file in self.log_dir.glob('*.log'):
            try:
                stat = log_file.stat()
                log_files[log_file.name] = {
                    'path': str(log_file),
                    'size_mb': round(stat.st_size / (1024 * 1024), 2),
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'exists': True
                }
            except Exception as e:
                log_files[log_file.name] = {
                    'path': str(log_file),
                    'error': str(e),
                    'exists': False
                }
        
        return log_files
    
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """
        Clean up old log files.
        
        Args:
            days_to_keep: Number of days to keep log files
        """
        import time
        
        cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
        
        for log_file in self.log_dir.glob('*.log*'):
            try:
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    print(f"Deleted old log file: {log_file}")
            except Exception as e:
                print(f"Failed to delete {log_file}: {e}")


# Global logger instance
_logger_instance: Optional[SteelParserLogger] = None


def get_logger_instance(log_dir: str = "logs", log_level: str = "INFO") -> SteelParserLogger:
    """
    Get the global logger instance.
    
    Args:
        log_dir: Directory for log files
        log_level: Default logging level
        
    Returns:
        SteelParserLogger instance
    """
    global _logger_instance
    
    if _logger_instance is None:
        _logger_instance = SteelParserLogger(log_dir, log_level)
    
    return _logger_instance


def setup_logging(log_dir: str = "logs", log_level: str = "INFO") -> SteelParserLogger:
    """
    Set up logging for the steel drawing parser.
    
    Args:
        log_dir: Directory for log files
        log_level: Default logging level
        
    Returns:
        SteelParserLogger instance
    """
    return get_logger_instance(log_dir, log_level)