"""Main entry point for the Steel Drawing Parser application."""

import argparse
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.interface.web_interface import launch_interface
from src.utils.logging_config import setup_logging
from src.models.configuration_manager import (
    get_config_manager, load_system_config, InterfaceType, ConfigurationError
)


def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(
        description="Steel Drawing Parser - Extract component information from PDF drawings"
    )
    
    parser.add_argument(
        '--config',
        type=str,
        help='Configuration file path (JSON or YAML)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        help='Port to run the web interface on (overrides config)'
    )
    
    parser.add_argument(
        '--host',
        type=str,
        help='Host to bind the web interface to (overrides config)'
    )
    
    parser.add_argument(
        '--share',
        action='store_true',
        help='Create a public shareable link'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Set logging level (overrides config)'
    )
    
    parser.add_argument(
        '--log-dir',
        type=str,
        help='Directory for log files (overrides config)'
    )
    
    parser.add_argument(
        '--create-config',
        type=str,
        help='Create a default configuration file at the specified path'
    )
    
    parser.add_argument(
        '--validate-config',
        type=str,
        help='Validate a configuration file without starting the application'
    )
    
    args = parser.parse_args()
    
    try:
        # Handle configuration file creation
        if args.create_config:
            config_manager = get_config_manager()
            config_manager.create_default_config_file(args.create_config)
            print(f"✅ Default configuration file created: {args.create_config}")
            return
        
        # Handle configuration validation
        if args.validate_config:
            config_manager = get_config_manager()
            errors = config_manager.validate_configuration_file(args.validate_config)
            if errors:
                print(f"❌ Configuration validation failed:")
                for error in errors:
                    print(f"   - {error}")
                sys.exit(1)
            else:
                print(f"✅ Configuration file is valid: {args.validate_config}")
                return
        
        # Load system configuration
        try:
            config = load_system_config(
                config_file=args.config,
                interface_type=InterfaceType.WEB
            )
        except ConfigurationError as e:
            print(f"❌ Configuration error: {e}")
            print("💡 Use --create-config to create a default configuration file")
            sys.exit(1)
        
        # Apply command-line overrides
        if args.port:
            config.web_interface.port = args.port
        if args.host:
            config.web_interface.host = args.host
        if args.share:
            config.web_interface.share = True
        if args.debug:
            config.web_interface.debug = True
        if args.log_level:
            config.logging.log_level = args.log_level
        if args.log_dir:
            config.logging.log_dir = args.log_dir
        
        # Set up logging with configuration
        setup_logging(log_dir=config.logging.log_dir, log_level=config.logging.log_level)
        
        print("🏗️  Steel Drawing Parser")
        print("=" * 50)
        print(f"Starting web interface on {config.web_interface.host}:{config.web_interface.port}")
        print(f"Log level: {config.logging.log_level}")
        print(f"Log directory: {config.logging.log_dir}")
        print(f"Configuration file: {args.config or 'default'}")
        print(f"Extensibility enabled: {config.enable_extensibility}")
        
        if config.web_interface.share:
            print("Creating public shareable link...")
        
        if config.web_interface.debug:
            print("Debug mode enabled")
        
        print("=" * 50)
        
        # Launch the web interface with configuration
        launch_interface(
            server_name=config.web_interface.host,
            server_port=config.web_interface.port,
            share=config.web_interface.share,
            debug=config.web_interface.debug,
            config=config
        )
        
    except KeyboardInterrupt:
        print("\n👋 Shutting down Steel Drawing Parser...")
    except Exception as e:
        print(f"❌ Failed to start application: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()