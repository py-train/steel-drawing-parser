"""
Configuration management system for the Steel Drawing Parser.

This module provides comprehensive configuration management including:
- Configuration loading and validation
- Environment-specific configurations
- Interface-specific configurations (Web, CLI)
- Component configuration management
"""

import json
import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field, asdict
import logging
from enum import Enum

from .config import ExtractionConfig, CLIConfig
from .part_type_config import PartTypeConfigLoader, PartTypeRegistry


class ConfigurationError(Exception):
    """Exception raised for configuration-related errors."""
    pass


class InterfaceType(Enum):
    """Supported interface types."""
    WEB = "web"
    CLI = "cli"
    API = "api"


@dataclass
class WebInterfaceConfig:
    """Configuration for web interface."""
    host: str = "127.0.0.1"
    port: int = 7860
    share: bool = False
    debug: bool = False
    max_file_size_mb: int = 100
    allowed_file_types: List[str] = field(default_factory=lambda: [".pdf"])
    enable_component_management: bool = True
    
    def validate(self) -> bool:
        """Validate web interface configuration."""
        if not (1 <= self.port <= 65535):
            return False
        if self.max_file_size_mb <= 0:
            return False
        return True


@dataclass
class APIInterfaceConfig:
    """Configuration for API interface (future extension)."""
    host: str = "127.0.0.1"
    port: int = 8000
    enable_docs: bool = True
    rate_limit_per_minute: int = 60
    max_concurrent_requests: int = 10
    
    def validate(self) -> bool:
        """Validate API interface configuration."""
        if not (1 <= self.port <= 65535):
            return False
        if self.rate_limit_per_minute <= 0:
            return False
        if self.max_concurrent_requests <= 0:
            return False
        return True


@dataclass
class LoggingConfig:
    """Configuration for logging system."""
    log_level: str = "INFO"
    log_dir: str = "logs"
    max_log_size_mb: int = 10
    backup_count: int = 5
    enable_console_logging: bool = True
    enable_file_logging: bool = True
    separate_error_log: bool = True
    
    def validate(self) -> bool:
        """Validate logging configuration."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level not in valid_levels:
            return False
        if self.max_log_size_mb <= 0:
            return False
        if self.backup_count < 0:
            return False
        return True


@dataclass
class SystemConfig:
    """Main system configuration container."""
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    web_interface: WebInterfaceConfig = field(default_factory=WebInterfaceConfig)
    cli_interface: CLIConfig = field(default_factory=CLIConfig)
    api_interface: APIInterfaceConfig = field(default_factory=APIInterfaceConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    # Component configuration
    part_types_config_file: str = "part_types.json"
    enable_extensibility: bool = True
    
    def validate(self) -> List[str]:
        """
        Validate all configuration sections.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        if not self.extraction.validate():
            errors.append("Invalid extraction configuration")
        
        if not self.web_interface.validate():
            errors.append("Invalid web interface configuration")
        
        if not self.cli_interface:  # Basic existence check
            errors.append("CLI interface configuration missing")
        
        if not self.api_interface.validate():
            errors.append("Invalid API interface configuration")
        
        if not self.logging.validate():
            errors.append("Invalid logging configuration")
        
        return errors


