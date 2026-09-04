"""Default configuration for the Steel Drawing Parser."""

from src.models.config import ExtractionConfig

# Default extraction configuration
DEFAULT_EXTRACTION_CONFIG = ExtractionConfig(
    min_component_size=50,
    dimension_tolerance=0.1,
    confidence_threshold=0.7,
    supported_units=["mm", "in", "ft", "m"],
    material_standards=["ASTM", "AISC", "EN", "ISO"],
    dpi=300
)

# Logging configuration
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
        'detailed': {
            'format': '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s'
        }
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard'
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': 'logs/errors.log',
            'formatter': 'detailed'
        },
        'processing_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'logs/processing.log',
            'formatter': 'standard'
        },
        'performance_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': 'logs/performance.log',
            'formatter': 'detailed'
        }
    },
    'loggers': {
        'steel_parser': {
            'handlers': ['console', 'processing_file'],
            'level': 'INFO',
            'propagate': False
        },
        'steel_parser.errors': {
            'handlers': ['console', 'error_file'],
            'level': 'ERROR',
            'propagate': False
        },
        'steel_parser.performance': {
            'handlers': ['performance_file'],
            'level': 'DEBUG',
            'propagate': False
        }
    }
}