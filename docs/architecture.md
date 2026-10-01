# Architecture: Cross-Folder Dependencies

```mermaid
flowchart TD
    main["main.py"]
    interface["interface"]
    extractors["extractors"]
    generators["generators"]
    processors["processors"]
    models["models"]
    utils["utils"]

    main -->|"launch_interface"| interface
    main -->|"setup_logging"| utils
    main -->|"get_config_manager, load_system_config,\nInterfaceType, ConfigurationError"| models

    interface -->|"PDFProcessor, ImageExtractor"| processors
    interface -->|"ExtensiblePartExtractor,\nDimensionExtractor, DataValidator"| extractors
    interface -->|"CSVGenerator"| generators
    interface -->|"setup_logging, resilient_operation,\nget_performance_monitor, ..."| utils
    interface -->|"SystemConfig"| models

    processors -->|"ProcessingError"| models
    processors -->|"get_performance_monitor,\nmonitor_performance"| utils

    generators -->|"Component, ComponentType,\nValidationResult, ..."| models
    generators -->|"get_performance_monitor,\nmonitor_performance"| utils

    extractors -->|"Component, ComponentType,\nComponentDimensions, MaterialSpec,\nPartTypeConfigLoader, ValidationResult, ..."| models
    extractors -->|"BoundingBox"| processors
    extractors -->|"get_performance_monitor,\nmonitor_performance"| utils
```

## Key Observations

- **models** and **utils** are pure leaf packages — zero outward cross-folder dependencies, imported by every other package.
- **interface** (`web_interface.py`) is the orchestration layer — it touches all five other subpackages.
- **main.py** is a thin entry point delegating to interface, models, and utils.
- **extractors** depends on both **models** (data classes) and **processors** (`BoundingBox`).
- **processors** does NOT depend on extractors or generators, keeping its dependency surface small.
- **utils** (especially `performance_monitor`) is the most universally depended-upon module.
