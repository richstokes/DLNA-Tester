# DLNA-Tester

A comprehensive DLNA/UPnP media server compliance testing tool. Tests servers for conformance with the DLNA and UPnP AV protocols.

## Features

- **Connectivity Tests**: Basic HTTP connection and device description discovery
- **Device Description Tests**: Validates UPnP device description XML, required fields, and service definitions
- **Content Directory Service Tests**: Tests Browse, Search, GetSearchCapabilities, GetSortCapabilities, and GetSystemUpdateID actions
- **Connection Manager Service Tests**: Tests GetProtocolInfo and protocol support
- **Browsing Tests**: Tests recursive browsing, pagination, and container navigation
- **Metadata Tests**: Validates DIDL-Lite metadata, item attributes, and UPnP class formats
- **Media Resource Tests**: Checks resource accessibility and range request support
- **Protocol Compliance Tests**: Tests error handling, HTTP HEAD support, and SOAP compliance

## Installation

Using `uv` (recommended):

```bash
cd DLNA-Tester
uv sync
```

Or install directly:

```bash
uv pip install -e .
```

## Usage

### Basic Usage

```bash
uv run dlna-tester <host> <port>
```

Example:
```bash
uv run dlna-tester 192.168.1.100 8200
```

### Options

- `-v, --verbose`: Show detailed output during tests
- `-t, --timeout SECONDS`: Set request timeout (default: 10s)
- `--no-color`: Disable colored output
- `--json`: Output results as JSON
- `--full-scan`: Traverse ALL containers and media items (slower but thorough)
- `--max-items N`: Maximum items to scan in full-scan mode (default: 1000)

### Examples

```bash
# Basic test (quick sample scan)
uv run dlna-tester 192.168.1.100 8200

# Verbose mode
uv run dlna-tester 192.168.1.100 8200 -v

# Full scan - traverse ALL media items (recommended for thorough testing)
uv run dlna-tester 192.168.1.100 8200 --full-scan

# Full scan with higher item limit
uv run dlna-tester 192.168.1.100 8200 --full-scan --max-items 5000

# With longer timeout
uv run dlna-tester 192.168.1.100 8200 --timeout 30

# JSON output (for scripting)
uv run dlna-tester 192.168.1.100 8200 --json

# Pipe-friendly (no colors)
uv run dlna-tester 192.168.1.100 8200 --no-color
```

## Test Categories

### Connectivity
- HTTP connection to server
- Device description XML discovery

### Device Description
- Device type validation (MediaServer)
- Required fields (friendlyName, manufacturer, modelName, UDN)
- UDN format validation
- Service definitions (ContentDirectory, ConnectionManager)
- Device icons

### Content Directory Service
- SCPD (Service Control Protocol Description) retrieval
- Required actions: Browse, GetSearchCapabilities, GetSortCapabilities, GetSystemUpdateID
- Optional actions: Search, CreateObject, DestroyObject, UpdateObject

### Connection Manager Service  
- SCPD retrieval
- GetProtocolInfo support
- HTTP streaming protocol (http-get)

### Browsing
- Root container browse (ObjectID=0)
- BrowseMetadata support
- Pagination (RequestedCount)
- **StartingIndex offset** (large result set navigation)
- Container navigation (recursive browsing)

### Metadata
- Required item attributes (id, title, class)
- Container childCount
- Media resources with protocolInfo
- **Resource duration** (required for audio/video items per DLNA spec)
- **Resource size** (recommended)
- **Audio metadata** (bitrate, sampleFrequency)
- **Video resolution**
- UPnP class format validation
- **Unicode/special character handling**
- **DLNA.ORG_PN** (profile names)
- **DLNA.ORG_OP** (seek operation flags)
- **DLNA.ORG_FLAGS** format validation (32 hex chars)

### Media Resources
- Resource URL accessibility
- HTTP HEAD support
- Range request support (for seeking)

### Protocol Compliance
- SOAP error handling
- HTTP HEAD requests
- XML Content-Type headers
- SystemUpdateID consistency

## Scoring

Each test contributes to an overall compliance score:
- **PASS**: Full points
- **WARN**: Half points
- **FAIL**: Zero points
- **SKIP**: Not counted

Grades are assigned based on percentage:
- **A+**: ≥95%
- **A**: ≥90%
- **B+**: ≥85%
- **B**: ≥80%
- **C+**: ≥75%
- **C**: ≥70%
- **D**: ≥60%
- **F**: <60%

## JSON Output Format

When using `--json`, the output includes:

```json
{
  "server": {"host": "...", "port": ...},
  "device": {
    "friendly_name": "...",
    "manufacturer": "...",
    "model_name": "...",
    "device_type": "..."
  },
  "summary": {
    "total": 42,
    "passed": 38,
    "failed": 2,
    "warned": 2,
    "skipped": 0,
    "score": 40.5,
    "max_score": 44.0,
    "percentage": 92.0,
    "grade": "A"
  },
  "results": [
    {
      "name": "HTTP Connection",
      "category": "Connectivity",
      "status": "PASS",
      "message": "Server responded with status 200",
      "details": {},
      "weight": 2.0
    }
  ]
}
```

## Exit Codes

- `0`: All tests passed (no failures)
- `1`: One or more tests failed
- `2`: Error (could not connect, invalid arguments, etc.)
- `130`: Interrupted by user (Ctrl+C)

## Programmatic Usage

```python
from dlna_tester import DLNATester, TestSuite

with DLNATester("192.168.1.100", 8200) as tester:
    suite = TestSuite(tester, verbose=True)
    results = suite.run_all_tests()
    
    score, max_score, grade = suite.get_score()
    print(f"Grade: {grade} ({score}/{max_score})")
    
    for result in results:
        print(f"{result.status.value}: {result.name}")
```

## License

MIT License - see [LICENSE](LICENSE) for details.
