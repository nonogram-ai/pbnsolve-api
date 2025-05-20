# PBNSolve API

A RESTful API for solving nonogram/paint-by-numbers puzzles using the powerful pbnsolve algorithm.

## Overview

This project provides a FastAPI-based REST API wrapper around the [pbnsolve](http://webpbn.com/pbnsolve.html) nonogram solver. It allows you to solve nonogram puzzles by:

1. Uploading puzzle files in various formats
2. Submitting puzzle data directly as text
3. Configuring various solving algorithm parameters

The API returns the solution along with metadata about the solving process, including the type of solution found (unique, multiple, etc.).

## Features

- Support for multiple nonogram file formats (XML, NON, MK, NIN, CWD, etc.)
- Configurable solving strategies
- Detailed solution information
- Automatic detection of solution uniqueness
- Docker support for easy deployment

## Installation

### Using Docker Compose (Recommended)

```bash
# Build and run with Docker Compose
docker compose up

# Build and run in detached mode
docker compose up -d
```

### Using Docker Manually

```bash
# Build the Docker image
docker build -t pbnsolve-api .

# Run the container
docker run -p 8000:8000 pbnsolve-api
```

### Manual Installation

1. First, compile the pbnsolve binary:

```bash
cd pbnsolve-1.10/
make
sudo cp pbnsolve /usr/local/bin/
```

2. Install Python dependencies:

```bash
pip install fastapi uvicorn python-multipart pydantic
```

3. Run the API server:

```bash
cd api/
uvicorn app:app --host 0.0.0.0 --port 8000
```

## API Endpoints

### `GET /health`

Check if the API is running.

**Response:**
```json
{
  "status": "ok",
  "message": "API is running"
}
```

### `POST /api/solve`

Solve a nonogram puzzle from a file upload.

**Parameters:**
- `file`: The puzzle file to upload
- Various solver options (see below)

**Response:**
```json
{
  "status": "success",
  "solution": "...",
  "solution_type": "UNIQUE_LINE_SOLUTION",
  "stdout": "...",
  "stderr": "...",
  "return_code": 0
}
```

### `POST /api/solve/text`

Solve a nonogram puzzle from text input.

**Parameters:**
- `puzzle`: Text content of the puzzle file
- `format`: Format of the puzzle (xml, non, etc.)
- Various solver options (see below)

**Response:** Same as `/api/solve`

## Solver Options

Both endpoints accept the following parameters to configure the solving process:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `check_uniqueness` | boolean | false | Check if the puzzle has a unique solution |
| `check_solution` | boolean | false | Check if the solution matches any goal solution |
| `use_line_solving` | boolean | true | Enable line solving algorithm |
| `use_exhaust` | boolean | true | Enable exhaustive checking |
| `use_contradiction` | boolean | false | Enable contradiction checking |
| `use_guessing` | boolean | true | Enable guessing strategy |
| `use_probing` | boolean | true | Enable probing strategy |
| `use_merge_probe` | boolean | false | Enable merge probing |
| `use_caching` | boolean | true | Cache line solving results |
| `contradiction_depth` | integer | 2 | Depth for contradiction checking |
| `cpu_limit` | integer | 0 | CPU time limit in seconds (0 = unlimited) |
| `start_solution` | integer | 0 | Solution to start from (0 = none) |
| `puzzle_index` | integer | 1 | Index of puzzle to solve in multi-puzzle files |
| `hint_log` | boolean | false | Enable hint logging |
| `hint_log_n` | integer | 10 | Number of hints to log |
| `scoring_rule` | integer | null | Scoring rule for guessing strategy |
| `probing_level` | integer | null | Probing level |

## Solution Types

The API returns a `solution_type` field which can be one of:

- `UNIQUE_LINE_SOLUTION`: Solution found using only line solving techniques
- `UNIQUE_DEPTH_SOLUTION`: Solution found using contradiction checking
- `UNIQUE_SOLUTION`: Solution proven to be unique
- `STOPPED_WITH_SOLUTION`: Solution found but uniqueness not checked
- `NON_GOAL_SOLUTION`: Found solution different from goal solution
- `MULTIPLE_SOLUTIONS`: Multiple solutions found
- `PARTIAL_SOLUTION`: Only partial solution found
- `NO_SOLUTION`: No solution exists
- `ALTERNATE_SOLUTION`: Additional solution found
- `CHECKING_FOR_MORE`: Found one solution, checking for more

## Supported File Formats

- `xml`: XML format
- `non`: NON format (WebPBN)
- `mk`: MK format
- `g`: G format
- `nin`: NIN format
- `cwd`: CWD format
- `lp`: LP format
- `pbm`: PBM format

## Example Usage

### Using cURL

```bash
# Solve a puzzle from a file
curl -X POST http://localhost:8000/api/solve \
  -F "file=@puzzle.xml" \
  -F "check_uniqueness=true" \
  -F "use_contradiction=true"

# Solve a puzzle from text
curl -X POST http://localhost:8000/api/solve/text \
  -F "puzzle=<puzzle content here>" \
  -F "format=xml" \
  -F "check_uniqueness=true"
```

### Using Python

```python
import requests

# Solve puzzle from file
with open('puzzle.xml', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/api/solve',
        files={'file': f},
        data={
            'check_uniqueness': 'true',
            'use_contradiction': 'true'
        }
    )
    
print(response.json())

# Solve puzzle from text
with open('puzzle.xml', 'r') as f:
    puzzle_text = f.read()
    
response = requests.post(
    'http://localhost:8000/api/solve/text',
    data={
        'puzzle': puzzle_text,
        'format': 'xml',
        'check_uniqueness': 'true'
    }
)

print(response.json())
```

## License

This project is based on the pbnsolve algorithm by Jan Wolter, which is licensed under the Apache License 2.0.