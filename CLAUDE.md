# agent-wiki-documents

`agent-wiki-documents` is an external MCP Streamable HTTP server for document
ingestion. It converts PDFs, Office files, text files and images into Markdown
for wiki ingestion workflows.

## Files

- `document_mcp_server.py`: Starlette/uvicorn MCP server with bearer-auth
  middleware and conversion tools.
- `Dockerfile`: runtime image with MarkItDown, Poppler and LLM OCR support.
- `docker-compose.yml`: standalone local service on port `3337` by default.
- `documents/input`: mounted input directory for local files.
- `WORKSPACES_ROOT`: container root for all workspaces. When a conversion call
  includes `workspace`, output is written to
  `/workspaces/<workspace>/raw/untracked/`.
- `DOCUMENT_OUTPUT_DIR`: fallback output directory for inline/no-workspace
  conversions.

## Tools

- `documents_status`: checks configuration and converter availability.
- `documents_convert_to_markdown`: converts one file to Markdown from either a
  mounted `filePath` or `base64Content` plus `filename`.

## Safety

Do not expose this service publicly without `MCP_AUTH_TOKEN`. Uploaded and
converted documents may contain sensitive information; keep input and output
volumes local or encrypted in production.

Set `WORKSPACES_ROOT` before `docker compose up`; generated Markdown is written
to the workspace selected by the `workspace` tool argument.

Keep `_AGENT_VERSION` aligned with the coordinated `llm-wiki-manager` release
version so status responses identify the deployed agent bundle. Current release
line: `0.7.0`.

MCP tool descriptions, `_activity` metadata, conversion progress labels,
status/correction pages, and operator-facing errors must stay in English. OCR
and image-to-Markdown prompts may instruct the LLM to preserve the original
document language, but the service UI itself is not localized from `.wikirc`.
