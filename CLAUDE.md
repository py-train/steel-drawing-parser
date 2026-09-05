# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Steel Drawing Parser extracts structural steel component information (beams, columns, plates, bolts, welds) from PDF technical drawings and outputs CSV data. It provides a Gradio web interface for uploading PDFs and viewing extracted components.

**Note:** The OCR in `DimensionExtractor._simulate_ocr()` is a placeholder that generates random data. Real OCR (e.g., Tesseract) is not yet integrated.

## Commands

```bash
# Run the web interface (Gradio, default port 7860)
python -m src.main

# Run all tests
pytest

# Run a single test file or test
pytest tests/test_file.py
pytest tests/test_file.py::TestClass::test_method

# Format
black src/ tests/

# Lint
flake8 src/ tests/
pylint $(git ls-files '*.py')

# Type check (strict mode)
mypy src/
```

## Architecture

Processing pipeline: **PDF → Images → Component Detection → Dimension/Material Extraction → Validation → CSV**

### Pipeline stages (`src/`)

1. **`processors/pdf_processor.py`** — `PDFProcessor`: validates PDF, extracts pages as `PDFPage` objects via PyMuPDF
2. **`processors/image_extractor.py`** — `ImageExtractor`: converts pages to NumPy arrays at configurable DPI, applies CLAHE/bilateral filter/morphological preprocessing
3. **`extractors/extensible_part_extractor.py`** — `ExtensiblePartExtractor`: plugin-style detector architecture using `DetectorRegistry`. Loads detector definitions from `config/part_types.json`. Uses non-maximum suppression for deduplication. This is the active extractor used by the web interface
4. **`extractors/dimension_extractor.py`** — `DimensionExtractor`: finds text regions via morphological ops, regex-parses dimensions (mm/in/ft/m) and material specs (W-shapes, ASTM grades)
5. **`extractors/data_validator.py`** — `DataValidator`: validates dimensions against expected ranges per component type, validates material specs against ASTM standards, cross-validates consistency
6. **`generators/csv_generator.py`** — `CSVGenerator`: outputs structured CSV with 19 standard columns including validation status

### Other key modules

- **`models/`** — data models: `Component`, `ComponentType` (enum), `ComponentDimensions`, `MaterialSpec`, `Coordinates`, `ProcessingResult`, `ValidationResult`, `SystemConfig`
- **`models/configuration_manager.py`** — `ConfigurationManager`: loads config from JSON/YAML with env var overrides (`STEEL_PARSER_*` prefix)
- **`interface/web_interface.py`** — `SteelDrawingParserInterface`: Gradio UI orchestrating the full pipeline
- **`extractors/part_extractor.py`** — `PartExtractor`: original monolithic extractor, superseded by `ExtensiblePartExtractor`

## Configuration

- `config/system_config.yaml` — main system config (extraction params, web interface, logging)
- `config/part_types.json` — component type definitions and detection parameters for the extensible extractor
- Environment variables: `STEEL_PARSER_HOST`, `STEEL_PARSER_PORT`, `STEEL_PARSER_DEBUG`, `STEEL_PARSER_LOG_LEVEL`, `STEEL_PARSER_LOG_DIR`, `STEEL_PARSER_CONFIDENCE_THRESHOLD`

## Tech Stack

- Python 3.13 (strict requirement)
- PyMuPDF (fitz), OpenCV, NumPy, Pillow for PDF/image processing
- Gradio for web interface
- pandas for CSV data handling
- hypothesis for property-based testing
- mypy in strict mode, black for formatting, flake8 + pylint for linting
