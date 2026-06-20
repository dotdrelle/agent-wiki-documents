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

Standalone:

```bash
cp .env.example .env
# Edit .env: set WORKSPACES_ROOT and MCP_AUTH_TOKEN.
docker compose up --build
```

Via `llm-wiki-manager` (recommended — starts all external agents together):

```bash
# manager/.env must have WORKSPACES_ROOT and DOCUMENTS_MCP_AUTH_TOKEN set
wiki-workspace agents up
```

Register the endpoint in `mcp.endpoints.json`:

```json
{
  "mcpServers": {
    "documents": {
      "url": "http://host.docker.internal:${DOCUMENTS_MCP_PORT:-3337}/mcp/",
      "headers": { "Authorization": "Bearer ${DOCUMENTS_MCP_AUTH_TOKEN}" }
    }
  }
}
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
<workspaces-root>/<workspace>/raw/untracked/
```

## Configuration

```bash
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"
export WORKSPACES_ROOT=/path/to/workspaces
export DOCUMENTS_MCP_PORT=3337
export DOCUMENT_INPUT_HOST_DIR=./documents/input
export DOCUMENT_MAX_UPLOAD_BYTES=52428800
export DOCUMENT_ENABLE_OCR=true
export DOCUMENT_OCR_LANG=eng+fra
```

`docker-compose.yml` mounts `${WORKSPACES_ROOT}` at `/workspaces`. When
`documents_convert_to_markdown` receives `workspace`, converted Markdown is ready
for `wiki ingest` in that workspace without a copy step.

## MCP Authentication

When running via `wiki-workspace agents up`, set `DOCUMENTS_MCP_AUTH_TOKEN` in
the manager's `.env`; it is mapped to `MCP_AUTH_TOKEN` inside the container.

For standalone start:

```bash
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"
docker compose up --build
```

MCP clients must send:

```txt
Authorization: Bearer <same-token>
```

If `MCP_AUTH_TOKEN` is empty, the server accepts unauthenticated requests.
Use that only for local debugging.

The conversion tool accepts either:

- `workspace`: optional target workspace. When set, output goes to that
  workspace's `raw/untracked/`.
- `filePath`: absolute path or path relative to the selected workspace or
  `DOCUMENT_INPUT_DIR`.
- `base64Content` plus `filename`: direct upload-style conversion.

Optional arguments:

- `outputFilename`: Markdown filename written under the workspace output
  directory or `DOCUMENT_OUTPUT_DIR` when no workspace is provided.
- `forceOcr`: force OCR for supported inputs.
- `includeMetadata`: include YAML front matter, defaults to true.
