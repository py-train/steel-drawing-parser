"""
Performance monitoring and optimization utilities for the Steel Drawing Parser.

This module provides comprehensive performance monitoring including:
- Processing time tracking
- Memory usage monitoring
- Resource utilization analysis
- Performance logging and reporting
- Optimization recommendations
"""

import time
import psutil
import threading
import logging
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from contextlib import contextmanager
from collections import defaultdict, deque
import json
from pathlib import Path


@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    memory_start: int = 0
    memory_end: int = 0
    memory_peak: int = 0
    memory_delta: int = 0
    cpu_percent: float = 0.0
    page_count: int = 0
    component_count: int = 0
    file_size_mb: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def finalize(self):
        """Finalize metrics calculation."""
        if self.end_time and self.start_time:
            self.duration = self.end_time - self.start_time
        if self.memory_end and self.memory_start:
            self.memory_delta = self.memory_end - self.memory_start


@dataclass
class SystemResourceSnapshot:
    """Snapshot of system resource usage."""
    timestamp: float
    memory_rss: int  # Resident Set Size
    memory_vms: int  # Virtual Memory Size
    memory_percent: float
    cpu_percent: float
    thread_count: int
    file_descriptors: int


class PerformanceMonitor:
    """
    Comprehensive performance monitoring system.
    
    Tracks processing time, memory usage, and system resources
    for optimization and performance analysis.
    """
    
    def __init__(self, log_level: str = "INFO"):
        """
        Initialize performance monitor.
        
        Args:
            log_level: Logging level for performance logs
        """
        self.logger = logging.getLogger('steel_parser.performance')
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # Performance metrics storage
        self._metrics: List[PerformanceMetrics] = []
        self._active_operations: Dict[str, PerformanceMetrics] = {}
        self._resource_snapshots: deque = deque(maxlen=1000)  # Keep last 1000 snapshots
        
        # System process reference
        self._process = psutil.Process()
        
        # Performance thresholds (configurable)
        self.thresholds = {
            'max_processing_time_seconds': 300,  # 5 minutes
            'max_memory_usage_mb': 1024,  # 1GB
            'max_memory_increase_mb': 512,  # 512MB
            'warning_processing_time_seconds': 60,  # 1 minute
            'warning_memory_increase_mb': 256,  # 256MB
        }
        
        # Background monitoring
        self._monitoring_active = False
        self._monitoring_thread: Optional[threading.Thread] = None
        self._monitoring_interval = 5.0  # seconds
        
        # Performance statistics
        self._stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'total_processing_time': 0.0,
            'total_memory_used': 0,
            'average_processing_time': 0.0,
            'peak_memory_usage': 0,
        }
        
        self.logger.info("Performance monitor initialized")
    
    def start_operation(self, operation_name: str, **metadata) -> str:
        """
        Start monitoring a performance operation.
        
        Args:
            operation_name: Name of the operation being monitored
            **metadata: Additional metadata for the operation
            
        Returns:
            Operation ID for tracking
        """
        operation_id = f"{operation_name}_{int(time.time() * 1000)}"
        
        # Get initial system state
        memory_info = self._process.memory_info()
        
        metrics = PerformanceMetrics(
            operation_name=operation_name,
            start_time=time.time(),
            memory_start=memory_info.rss,
            metadata=metadata
        )
        
        self._active_operations[operation_id] = metrics
        
        self.logger.debug(f"Started monitoring operation: {operation_name} (ID: {operation_id})")
        return operation_id
    
    def end_operation(self, operation_id: str, success: bool = True, 
                     error_message: Optional[str] = None, **result_metadata) -> PerformanceMetrics:
        """
        End monitoring a performance operation.
        
        Args:
            operation_id: Operation ID returned by start_operation
            success: Whether the operation succeeded
            error_message: Error message if operation failed
            **result_metadata: Additional result metadata
            
        Returns:
            Completed performance metrics
        """
        if operation_id not in self._active_operations:
            self.logger.warning(f"Unknown operation ID: {operation_id}")
            return None
        
        metrics = self._active_operations.pop(operation_id)
        
        # Finalize metrics
        metrics.end_time = time.time()
        metrics.success = success
        metrics.error_message = error_message
        metrics.metadata.update(result_metadata)
        
        # Get final system state
        memory_info = self._process.memory_info()
        metrics.memory_end = memory_info.rss
        metrics.cpu_percent = self._process.cpu_percent()
        
        # Calculate derived metrics
        metrics.finalize()
        
        # Store completed metrics
        self._metrics.append(metrics)
        
        # Update statistics
        self._update_statistics(metrics)
        
        # Log performance information
        self._log_performance_metrics(metrics)
        
        # Check for performance issues
        self._check_performance_thresholds(metrics)
        
        self.logger.debug(f"Completed monitoring operation: {metrics.operation_name} "
                         f"(Duration: {metrics.duration:.2f}s, Memory: {metrics.memory_delta/1024/1024:.1f}MB)")
        
        return metrics
    
    @contextmanager
    def monitor_operation(self, operation_name: str, **metadata):
        """
        Context manager for monitoring operations.
        
        Args:
            operation_name: Name of the operation
            **metadata: Additional metadata
            
        Usage:
            with monitor.monitor_operation("pdf_processing", file_size=1024):
                # Your operation code here
                pass
        """
        operation_id = self.start_operation(operation_name, **metadata)
        try:
            yield operation_id
            self.end_operation(operation_id, success=True)
        except Exception as e:
            self.end_operation(operation_id, success=False, error_message=str(e))
            raise
    
    def start_background_monitoring(self):
        """Start background system resource monitoring."""
        if self._monitoring_active:
            return
        
        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(target=self._background_monitor, daemon=True)
        self._monitoring_thread.start()
        
        self.logger.info("Started background resource monitoring")
    
    def stop_background_monitoring(self):
        """Stop background system resource monitoring."""
        self._monitoring_active = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=1.0)
        
        self.logger.info("Stopped background resource monitoring")
    
    def _background_monitor(self):
        """Background thread for continuous resource monitoring."""
        while self._monitoring_active:
            try:
                # Capture system resource snapshot
                memory_info = self._process.memory_info()
                
                snapshot = SystemResourceSnapshot(
                    timestamp=time.time(),
                    memory_rss=memory_info.rss,
                    memory_vms=memory_info.vms,
                    memory_percent=self._process.memory_percent(),
                    cpu_percent=self._process.cpu_percent(),
                    thread_count=self._process.num_threads(),
                    file_descriptors=self._process.num_fds() if hasattr(self._process, 'num_fds') else 0
                )
                
                self._resource_snapshots.append(snapshot)
                
                # Check for resource issues
                self._check_resource_thresholds(snapshot)
                
            except Exception as e:
                self.logger.error(f"Error in background monitoring: {e}")
            
            time.sleep(self._monitoring_interval)
    
    def _update_statistics(self, metrics: PerformanceMetrics):
        """Update performance statistics."""
        self._stats['total_operations'] += 1
        
        if metrics.success:
            self._stats['successful_operations'] += 1
        else:
            self._stats['failed_operations'] += 1
        
        if metrics.duration:
            self._stats['total_processing_time'] += metrics.duration
            self._stats['average_processing_time'] = (
                self._stats['total_processing_time'] / self._stats['total_operations']
            )
        
        if metrics.memory_delta > 0:
            self._stats['total_memory_used'] += metrics.memory_delta
        
        if metrics.memory_end > self._stats['peak_memory_usage']:
            self._stats['peak_memory_usage'] = metrics.memory_end
    
    def _log_performance_metrics(self, metrics: PerformanceMetrics):
        """Log performance metrics."""
        if metrics.success:
            self.logger.info(
                f"Operation '{metrics.operation_name}' completed in {metrics.duration:.2f}s, "
                f"Memory: {metrics.memory_delta/1024/1024:+.1f}MB, "
                f"CPU: {metrics.cpu_percent:.1f}%"
            )
        else:
            self.logger.error(
                f"Operation '{metrics.operation_name}' failed after {metrics.duration:.2f}s: "
                f"{metrics.error_message}"
            )
    
    def _check_performance_thresholds(self, metrics: PerformanceMetrics):
        """Check performance metrics against thresholds."""
        # Check processing time
        if metrics.duration:
            if metrics.duration > self.thresholds['max_processing_time_seconds']:
                self.logger.error(
                    f"Operation '{metrics.operation_name}' exceeded maximum processing time: "
                    f"{metrics.duration:.2f}s > {self.thresholds['max_processing_time_seconds']}s"
                )
            elif metrics.duration > self.thresholds['warning_processing_time_seconds']:
                self.logger.warning(
                    f"Operation '{metrics.operation_name}' took longer than expected: "
                    f"{metrics.duration:.2f}s"
                )
        
        # Check memory usage
        memory_delta_mb = metrics.memory_delta / 1024 / 1024
        if memory_delta_mb > self.thresholds['max_memory_increase_mb']:
            self.logger.error(
                f"Operation '{metrics.operation_name}' exceeded maximum memory increase: "
                f"{memory_delta_mb:.1f}MB > {self.thresholds['max_memory_increase_mb']}MB"
            )
        elif memory_delta_mb > self.thresholds['warning_memory_increase_mb']:
            self.logger.warning(
                f"Operation '{metrics.operation_name}' used more memory than expected: "
                f"{memory_delta_mb:.1f}MB"
            )
    
    def _check_resource_thresholds(self, snapshot: SystemResourceSnapshot):
        """Check system resource thresholds."""
        memory_mb = snapshot.memory_rss / 1024 / 1024
        
        if memory_mb > self.thresholds['max_memory_usage_mb']:
            self.logger.error(
                f"System memory usage exceeded threshold: "
                f"{memory_mb:.1f}MB > {self.thresholds['max_memory_usage_mb']}MB"
            )
        
        if snapshot.cpu_percent > 90.0:
            self.logger.warning(f"High CPU usage detected: {snapshot.cpu_percent:.1f}%")
    
    def get_performance_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive performance report.
        
        Returns:
            Dictionary containing performance statistics and analysis
        """
        report = {
            'summary': dict(self._stats),
            'recent_operations': [],
            'performance_trends': {},
            'resource_usage': {},
            'recommendations': []
        }
        
        # Recent operations (last 10)
        recent_metrics = self._metrics[-10:] if self._metrics else []
        for metrics in recent_metrics:
            report['recent_operations'].append({
                'operation': metrics.operation_name,
                'duration': metrics.duration,
                'memory_delta_mb': metrics.memory_delta / 1024 / 1024 if metrics.memory_delta else 0,
                'success': metrics.success,
                'timestamp': metrics.start_time
            })
        
        # Performance trends
        if len(self._metrics) >= 5:
            recent_durations = [m.duration for m in self._metrics[-5:] if m.duration]
            if recent_durations:
                report['performance_trends']['average_recent_duration'] = sum(recent_durations) / len(recent_durations)
                report['performance_trends']['duration_trend'] = 'improving' if recent_durations[-1] < recent_durations[0] else 'degrading'
        
        # Current resource usage
        if self._resource_snapshots:
            latest_snapshot = self._resource_snapshots[-1]
            report['resource_usage'] = {
                'memory_rss_mb': latest_snapshot.memory_rss / 1024 / 1024,
                'memory_percent': latest_snapshot.memory_percent,
                'cpu_percent': latest_snapshot.cpu_percent,
                'thread_count': latest_snapshot.thread_count,
                'file_descriptors': latest_snapshot.file_descriptors
            }
        
        # Performance recommendations
        report['recommendations'] = self._generate_recommendations()
        
        return report
    
    def _generate_recommendations(self) -> List[str]:
        """Generate performance optimization recommendations."""
        recommendations = []
        
        if not self._metrics:
            return recommendations
        
        # Analyze recent performance
        recent_metrics = self._metrics[-10:] if len(self._metrics) >= 10 else self._metrics
        
        # Check for slow operations
        slow_operations = [m for m in recent_metrics if m.duration and m.duration > 30]
        if slow_operations:
            recommendations.append(
                f"Consider optimizing slow operations: {len(slow_operations)} operations took >30s"
            )
        
        # Check for high memory usage
        high_memory_ops = [m for m in recent_metrics if m.memory_delta > 100 * 1024 * 1024]  # >100MB
        if high_memory_ops:
            recommendations.append(
                f"Consider memory optimization: {len(high_memory_ops)} operations used >100MB"
            )
        
        # Check failure rate
        failed_ops = [m for m in recent_metrics if not m.success]
        if len(failed_ops) > len(recent_metrics) * 0.1:  # >10% failure rate
            recommendations.append(
                f"High failure rate detected: {len(failed_ops)}/{len(recent_metrics)} operations failed"
            )
        
        # Check for resource trends
        if self._resource_snapshots and len(self._resource_snapshots) >= 10:
            recent_snapshots = list(self._resource_snapshots)[-10:]
            memory_trend = recent_snapshots[-1].memory_rss - recent_snapshots[0].memory_rss
            if memory_trend > 50 * 1024 * 1024:  # >50MB increase
                recommendations.append("Memory usage is trending upward - check for memory leaks")
        
        return recommendations
    
    def save_performance_report(self, file_path: str):
        """
        Save performance report to file.
        
        Args:
            file_path: Path to save the report
        """
        report = self.get_performance_report()
        
        try:
            with open(file_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.info(f"Performance report saved to {file_path}")
        except Exception as e:
            self.logger.error(f"Failed to save performance report: {e}")
    
    def reset_metrics(self):
        """Reset all performance metrics and statistics."""
        self._metrics.clear()
        self._resource_snapshots.clear()
        self._stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'total_processing_time': 0.0,
            'total_memory_used': 0,
            'average_processing_time': 0.0,
            'peak_memory_usage': 0,
        }
        
        self.logger.info("Performance metrics reset")
    
    def get_operation_metrics(self, operation_name: str) -> List[PerformanceMetrics]:
        """
        Get metrics for specific operation type.
        
        Args:
            operation_name: Name of the operation
            
        Returns:
            List of metrics for the specified operation
        """
        return [m for m in self._metrics if m.operation_name == operation_name]
    
    def set_thresholds(self, **thresholds):
        """
        Update performance thresholds.
        
        Args:
            **thresholds: Threshold values to update
        """
        self.thresholds.update(thresholds)
        self.logger.info(f"Updated performance thresholds: {thresholds}")


# Global performance monitor instance
_performance_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """
    Get the global performance monitor instance.
    
    Returns:
        Performance monitor instance
    """
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


def monitor_performance(operation_name: str, **metadata):
    """
    Decorator for monitoring function performance.
    
    Args:
        operation_name: Name of the operation
        **metadata: Additional metadata
        
    Usage:
        @monitor_performance("pdf_processing")
        def process_pdf(file_path):
            # Your code here
            pass
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            monitor = get_performance_monitor()
            with monitor.monitor_operation(operation_name, **metadata):
                return func(*args, **kwargs)
        return wrapper
    return decorator