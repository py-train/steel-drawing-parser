# Steel Drawing Parser

A Python system for extracting structural steel component information from PDF technical drawings and outputting the data in CSV format.

## Features

- **PDF Processing**: Extract and process pages from CAD-generated PDF drawings
- **Component Recognition**: Identify steel beams, columns, plates, bolts, and welds
- **Data Extraction**: Extract dimensions, material specifications, and connection details
- **CSV Output**: Generate structured CSV files with extracted component data
- **Web Interface**: Simple Gradio-based interface for file upload and results download
- **Extensible Architecture**: Designed to support future audit capabilities

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd steel-drawing-parser
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Or with conda (recommended for Python 3.13):
```bash
conda create -n steel-parser python=3.13
conda activate steel-parser
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Web Interface

Run the web interface:
```bash
python -m src.main
```

Then open your browser to the displayed URL (typically http://localhost:7860).

### Command Line (Future)

```bash
steel-parser input.pdf --output output.csv
```

## Project Structure

```
steel-drawing-parser/
├── src/
│   ├── models/          # Data models
│   ├── processors/      # PDF and image processing
│   ├── extractors/      # Component extraction logic
│   ├── generators/      # CSV output generation
│   ├── interface/       # Web and CLI interfaces
│   └── utils/           # Utility functions
├── tests/               # Test files
├── config/              # Configuration files
├── logs/                # Log files (created at runtime)
└── examples/            # Example files and documentation
```

## Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/ tests/
flake8 src/ tests/
```

### Type Checking

```bash
mypy src/
```

## License

MIT License - see LICENSE file for details.