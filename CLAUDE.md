# agent-wiki-documents

`agent-wiki-documents` is an external MCP Streamable HTTP server for document
ingestion. It converts PDFs, Office files, text files and images into Markdown
for wiki ingestion workflows.

## Files

- `document_mcp_server.py`: Starlette/uvicorn MCP server with bearer-auth
  middleware and conversion tools.
- `Dockerfile`: runtime image with LibreOffice, Poppler and Tesseract OCR.
- `docker-compose.yml`: standalone local service on port `3337` by default.
- `documents/input`: mounted input directory for local files.
- `DOCUMENT_OUTPUT_DIR`: container output directory mounted to the configured
  wiki workspace `raw/untracked` path by `docker-compose.yml`.

## Tools

- `documents_status`: checks configuration and converter availability.
- `documents_convert_to_markdown`: converts one file to Markdown from either a
  mounted `filePath` or `base64Content` plus `filename`.

## Safety

Do not expose this service publicly without `MCP_AUTH_TOKEN`. Uploaded and
converted documents may contain sensitive information; keep input and output
volumes local or encrypted in production.

Set `WIKI_WORKSPACE_PATH` before `docker compose up`; generated Markdown is
written directly to `${WIKI_WORKSPACE_PATH}/raw/untracked`.
