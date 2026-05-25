# agent-wiki-documents

Document ingestion MCP server for wiki workflows.

It converts PDF, Office, text and image files to Markdown. OCR is used for
images and for PDFs where direct text extraction returns no useful text.

## Tools

| Tool | Purpose |
| --- | --- |
| `documents_status` | Check runtime configuration and available converters. |
| `documents_convert_to_markdown` | Convert one mounted file or base64 upload to Markdown. |

## Supported Inputs

- PDF: direct text extraction first, OCR fallback.
- Office: `docx` is parsed directly; other Office/OpenDocument files are
  converted through LibreOffice and then extracted as PDF.
- Text: `txt`, `md`, `csv`, `json`, `xml`, `yaml`, `html`, `rtf`.
- Images: `png`, `jpg`, `jpeg`, `tif`, `tiff`, `bmp`, `webp` through OCR.

## Run Locally

```bash
cp .env.example .env
# Edit .env and set WIKI_WORKSPACE_PATH + MCP_AUTH_TOKEN.
docker compose up --build
```

The MCP endpoint is:

```txt
http://localhost:3337/mcp/
```

Mounted input files go in:

```txt
documents/input/
```

Generated Markdown files are written to:

```txt
<wiki-workspace>/raw/untracked/
```

## Configuration

```bash
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"
export WIKI_WORKSPACE_PATH=/path/to/initialized/wiki-workspace
export DOCUMENTS_MCP_PORT=3337
export DOCUMENT_INPUT_HOST_DIR=./documents/input
export DOCUMENT_MAX_UPLOAD_BYTES=52428800
export DOCUMENT_ENABLE_OCR=true
export DOCUMENT_OCR_LANG=eng+fra
```

`docker-compose.yml` mounts `${WIKI_WORKSPACE_PATH}/raw/untracked` as the
container output directory. Converted Markdown is therefore ready for
`wiki ingest` without a copy step.

## MCP Authentication

Set `MCP_AUTH_TOKEN` before starting the container:

```bash
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"
docker compose up --build
```

MCP clients must send this HTTP header:

```txt
Authorization: Bearer <same-token>
```

If `MCP_AUTH_TOKEN` is empty, the server accepts unauthenticated MCP requests.
Use that only for local debugging.

The conversion tool accepts either:

- `filePath`: absolute path or path relative to `DOCUMENT_INPUT_DIR`.
- `base64Content` plus `filename`: direct upload-style conversion.

Optional arguments:

- `outputFilename`: Markdown filename written under `DOCUMENT_OUTPUT_DIR`.
- `forceOcr`: force OCR for supported inputs.
- `includeMetadata`: include YAML front matter, defaults to true.
