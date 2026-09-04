"""Tests for the configuration management system."""

import pytest
import tempfile
import json
import os
from pathlib import Path
from unittest.mock import patch

from src.models.configuration_manager import (
    ConfigurationManager, SystemConfig, InterfaceType, ConfigurationError,
    WebInterfaceConfig, CLIConfig, APIInterfaceConfig, LoggingConfig,
    get_config_manager, load_system_config
)
from src.models.config import ExtractionConfig


class TestConfigurationManager:
    """Test the configuration management system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_manager = ConfigurationManager(self.temp_dir)
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_default_configuration_loading(self):
        """Test loading default configuration."""
        config = self.config_manager.load_configuration()
        
        assert isinstance(config, SystemConfig)
        assert isinstance(config.extraction, ExtractionConfig)
        assert isinstance(config.web_interface, WebInterfaceConfig)
        assert isinstance(config.cli_interface, CLIConfig)
        assert isinstance(config.api_interface, APIInterfaceConfig)
        assert isinstance(config.logging, LoggingConfig)
        
        # Test default values
        assert config.extraction.confidence_threshold == 0.7
        assert config.web_interface.port == 7860
        assert config.logging.log_level == "INFO"
    
    def test_configuration_from_json_file(self):
        """Test loading configuration from JSON file."""
        # Create test configuration file
        test_config = {
            "extraction": {
                "confidence_threshold": 0.8,
                "min_component_size": 75
            },
            "web_interface": {
                "port": 8080,
                "debug": True
            },
            "logging": {
                "log_level": "DEBUG"
            }
        }
        
        config_file = Path(self.temp_dir) / "test_config.json"
        with open(config_file, 'w') as f:
            json.dump(test_config, f)
        
        # Load configuration
        config = self.config_manager.load_configuration("test_config.json")
        
        # Verify loaded values
        assert config.extraction.confidence_threshold == 0.8
        assert config.extraction.min_component_size == 75
        assert config.web_interface.port == 8080
        assert config.web_interface.debug is True
        assert config.logging.log_level == "DEBUG"
    
    def test_environment_variable_overrides(self):
        """Test environment variable overrides."""
        with patch.dict(os.environ, {
            'STEEL_PARSER_HOST': '0.0.0.0',
            'STEEL_PARSER_PORT': '9000',
            'STEEL_PARSER_DEBUG': 'true',
            'STEEL_PARSER_LOG_LEVEL': 'WARNING',
            'STEEL_PARSER_CONFIDENCE_THRESHOLD': '0.9'
        }):
            config = self.config_manager.load_configuration()
            
            assert config.web_interface.host == '0.0.0.0'
            assert config.web_interface.port == 9000
            assert config.web_interface.debug is True
            assert config.logging.log_level == 'WARNING'
            assert config.extraction.confidence_threshold == 0.9
    
    def test_interface_specific_defaults(self):
        """Test interface-specific default configurations."""
        # Test CLI interface defaults
        cli_config = self.config_manager.load_configuration(
            interface_type=InterfaceType.CLI
        )
        assert cli_config.logging.enable_console_logging is True
        assert cli_config.web_interface.debug is False
        
        # Test Web interface defaults
        web_config = self.config_manager.load_configuration(
            interface_type=InterfaceType.WEB
        )
        assert web_config.web_interface.enable_component_management is True
        
        # Test API interface defaults
        api_config = self.config_manager.load_configuration(
            interface_type=InterfaceType.API
        )
        assert api_config.api_interface.enable_docs is True
    
    def test_configuration_validation(self):
        """Test configuration validation."""
        # Test valid configuration
        valid_config = SystemConfig()
        errors = valid_config.validate()
        assert len(errors) == 0
        
        # Test invalid configuration
        invalid_config = SystemConfig()
        invalid_config.web_interface.port = -1  # Invalid port
        invalid_config.logging.log_level = "INVALID"  # Invalid log level
        
        errors = invalid_config.validate()
        assert len(errors) > 0
        assert any("web interface" in error.lower() for error in errors)
        assert any("logging" in error.lower() for error in errors)
    
    def test_configuration_saving(self):
        """Test saving configuration to file."""
        config = SystemConfig()
        config.web_interface.port = 8888
        config.extraction.confidence_threshold = 0.85
        
        # Save configuration
        self.config_manager.save_configuration(config, "saved_config.json")
        
        # Verify file exists
        config_file = Path(self.temp_dir) / "saved_config.json"
        assert config_file.exists()
        
        # Load and verify saved configuration
        with open(config_file, 'r') as f:
            saved_data = json.load(f)
        
        assert saved_data["web_interface"]["port"] == 8888
        assert saved_data["extraction"]["confidence_threshold"] == 0.85
    
    def test_configuration_file_validation(self):
        """Test configuration file validation without loading."""
        # Create valid configuration file
        valid_config = {
            "extraction": {"confidence_threshold": 0.8},
            "web_interface": {"port": 8080}
        }
        
        valid_file = Path(self.temp_dir) / "valid_config.json"
        with open(valid_file, 'w') as f:
            json.dump(valid_config, f)
        
        # Test validation
        errors = self.config_manager.validate_configuration_file("valid_config.json")
        assert len(errors) == 0
        
        # Create invalid configuration file
        invalid_config = {
            "web_interface": {"port": -1},  # Invalid port
            "logging": {"log_level": "INVALID"}  # Invalid log level
        }
        
        invalid_file = Path(self.temp_dir) / "invalid_config.json"
        with open(invalid_file, 'w') as f:
            json.dump(invalid_config, f)
        
        # Test validation
        errors = self.config_manager.validate_configuration_file("invalid_config.json")
        assert len(errors) > 0
    
    def test_default_config_file_creation(self):
        """Test creating default configuration file."""
        config_file = "default_config.json"
        self.config_manager.create_default_config_file(config_file)
        
        # Verify file was created
        config_path = Path(self.temp_dir) / config_file
        assert config_path.exists()
        
        # Verify file contains valid configuration
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        
        assert "extraction" in config_data
        assert "web_interface" in config_data
        assert "logging" in config_data
    
    def test_configuration_reload(self):
        """Test configuration reloading."""
        # Load initial configuration
        config1 = self.config_manager.load_configuration()
        
        # Reload configuration
        config2 = self.config_manager.reload_configuration()
        
        # Should be equivalent
        assert config1.extraction.confidence_threshold == config2.extraction.confidence_threshold
        assert config1.web_interface.port == config2.web_interface.port
    
    def test_part_type_configuration_loading(self):
        """Test loading part type configurations."""
        # Create part types configuration file
        part_types_config = {
            "component_types": [
                {
                    "name": "test_beam",
                    "display_name": "Test Beam",
                    "description": "Test beam component",
                    "detection_method": "extract_test_beams",
                    "detection_params": {
                        "min_size": 100,
                        "confidence_threshold": 0.7,
                        "aspect_ratio_range": [3.0, 20.0],
                        "angle_tolerance": 15.0,
                        "line_grouping_distance": 20,
                        "custom_params": {}
                    },
                    "enabled": True
                }
            ]
        }
        
        part_types_file = Path(self.temp_dir) / "part_types.json"
        with open(part_types_file, 'w') as f:
            json.dump(part_types_config, f)
        
        # Load configuration with part types
        config = self.config_manager.load_configuration()
        
        # Verify part type registry is available
        registry = self.config_manager.get_part_type_registry()
        assert registry is not None
    
    def test_configuration_error_handling(self):
        """Test configuration error handling."""
        # Test loading non-existent file (should use defaults, not raise error)
        config = self.config_manager.load_configuration("non_existent.json")
        assert isinstance(config, SystemConfig)  # Should load defaults
        
        # Test invalid JSON file
        invalid_file = Path(self.temp_dir) / "invalid.json"
        with open(invalid_file, 'w') as f:
            f.write("invalid json content")
        
        with pytest.raises(ConfigurationError):
            self.config_manager.load_configuration("invalid.json")


class TestConfigurationDataClasses:
    """Test configuration data classes."""
    
    def test_extraction_config_validation(self):
        """Test ExtractionConfig validation."""
        # Valid configuration
        valid_config = ExtractionConfig()
        assert valid_config.validate() is True
        
        # Invalid configurations
        invalid_config1 = ExtractionConfig(min_component_size=-1)
        assert invalid_config1.validate() is False
        
        invalid_config2 = ExtractionConfig(confidence_threshold=1.5)
        assert invalid_config2.validate() is False
        
        invalid_config3 = ExtractionConfig(dpi=-100)
        assert invalid_config3.validate() is False
    
    def test_web_interface_config_validation(self):
        """Test WebInterfaceConfig validation."""
        # Valid configuration
        valid_config = WebInterfaceConfig()
        assert valid_config.validate() is True
        
        # Invalid configurations
        invalid_config1 = WebInterfaceConfig(port=-1)
        assert invalid_config1.validate() is False
        
        invalid_config2 = WebInterfaceConfig(port=70000)
        assert invalid_config2.validate() is False
        
        invalid_config3 = WebInterfaceConfig(max_file_size_mb=-1)
        assert invalid_config3.validate() is False
    
    def test_api_interface_config_validation(self):
        """Test APIInterfaceConfig validation."""
        # Valid configuration
        valid_config = APIInterfaceConfig()
        assert valid_config.validate() is True
        
        # Invalid configurations
        invalid_config1 = APIInterfaceConfig(port=-1)
        assert invalid_config1.validate() is False
        
        invalid_config2 = APIInterfaceConfig(rate_limit_per_minute=-1)
        assert invalid_config2.validate() is False
        
        invalid_config3 = APIInterfaceConfig(max_concurrent_requests=-1)
        assert invalid_config3.validate() is False
    
    def test_logging_config_validation(self):
        """Test LoggingConfig validation."""
        # Valid configuration
        valid_config = LoggingConfig()
        assert valid_config.validate() is True
        
        # Invalid configurations
        invalid_config1 = LoggingConfig(log_level="INVALID")
        assert invalid_config1.validate() is False
        
        invalid_config2 = LoggingConfig(max_log_size_mb=-1)
        assert invalid_config2.validate() is False
        
        invalid_config3 = LoggingConfig(backup_count=-1)
        assert invalid_config3.validate() is False


class TestGlobalConfigurationFunctions:
    """Test global configuration functions."""
    
    def test_get_config_manager(self):
        """Test getting global configuration manager."""
        manager1 = get_config_manager()
        manager2 = get_config_manager()
        
        # Should return the same instance
        assert manager1 is manager2
    
    def test_load_system_config(self):
        """Test convenience function for loading system config."""
        config = load_system_config(interface_type=InterfaceType.WEB)
        
        assert isinstance(config, SystemConfig)
        assert config.web_interface.enable_component_management is True