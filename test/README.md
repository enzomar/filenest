# FileNest API Tests with HTTPie

This folder contains simple HTTPie scripts and a dummy file to test the FileNest API and the S3-compatible API endpoints.

## Structure

- `dummyfile.txt` — A small text file used for file upload tests.
- `test_filenest.sh` — Script to test FileNest original API endpoints.
- `test_s3.sh` — Script to test the S3-compatible API endpoints.
- `README.md` — This file.

## Prerequisites

- [HTTPie](https://httpie.io/) installed on your system.
- (Optional) `jq` installed for JSON parsing in shell scripts.

### Installing HTTPie

- **Ubuntu/Debian:** `sudo apt install httpie`
- **macOS:** `brew install httpie`
- **Windows:** Use Chocolatey `choco install httpie` or pip `pip install --user httpie`

### Installing jq (optional)

- **Ubuntu/Debian:** `sudo apt install jq`
- **macOS:** `brew install jq`
- **Windows:** `choco install jq`

## Usage

Make sure your FileNest API server is running locally (default `http://localhost:8000`).

Run the tests by executing:

```bash
chmod +x test_filenest.sh test_s3.sh
./test_filenest.sh
./test_s3.sh
```

The scripts will:

- Upload a file
- Retrieve metadata
- Search records
- Delete the uploaded file
- (For S3) Perform basic bucket and object operations

## Notes

Update the API key and endpoint URLs in the scripts if different from defaults.
Scripts are designed for demonstration and simple testing, not for production.