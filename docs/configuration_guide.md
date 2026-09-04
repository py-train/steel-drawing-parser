# Steel Drawing Parser - Configuration Guide

## Overview

The Steel Drawing Parser features a comprehensive configuration management system that supports multiple configuration sources, validation, and interface-specific settings. This guide explains how to configure and customize the system for your needs.

## Configuration Architecture

The configuration system follows a hierarchical approach with the following precedence (highest to lowest):

1. **Command Line Arguments** - Runtime parameter overrides
2. **Environment Variables** - System-level configuration
3. **Configuration Files** - JSON or YAML files
4. **Default Values** - Built-in system defaults

## Configuration Structure

The system configuration is organized into several sections:

### Extraction Configuration
Controls component detection and processing parameters:

```json
{
  "extraction": {
    "min_component_size": 50,
    "dimension_tolerance": 0.1,
    "confidence_threshold": 0.7,
    "supported_units": ["mm", "in", "ft", "m"],
    "material_standards": ["ASTM", "AISC", "EN", "ISO"],
    "dpi": 300
  }
}
```

### Web Interface Configuration
Settings for the Gradio web interface:

```json
{
  "web_interface": {
    "host": "127.0.0.1",
    "port": 7860,
    "share": false,
    "debug": false,
    "max_file_size_mb": 100,
    "allowed_file_types": [".pdf"],
    "enable_component_management": true
  }
}
```

### CLI Interface Configuration
Settings for command-line operations:

```json
{
  "cli_interface": {
    "input_files": [],
    "output_directory": "output",
    "batch_mode": false,
    "verbose": false,
    "format": "csv",
    "config_file": null
  }
}
```

### API Interface Configuration
Settings for future API interface:

```json
{
  "api_interface": {
    "host": "127.0.0.1",
    "port": 8000,
    "enable_docs": true,
    "rate_limit_per_minute": 60,
    "max_concurrent_requests": 10
  }
}
```

### Logging Configuration
Logging system settings:

```json
{
  "logging": {
    "log_level": "INFO",
    "log_dir": "logs",
    "max_log_size_mb": 10,
    "backup_count": 5,
    "enable_console_logging": true,
    "enable_file_logging": true,
    "separate_error_log": true
  }
}
```

## Configuration Files

### Supported Formats

The system supports both JSON and YAML configuration files:

**JSON Example** (`config/system_config.json`):
```json
{
  "extraction": {
    "confidence_threshold": 0.8,
    "min_component_size": 75
  },
  "web_interface": {
    "port": 8080,
    "debug": true
  }
}
```

**YAML Example** (`config/system_config.yaml`):
```yaml
extraction:
  confidence_threshold: 0.8
  min_component_size: 75

web_interface:
  port: 8080
  debug: true
```

### Configuration File Management

#### Creating Default Configuration
```bash
# Create a default JSON configuration file
python src/main.py --create-config config/my_config.json

# Create a default YAML configuration file
python src/main.py --create-config config/my_config.yaml
```

#### Validating Configuration
```bash
# Validate a configuration file
python src/main.py --validate-config config/my_config.json

# Validate YAML configuration
python src/main.py --validate-config config/my_config.yaml
```

#### Using Custom Configuration
```bash
# Start with custom configuration
python src/main.py --config config/my_config.json

# Start with YAML configuration
python src/main.py --config config/my_config.yaml
```

## Environment Variables

Override specific configuration values using environment variables:

### Web Interface Variables
- `STEEL_PARSER_HOST` - Web interface host (default: 127.0.0.1)
- `STEEL_PARSER_PORT` - Web interface port (default: 7860)
- `STEEL_PARSER_DEBUG` - Enable debug mode (true/false)

### Logging Variables
- `STEEL_PARSER_LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
- `STEEL_PARSER_LOG_DIR` - Log directory path

### Processing Variables
- `STEEL_PARSER_CONFIDENCE_THRESHOLD` - Detection confidence threshold (0.0-1.0)

### Example Usage
```bash
# Set environment variables
export STEEL_PARSER_HOST=0.0.0.0
export STEEL_PARSER_PORT=8080
export STEEL_PARSER_DEBUG=true
export STEEL_PARSER_LOG_LEVEL=DEBUG

# Start the application
python src/main.py
```

## Command Line Overrides

Command line arguments take precedence over all other configuration sources:

```bash
# Override web interface settings
python src/main.py --host 0.0.0.0 --port 8080 --debug

# Override logging settings
python src/main.py --log-level DEBUG --log-dir /var/log/steel-parser

