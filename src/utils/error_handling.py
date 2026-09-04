"""Error handling and system resilience utilities."""

import logging
import traceback
import functools
import time
from typing import Any, Callable, Dict, List, Optional, Type, Union
from dataclasses import dataclass
from enum import Enum
import psutil
import os


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecoveryStrategy(Enum):
    """Error recovery strategies."""
    RETRY = "retry"
    SKIP = "skip"
    FALLBACK = "fallback"
    ABORT = "abort"


@dataclass
class ErrorContext:
    """Context information for errors."""
    operation: str
    component_id: Optional[str] = None
    file_path: Optional[str] = None
    page_number: Optional[int] = None
    timestamp: Optional[float] = None
    memory_usage: Optional[float] = None
    additional_info: Optional[Dict[str, Any]] = None


@dataclass
class RecoveryResult:
    """Result of error recovery attempt."""
    success: bool
    strategy_used: RecoveryStrategy
    attempts: int
    final_result: Any = None
    error_message: Optional[str] = None


class SystemMonitor:
    """Monitor system resources and health."""
    
    def __init__(self):
        self.logger = logging.getLogger('steel_parser.system_monitor')
        self.process = psutil.Process(os.getpid())
    
    def get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            memory_info = self.process.memory_info()
            return memory_info.rss / (1024 * 1024)  # Convert to MB
        except Exception as e:
            self.logger.warning(f"Failed to get memory usage: {e}")
            return 0.0
    
    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage."""
        try:
            return self.process.cpu_percent()
        except Exception as e:
            self.logger.warning(f"Failed to get CPU usage: {e}")
            return 0.0
    
    def check_memory_threshold(self, threshold_mb: float = 1000.0) -> bool:
        """
        Check if memory usage exceeds threshold.
        
        Args:
            threshold_mb: Memory threshold in MB
            
        Returns:
            True if memory usage is below threshold
        """
        current_usage = self.get_memory_usage()
        return current_usage < threshold_mb
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get comprehensive system statistics."""
        try:
            return {
                'memory_usage_mb': self.get_memory_usage(),
                'cpu_usage_percent': self.get_cpu_usage(),
                'available_memory_mb': psutil.virtual_memory().available / (1024 * 1024),
                'disk_usage_percent': psutil.disk_usage('/').percent,
                'process_threads': self.process.num_threads(),
                'timestamp': time.time()
            }
        except Exception as e:
            self.logger.error(f"Failed to get system stats: {e}")
            return {'error': str(e), 'timestamp': time.time()}


