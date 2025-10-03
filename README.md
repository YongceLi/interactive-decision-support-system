# Interactive Decision Support System (IDSS)

## Setup

1. Create and activate conda environment:
```bash
conda create -n idss python=3.10
conda activate idss
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your API keys in `.env`:
```bash
OPENAI_API_KEY=your_openai_key
AUTODEV_API_KEY=your_autodev_key
```

## Usage

Run the interactive CLI:
```bash
python cli.py
```

Run with debug mode:
```bash
python cli.py --debug
```