# Use custom configuration with overrides
python src/main.py --config config/production.json --port 9000
```

## Interface-Specific Configurations

The system applies different default configurations based on the interface type:

### Web Interface Defaults
- Component management enabled
- Console logging enabled
- Debug mode disabled

### CLI Interface Defaults
- Console logging enabled
- File logging enabled
- Verbose output available

### API Interface Defaults
- Documentation enabled
- Rate limiting enabled
- Concurrent request limits

## Configuration Validation

The system validates all configuration parameters:

### Validation Rules

**Extraction Configuration:**
- `min_component_size` must be positive
- `confidence_threshold` must be between 0.0 and 1.0
- `dpi` must be positive

**Web Interface Configuration:**
- `port` must be between 1 and 65535
- `max_file_size_mb` must be positive

**Logging Configuration:**
- `log_level` must be valid (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `max_log_size_mb` must be positive
- `backup_count` must be non-negative

### Validation Examples

```bash
# Validate configuration before starting
python src/main.py --validate-config config/my_config.json

# Check validation results
echo $?  # 0 = valid, 1 = invalid
```

## Extensibility Configuration

The system supports extensible component types through configuration:

### Part Types Configuration
Reference to part types configuration file:
```json
{
  "part_types_config_file": "part_types.json",
  "enable_extensibility": true
}
```

### Component Type Management
Enable/disable component type management in the web interface:
```json
{
  "web_interface": {
    "enable_component_management": true
  }
}
```

## Production Configuration

### Recommended Production Settings

```json
{
  "extraction": {
    "confidence_threshold": 0.8,
    "min_component_size": 75
  },
  "web_interface": {
    "host": "0.0.0.0",
    "port": 80,
    "share": false,
    "debug": false,
    "max_file_size_mb": 500
  },
  "logging": {
    "log_level": "INFO",
    "log_dir": "/var/log/steel-parser",
    "max_log_size_mb": 50,
    "backup_count": 10,
    "separate_error_log": true
  }
}
```

### Security Considerations

1. **Host Binding**: Use `127.0.0.1` for local access only, `0.0.0.0` for network access
2. **File Size Limits**: Set appropriate `max_file_size_mb` limits
3. **Debug Mode**: Disable debug mode in production
4. **Log Management**: Configure appropriate log rotation and retention

## Troubleshooting

### Common Configuration Issues

1. **Invalid Port Numbers**
   ```
   Error: Invalid web interface configuration
   Solution: Ensure port is between 1 and 65535
   ```

2. **Missing Configuration File**
   ```
   Warning: Configuration file not found, using defaults
   Solution: Create configuration file or check path
   ```

3. **Invalid JSON/YAML Syntax**
   ```
   Error: Failed to parse configuration file
   Solution: Validate JSON/YAML syntax
   ```

### Configuration Debugging

Enable debug mode to see detailed configuration loading:
```bash
python src/main.py --debug --config config/my_config.json
```

Check current configuration in the web interface:
1. Open the web interface
2. Go to "System Configuration" tab
3. View current configuration settings

## Advanced Usage

### Programmatic Configuration

```python
from src.models.configuration_manager import (
    ConfigurationManager, SystemConfig, InterfaceType
)

# Create configuration manager
manager = ConfigurationManager("config")

# Load configuration
config = manager.load_configuration(
    config_file="my_config.json",
    interface_type=InterfaceType.WEB
)

# Modify configuration
config.web_interface.port = 8080
config.extraction.confidence_threshold = 0.8

# Save configuration
manager.save_configuration(config, "modified_config.json")
```

### Custom Configuration Sections

Extend the configuration system by modifying the `SystemConfig` class:

```python
@dataclass
class CustomConfig:
    custom_parameter: str = "default_value"
    
    def validate(self) -> bool:
        return len(self.custom_parameter) > 0

# Add to SystemConfig
@dataclass
class SystemConfig:
    # ... existing fields ...
    custom: CustomConfig = field(default_factory=CustomConfig)
```

## Migration Guide

### Upgrading Configuration Files

When upgrading to newer versions, use the validation tool to check compatibility:

```bash
# Check if old configuration is still valid
python src/main.py --validate-config config/old_config.json

# Create new default configuration for comparison
python src/main.py --create-config config/new_default.json
```

### Configuration Schema Changes

The system maintains backward compatibility, but new features may require configuration updates. Check the changelog for configuration schema changes.

## Best Practices

1. **Version Control**: Store configuration files in version control
2. **Environment Separation**: Use different configurations for development, testing, and production
3. **Validation**: Always validate configurations before deployment
4. **Documentation**: Document custom configuration changes
5. **Backup**: Keep backups of working configurations
6. **Security**: Avoid storing sensitive information in configuration files
7. **Monitoring**: Monitor configuration changes in production environments

## Support

For configuration-related issues:

1. Check the validation output for specific error messages
2. Review the configuration guide for parameter requirements
3. Use debug mode to see detailed configuration loading
4. Check environment variables and command line overrides
5. Verify file permissions and paths