class ConfigurationManager:
    """
    Comprehensive configuration management system.
    
    Supports loading configurations from:
    - JSON files
    - YAML files
    - Environment variables
    - Default values
    """
    
    def __init__(self, config_dir: str = "config"):
        """
        Initialize configuration manager.
        
        Args:
            config_dir: Directory containing configuration files
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger('steel_parser.config_manager')
        
        # Current configuration
        self._config: Optional[SystemConfig] = None
        
        # Part type configuration loader
        self._part_type_loader: Optional[PartTypeConfigLoader] = None
        
        # Configuration file watchers (for future hot-reload)
        self._config_files: Dict[str, Path] = {}
    
    def load_configuration(self, 
                         config_file: Optional[str] = None,
                         interface_type: InterfaceType = InterfaceType.WEB) -> SystemConfig:
        """
        Load system configuration from file or defaults.
        
        Args:
            config_file: Path to configuration file (JSON or YAML)
            interface_type: Type of interface being configured
            
        Returns:
            Loaded and validated system configuration
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        try:
            # Start with default configuration
            config = SystemConfig()
            
            # Load from file if specified
            if config_file:
                config = self._load_from_file(config_file, config)
            
            # Apply environment variable overrides
            config = self._apply_environment_overrides(config)
            
            # Apply interface-specific defaults
            config = self._apply_interface_defaults(config, interface_type)
            
            # Validate configuration
            validation_errors = config.validate()
            if validation_errors:
                raise ConfigurationError(f"Configuration validation failed: {', '.join(validation_errors)}")
            
            # Load part type configurations
            self._load_part_type_configuration(config)
            
            self._config = config
            self.logger.info(f"Configuration loaded successfully for {interface_type.value} interface")
            
            return config
            
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            raise ConfigurationError(f"Configuration loading failed: {e}")
    
    def _load_from_file(self, config_file: str, base_config: SystemConfig) -> SystemConfig:
        """Load configuration from JSON or YAML file."""
        config_path = self.config_dir / config_file
        
        if not config_path.exists():
            self.logger.warning(f"Configuration file not found: {config_path}")
            return base_config
        
        try:
            with open(config_path, 'r') as f:
                if config_path.suffix.lower() in ['.yaml', '.yml']:
                    config_data = yaml.safe_load(f)
                else:
                    config_data = json.load(f)
            
            # Merge with base configuration
            return self._merge_configuration(base_config, config_data)
            
        except Exception as e:
            raise ConfigurationError(f"Failed to parse configuration file {config_path}: {e}")
    
    def _merge_configuration(self, base_config: SystemConfig, config_data: Dict[str, Any]) -> SystemConfig:
        """Merge configuration data with base configuration."""
        # Convert base config to dict for easier manipulation
        config_dict = asdict(base_config)
        
        # Recursively merge configuration sections
        for section, values in config_data.items():
            if section in config_dict and isinstance(values, dict):
                if isinstance(config_dict[section], dict):
                    config_dict[section].update(values)
                else:
                    # Handle dataclass sections
                    self._update_dataclass_from_dict(config_dict[section], values)
            else:
                config_dict[section] = values
        
        # Reconstruct SystemConfig from merged data
        return self._dict_to_system_config(config_dict)
    
    def _update_dataclass_from_dict(self, dataclass_instance: Any, update_dict: Dict[str, Any]) -> None:
        """Update dataclass instance with values from dictionary."""
        for key, value in update_dict.items():
            if hasattr(dataclass_instance, key):
                setattr(dataclass_instance, key, value)
    
    def _dict_to_system_config(self, config_dict: Dict[str, Any]) -> SystemConfig:
        """Convert dictionary back to SystemConfig."""
        # This is a simplified conversion - in a production system,
        # you might want to use a more sophisticated serialization library
        
        extraction_config = ExtractionConfig(**config_dict.get('extraction', {}))
        web_config = WebInterfaceConfig(**config_dict.get('web_interface', {}))
        cli_config = CLIConfig(**config_dict.get('cli_interface', {}))
        api_config = APIInterfaceConfig(**config_dict.get('api_interface', {}))
        logging_config = LoggingConfig(**config_dict.get('logging', {}))
        
        return SystemConfig(
            extraction=extraction_config,
            web_interface=web_config,
            cli_interface=cli_config,
            api_interface=api_config,
            logging=logging_config,
            part_types_config_file=config_dict.get('part_types_config_file', 'part_types.json'),
            enable_extensibility=config_dict.get('enable_extensibility', True)
        )
    
    def _apply_environment_overrides(self, config: SystemConfig) -> SystemConfig:
        """Apply environment variable overrides to configuration."""
        # Web interface overrides
        if os.getenv('STEEL_PARSER_HOST'):
            config.web_interface.host = os.getenv('STEEL_PARSER_HOST')
        
        if os.getenv('STEEL_PARSER_PORT'):
            try:
                config.web_interface.port = int(os.getenv('STEEL_PARSER_PORT'))
            except ValueError:
                self.logger.warning("Invalid STEEL_PARSER_PORT environment variable")
        
        if os.getenv('STEEL_PARSER_DEBUG'):
            config.web_interface.debug = os.getenv('STEEL_PARSER_DEBUG').lower() in ['true', '1', 'yes']
        
        # Logging overrides
        if os.getenv('STEEL_PARSER_LOG_LEVEL'):
            config.logging.log_level = os.getenv('STEEL_PARSER_LOG_LEVEL').upper()
        
        if os.getenv('STEEL_PARSER_LOG_DIR'):
            config.logging.log_dir = os.getenv('STEEL_PARSER_LOG_DIR')
        
        # Extraction overrides
        if os.getenv('STEEL_PARSER_CONFIDENCE_THRESHOLD'):
            try:
                config.extraction.confidence_threshold = float(os.getenv('STEEL_PARSER_CONFIDENCE_THRESHOLD'))
            except ValueError:
                self.logger.warning("Invalid STEEL_PARSER_CONFIDENCE_THRESHOLD environment variable")
        
        return config
    
    def _apply_interface_defaults(self, config: SystemConfig, interface_type: InterfaceType) -> SystemConfig:
        """Apply interface-specific default configurations."""
        if interface_type == InterfaceType.CLI:
            # CLI-specific defaults
            config.logging.enable_console_logging = True
            config.web_interface.debug = False
        elif interface_type == InterfaceType.WEB:
            # Web interface defaults
            config.web_interface.enable_component_management = True
        elif interface_type == InterfaceType.API:
            # API-specific defaults
            config.api_interface.enable_docs = True
        
        return config
    
    def _load_part_type_configuration(self, config: SystemConfig) -> None:
        """Load part type configurations."""
        if config.enable_extensibility:
            try:
                self._part_type_loader = PartTypeConfigLoader(str(self.config_dir))
                self._part_type_loader.load_from_file(config.part_types_config_file)
                self.logger.info("Part type configurations loaded successfully")
            except Exception as e:
                self.logger.warning(f"Failed to load part type configurations: {e}")
                # Continue without part type configurations
    
    def save_configuration(self, config: SystemConfig, config_file: str) -> None:
        """
        Save configuration to file.
        
        Args:
            config: Configuration to save
            config_file: Target configuration file path
        """
        try:
            # Handle absolute paths
            if os.path.isabs(config_file):
                config_path = Path(config_file)
            else:
                config_path = self.config_dir / config_file
            
            # Ensure parent directory exists
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            config_dict = asdict(config)
            
            with open(config_path, 'w') as f:
                if config_path.suffix.lower() in ['.yaml', '.yml']:
                    yaml.dump(config_dict, f, default_flow_style=False, indent=2)
                else:
                    json.dump(config_dict, f, indent=2)
            
            self.logger.info(f"Configuration saved to {config_path}")
            
        except Exception as e:
            raise ConfigurationError(f"Failed to save configuration: {e}")
    
    def get_current_config(self) -> Optional[SystemConfig]:
        """Get the currently loaded configuration."""
        return self._config
    
    def get_part_type_registry(self) -> Optional[PartTypeRegistry]:
        """Get the part type registry if available."""
        if self._part_type_loader:
            return self._part_type_loader.get_registry()
        return None
    
    def reload_configuration(self) -> SystemConfig:
        """Reload configuration from the last loaded file."""
        if self._config:
            # Re-load with the same parameters
            return self.load_configuration()
        else:
            raise ConfigurationError("No configuration loaded to reload")
    
    def validate_configuration_file(self, config_file: str) -> List[str]:
        """
        Validate a configuration file without loading it.
        
        Args:
            config_file: Path to configuration file
            
        Returns:
            List of validation errors (empty if valid)
        """
        try:
            temp_config = SystemConfig()
            temp_config = self._load_from_file(config_file, temp_config)
            return temp_config.validate()
        except Exception as e:
            return [f"Configuration file error: {e}"]
    
    def create_default_config_file(self, config_file: str) -> None:
        """
        Create a default configuration file.
        
        Args:
            config_file: Path for the new configuration file
        """
        default_config = SystemConfig()
        self.save_configuration(default_config, config_file)
        self.logger.info(f"Default configuration file created: {config_file}")


# Global configuration manager instance
_config_manager: Optional[ConfigurationManager] = None


def get_config_manager(config_dir: str = "config") -> ConfigurationManager:
    """
    Get the global configuration manager instance.
    
    Args:
        config_dir: Configuration directory path
        
    Returns:
        Configuration manager instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigurationManager(config_dir)
    return _config_manager


def load_system_config(config_file: Optional[str] = None,
                      interface_type: InterfaceType = InterfaceType.WEB,
                      config_dir: str = "config") -> SystemConfig:
    """
    Convenience function to load system configuration.
    
    Args:
        config_file: Configuration file path
        interface_type: Interface type
        config_dir: Configuration directory
        
    Returns:
        Loaded system configuration
    """
    manager = get_config_manager(config_dir)
    return manager.load_configuration(config_file, interface_type)