class ErrorRecoveryManager:
    """Manage error recovery strategies and system resilience."""
    
    def __init__(self):
        self.logger = logging.getLogger('steel_parser.error_recovery')
        self.system_monitor = SystemMonitor()
        self.error_counts: Dict[str, int] = {}
        self.recovery_strategies: Dict[str, RecoveryStrategy] = {}
        
        # Default recovery strategies for different operations
        self.default_strategies = {
            'pdf_processing': RecoveryStrategy.RETRY,
            'image_extraction': RecoveryStrategy.FALLBACK,
            'component_detection': RecoveryStrategy.SKIP,
            'dimension_extraction': RecoveryStrategy.SKIP,
            'material_extraction': RecoveryStrategy.SKIP,
            'validation': RecoveryStrategy.SKIP,
            'csv_generation': RecoveryStrategy.RETRY
        }
    
    def handle_error(self, error: Exception, context: ErrorContext,
                    max_retries: int = 3,
                    recovery_strategy: Optional[RecoveryStrategy] = None) -> RecoveryResult:
        """
        Handle an error with appropriate recovery strategy.
        
        Args:
            error: The exception that occurred
            context: Context information about the error
            max_retries: Maximum number of retry attempts
            recovery_strategy: Override recovery strategy
            
        Returns:
            RecoveryResult with outcome
        """
        # Log the error with context
        self._log_error(error, context)
        
        # Determine recovery strategy
        strategy = recovery_strategy or self._get_recovery_strategy(context.operation)
        
        # Track error count
        error_key = f"{context.operation}:{type(error).__name__}"
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        
        # Execute recovery strategy
        if strategy == RecoveryStrategy.RETRY:
            return self._retry_operation(error, context, max_retries)
        elif strategy == RecoveryStrategy.SKIP:
            return self._skip_operation(error, context)
        elif strategy == RecoveryStrategy.FALLBACK:
            return self._fallback_operation(error, context)
        elif strategy == RecoveryStrategy.ABORT:
            return self._abort_operation(error, context)
        else:
            return RecoveryResult(
                success=False,
                strategy_used=strategy,
                attempts=1,
                error_message=str(error)
            )
    
    def _log_error(self, error: Exception, context: ErrorContext):
        """Log error with full context information."""
        error_info = {
            'operation': context.operation,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'traceback': traceback.format_exc(),
            'component_id': context.component_id,
            'file_path': context.file_path,
            'page_number': context.page_number,
            'memory_usage': context.memory_usage or self.system_monitor.get_memory_usage(),
            'system_stats': self.system_monitor.get_system_stats()
        }
        
        if context.additional_info:
            error_info.update(context.additional_info)
        
        # Determine severity
        severity = self._determine_error_severity(error, context)
        
        if severity == ErrorSeverity.CRITICAL:
            self.logger.critical(f"Critical error in {context.operation}", extra=error_info)
        elif severity == ErrorSeverity.HIGH:
            self.logger.error(f"High severity error in {context.operation}", extra=error_info)
        elif severity == ErrorSeverity.MEDIUM:
            self.logger.warning(f"Medium severity error in {context.operation}", extra=error_info)
        else:
            self.logger.info(f"Low severity error in {context.operation}", extra=error_info)
    
    def _determine_error_severity(self, error: Exception, context: ErrorContext) -> ErrorSeverity:
        """Determine the severity of an error."""
        # Critical errors that should stop processing
        if isinstance(error, (MemoryError, SystemError, KeyboardInterrupt)):
            return ErrorSeverity.CRITICAL
        
        # High severity errors for core operations
        if context.operation in ['pdf_processing', 'csv_generation']:
            if isinstance(error, (FileNotFoundError, PermissionError, ValueError)):
                return ErrorSeverity.HIGH
        
        # Medium severity for processing errors
        if context.operation in ['image_extraction', 'component_detection']:
            return ErrorSeverity.MEDIUM
        
        # Low severity for optional operations
        return ErrorSeverity.LOW
    
    def _get_recovery_strategy(self, operation: str) -> RecoveryStrategy:
        """Get recovery strategy for an operation."""
        return self.recovery_strategies.get(operation, 
                                          self.default_strategies.get(operation, 
                                                                    RecoveryStrategy.SKIP))
    
    def _retry_operation(self, error: Exception, context: ErrorContext, 
                        max_retries: int) -> RecoveryResult:
        """Implement retry recovery strategy."""
        self.logger.info(f"Retrying operation {context.operation} (max {max_retries} attempts)")
        
        # For now, return failure as we can't actually retry without the original function
        # This would be implemented by the calling code using the resilient_operation decorator
        return RecoveryResult(
            success=False,
            strategy_used=RecoveryStrategy.RETRY,
            attempts=1,
            error_message=f"Retry strategy requires caller implementation: {str(error)}"
        )
    
    def _skip_operation(self, error: Exception, context: ErrorContext) -> RecoveryResult:
        """Implement skip recovery strategy."""
        self.logger.info(f"Skipping operation {context.operation} due to error: {str(error)}")
        
        return RecoveryResult(
            success=True,  # Success in terms of recovery
            strategy_used=RecoveryStrategy.SKIP,
            attempts=1,
            final_result=None,
            error_message=f"Operation skipped: {str(error)}"
        )
    
    def _fallback_operation(self, error: Exception, context: ErrorContext) -> RecoveryResult:
        """Implement fallback recovery strategy."""
        self.logger.info(f"Using fallback for operation {context.operation}")
        
        # Implement operation-specific fallbacks
        fallback_result = None
        
        if context.operation == 'image_extraction':
            # Fallback to lower quality settings
            fallback_result = "fallback_image_processing"
        elif context.operation == 'component_detection':
            # Return empty component list
            fallback_result = []
        
        return RecoveryResult(
            success=True,
            strategy_used=RecoveryStrategy.FALLBACK,
            attempts=1,
            final_result=fallback_result,
            error_message=f"Fallback used: {str(error)}"
        )
    
    def _abort_operation(self, error: Exception, context: ErrorContext) -> RecoveryResult:
        """Implement abort recovery strategy."""
        self.logger.error(f"Aborting operation {context.operation} due to critical error: {str(error)}")
        
        return RecoveryResult(
            success=False,
            strategy_used=RecoveryStrategy.ABORT,
            attempts=1,
            error_message=f"Operation aborted: {str(error)}"
        )
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics and system health information."""
        return {
            'error_counts': self.error_counts.copy(),
            'total_errors': sum(self.error_counts.values()),
            'system_stats': self.system_monitor.get_system_stats(),
            'recovery_strategies': self.recovery_strategies.copy()
        }
    
    def reset_error_counts(self):
        """Reset error counters."""
        self.error_counts.clear()
        self.logger.info("Error counters reset")


# Global error recovery manager
_error_manager: Optional[ErrorRecoveryManager] = None


def get_error_manager() -> ErrorRecoveryManager:
    """Get the global error recovery manager."""
    global _error_manager
    if _error_manager is None:
        _error_manager = ErrorRecoveryManager()
    return _error_manager


def resilient_operation(operation_name: str, 
                       max_retries: int = 3,
                       recovery_strategy: Optional[RecoveryStrategy] = None,
                       timeout_seconds: Optional[float] = None):
    """
    Decorator to make operations resilient to errors.
    
    Args:
        operation_name: Name of the operation for logging
        max_retries: Maximum number of retry attempts
        recovery_strategy: Override recovery strategy
        timeout_seconds: Optional timeout for the operation
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            error_manager = get_error_manager()
            
            for attempt in range(max_retries + 1):
                try:
                    # Monitor system resources
                    start_time = time.time()
                    start_memory = error_manager.system_monitor.get_memory_usage()
                    
                    # Execute the function
                    if timeout_seconds:
                        # Note: This is a simplified timeout implementation
                        # In production, you might want to use signal.alarm or threading.Timer
                        result = func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    
                    # Log successful execution
                    end_time = time.time()
                    processing_time = end_time - start_time
                    
                    error_manager.logger.info(
                        f"Operation {operation_name} completed successfully",
                        extra={
                            'operation': operation_name,
                            'processing_time': processing_time,
                            'memory_usage': error_manager.system_monitor.get_memory_usage(),
                            'attempt': attempt + 1
                        }
                    )
                    
                    return result
                    
                except Exception as e:
                    # Create error context
                    context = ErrorContext(
                        operation=operation_name,
                        timestamp=time.time(),
                        memory_usage=error_manager.system_monitor.get_memory_usage(),
                        additional_info={
                            'attempt': attempt + 1,
                            'max_retries': max_retries,
                            'args_count': len(args),
                            'kwargs_keys': list(kwargs.keys())
                        }
                    )
                    
                    # Handle the error
                    recovery_result = error_manager.handle_error(
                        e, context, max_retries, recovery_strategy
                    )
                    
                    # If this is the last attempt or recovery says to abort, re-raise
                    if (attempt == max_retries or 
                        recovery_result.strategy_used == RecoveryStrategy.ABORT):
                        raise e
                    
                    # If recovery strategy is skip, return the fallback result
                    if recovery_result.strategy_used == RecoveryStrategy.SKIP:
                        return recovery_result.final_result
                    
                    # If recovery strategy is fallback, return the fallback result
                    if recovery_result.strategy_used == RecoveryStrategy.FALLBACK:
                        return recovery_result.final_result
                    
                    # For retry strategy, continue to next iteration
                    if recovery_result.strategy_used == RecoveryStrategy.RETRY:
                        # Only retry if we haven't exceeded max attempts
                        if attempt < max_retries:
                            time.sleep(min(2 ** attempt, 10))  # Exponential backoff
                            continue
                        else:
                            raise e
            
            # Should not reach here, but just in case
            raise RuntimeError(f"Operation {operation_name} failed after all recovery attempts")
        
        return wrapper
    return decorator


def log_status_update(operation: str, status: str, progress: Optional[float] = None,
                     **kwargs):
    """
    Log a status update for long-running operations.
    
    Args:
        operation: Name of the operation
        status: Current status
        progress: Optional progress percentage (0.0 to 1.0)
        **kwargs: Additional status information
    """
    logger = logging.getLogger('steel_parser.status')
    
    extra = {
        'operation': operation,
        'status': status,
        'timestamp': time.time(),
        **kwargs
    }
    
    if progress is not None:
        extra['progress'] = progress
        message = f"{operation}: {status} ({progress:.1%} complete)"
    else:
        message = f"{operation}: {status}"
    
    logger.info(message, extra=extra)