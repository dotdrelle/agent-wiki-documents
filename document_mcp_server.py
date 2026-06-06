#!/usr/bin/env python3
"""Document ingestion MCP Server - convert files to Markdown with OCR fallback."""

import base64
import contextlib
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send
import uvicorn


app = Server("agent-wiki-documents")

_AGENT_VERSION = "0.5.1"
_MCP_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")
_DOCUMENT_INPUT_DIR = Path(os.environ.get("DOCUMENT_INPUT_DIR", "/documents/input")).resolve()
_DOCUMENT_OUTPUT_DIR = Path(os.environ.get("DOCUMENT_OUTPUT_DIR", "/documents/output")).resolve()
_MAX_UPLOAD_BYTES = int(os.environ.get("DOCUMENT_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
_OCR_LANG = os.environ.get("DOCUMENT_OCR_LANG", "eng+fra")
_ENABLE_OCR = os.environ.get("DOCUMENT_ENABLE_OCR", "true").lower() not in {"0", "false", "no"}

if not _MCP_TOKEN:
    print("[document-mcp] Warning: MCP_AUTH_TOKEN is not configured; the endpoint accepts unauthenticated clients.")


class _BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "GET" and _wants_html(request):
            return await call_next(request)
        if _MCP_TOKEN:
            auth = request.headers.get("authorization", "")
            if auth != f"Bearer {_MCP_TOKEN}":
                return PlainTextResponse("Unauthorized", status_code=401)
        return await call_next(request)


def _wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _json_text(payload: dict[str, Any]) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


def _render_landing_page(endpoint_url: str, scheme: str) -> str:
    auth_status = (
        "Bearer token enabled"
        if _MCP_TOKEN
        else "Warning: MCP_AUTH_TOKEN is not configured; the endpoint accepts unauthenticated clients."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>agent-wiki-documents MCP connector</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#f8fafc; --panel:#fff; --text:#111827; --muted:#64748b; --line:#d8dee8; --accent:#2563eb; --code:#eef2ff; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f172a; --panel:#111827; --text:#f8fafc; --muted:#94a3b8; --line:#253044; --accent:#60a5fa; --code:#1e293b; }} }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; min-height:100vh; background:var(--bg); color:var(--text); font:15px/1.55 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    main {{ width:min(920px,calc(100% - 32px)); margin:0 auto; padding:56px 0; }}
    .eyebrow {{ color:var(--accent); font-weight:700; letter-spacing:.04em; text-transform:uppercase; font-size:12px; }}
    h1 {{ margin:8px 0 10px; font-size:clamp(32px,6vw,52px); line-height:1.05; letter-spacing:0; }}
    h2 {{ margin:0 0 16px; font-size:20px; letter-spacing:0; }}
    .lead {{ margin:0 0 28px; color:var(--muted); max-width:720px; font-size:17px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:22px; margin:18px 0; }}
    dl {{ display:grid; grid-template-columns:170px 1fr; gap:10px 18px; margin:0; }}
    dt {{ color:var(--muted); }}
    dd {{ margin:0; min-width:0; overflow-wrap:anywhere; }}
    code {{ background:var(--code); border:1px solid var(--line); border-radius:6px; padding:2px 6px; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:13px; }}
    ul {{ list-style:none; margin:0; padding:0; display:grid; gap:10px; }}
    li {{ display:grid; grid-template-columns:minmax(170px,240px) 1fr; gap:14px; align-items:start; padding:12px 0; border-top:1px solid var(--line); }}
    li:first-child {{ border-top:0; padding-top:0; }}
    li span {{ color:var(--muted); }}
    @media (max-width:640px) {{ dl,li {{ grid-template-columns:1fr; }} main {{ padding:32px 0; }} }}
  </style>
</head>
<body>
  <main>
    <div class="eyebrow">MCP Streamable HTTP</div>
    <h1>agent-wiki-documents MCP connector</h1>
    <p class="lead">Document ingestion agent for converting PDF, Office, text and image files into Markdown.</p>
    <section class="panel">
      <dl>
        <dt>Status</dt><dd>Ready</dd>
        <dt>Version</dt><dd><code>{_escape_html(_AGENT_VERSION)}</code></dd>
        <dt>Endpoint</dt><dd><code>{_escape_html(endpoint_url)}</code></dd>
        <dt>Transport</dt><dd>MCP Streamable HTTP over {_escape_html(scheme.upper())}</dd>
        <dt>Authentication</dt><dd>{_escape_html(auth_status)}</dd>
        <dt>Input dir</dt><dd><code>{_escape_html(str(_DOCUMENT_INPUT_DIR))}</code></dd>
        <dt>Output dir</dt><dd><code>{_escape_html(str(_DOCUMENT_OUTPUT_DIR))}</code></dd>
        <dt>OCR</dt><dd>{_escape_html("enabled" if _ENABLE_OCR else "disabled")} / <code>{_escape_html(_OCR_LANG)}</code></dd>
      </dl>
    </section>
    <section class="panel">
      <h2>Available tools</h2>
      <ul>
        <li><code>documents_status</code><span>Check conversion runtime and available OCR tools.</span></li>
        <li><code>documents_convert_to_markdown</code><span>Convert one uploaded or mounted document to Markdown.</span></li>
      </ul>
    </section>
  </main>
</body>
</html>"""


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="documents_status",
            description="Check agent-wiki-documents configuration, directories and available conversion tools.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="documents_convert_to_markdown",
            description=(
                "Convert a PDF, Office document, text file or image to Markdown. Provide either filePath for a file "
                "mounted under DOCUMENT_INPUT_DIR, or base64Content plus filename for direct upload. OCR is used for "
                "images and PDF pages where direct text extraction is empty."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filePath": {
                        "type": "string",
                        "description": "Path to an input file, absolute or relative to DOCUMENT_INPUT_DIR.",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Original filename when base64Content is provided.",
                    },
                    "base64Content": {
                        "type": "string",
                        "description": "Base64 encoded file content for upload-style conversion.",
                    },
                    "outputFilename": {
                        "type": "string",
                        "description": "Optional Markdown output filename. Defaults to the input stem plus .md.",
                    },
                    "forceOcr": {
                        "type": "boolean",
                        "description": "Force OCR even if text extraction succeeds for supported types.",
                    },
                    "includeMetadata": {
                        "type": "boolean",
                        "description": "Include Markdown front matter metadata. Defaults to true.",
                    },
                },
                "additionalProperties": False,
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    start = time.time()
    print(f"[document-mcp] tools/call {name}")
    try:
        match name:
            case "documents_status":
                result = _tool_status()
            case "documents_convert_to_markdown":
                result = _tool_convert_to_markdown(arguments)
            case _:
                raise ValueError(f"Unknown tool: {name}")
        print(f"[document-mcp] tools/result {name} ok {int((time.time() - start) * 1000)}ms")
        return result
    except Exception as exc:
        print(f"[document-mcp] tools/result {name} error {int((time.time() - start) * 1000)}ms {exc}")
        return _json_text({"ok": False, "error": str(exc)})


def _tool_status() -> list[TextContent]:
    return _json_text(
        {
            "ok": True,
            "service": "agent-wiki-documents",
            "version": _AGENT_VERSION,
            "inputDir": str(_DOCUMENT_INPUT_DIR),
            "outputDir": str(_DOCUMENT_OUTPUT_DIR),
            "maxUploadBytes": _MAX_UPLOAD_BYTES,
            "ocr": {
                "enabled": _ENABLE_OCR,
                "lang": _OCR_LANG,
                "tesseractAvailable": bool(shutil.which("tesseract")),
                "pdftoppmAvailable": bool(shutil.which("pdftoppm")),
            },
            "office": {"libreOfficeAvailable": bool(shutil.which("libreoffice"))},
            "supportedExtensions": sorted(_SUPPORTED_EXTENSIONS),
        }
    )


def _tool_convert_to_markdown(args: dict[str, Any]) -> list[TextContent]:
    _DOCUMENT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    include_metadata = bool(args.get("includeMetadata", True))
    force_ocr = bool(args.get("forceOcr", False))

    with tempfile.TemporaryDirectory(prefix="agent-wiki-documents-") as tmpdir:
        source = _resolve_source(args, Path(tmpdir))
        markdown, method = _convert_file(source, Path(tmpdir), force_ocr=force_ocr)
        output_name = _safe_output_name(args.get("outputFilename"), source)
        output_path = _DOCUMENT_OUTPUT_DIR / output_name
        final_markdown = _with_metadata(markdown, source, method) if include_metadata else markdown
        output_path.write_text(final_markdown, encoding="utf-8")
        return _json_text(
            {
                "ok": True,
                "source": str(source),
                "outputPath": str(output_path),
                "method": method,
                "bytes": output_path.stat().st_size,
                "markdown": final_markdown,
            }
        )


def _resolve_source(args: dict[str, Any], tmpdir: Path) -> Path:
    file_path = str(args.get("filePath", "") or "").strip()
    base64_content = str(args.get("base64Content", "") or "").strip()
    if file_path and base64_content:
        raise ValueError("Provide either filePath or base64Content, not both.")
    if file_path:
        path = Path(file_path)
        if not path.is_absolute():
            path = _DOCUMENT_INPUT_DIR / path
        path = path.resolve()
        if not path.is_file():
            raise ValueError(f"Input file does not exist: {path}")
        return path
    if base64_content:
        filename = _safe_filename(str(args.get("filename", "") or "").strip() or "upload.bin")
        try:
            data = base64.b64decode(base64_content, validate=True)
        except Exception as exc:
            raise ValueError("base64Content is not valid base64.") from exc
        if len(data) > _MAX_UPLOAD_BYTES:
            raise ValueError(f"Upload is too large. Limit is {_MAX_UPLOAD_BYTES} bytes.")
        path = tmpdir / filename
        path.write_bytes(data)
        return path
    raise ValueError("Provide filePath or base64Content.")


_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".yaml", ".yml", ".html", ".htm", ".rtf"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
_OFFICE_EXTENSIONS = {".docx", ".pptx", ".xlsx", ".doc", ".ppt", ".xls", ".odt", ".ods", ".odp"}
_SUPPORTED_EXTENSIONS = _TEXT_EXTENSIONS | _IMAGE_EXTENSIONS | _OFFICE_EXTENSIONS | {".pdf"}


def _convert_file(path: Path, tmpdir: Path, force_ocr: bool) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix not in _SUPPORTED_EXTENSIONS:
        mime, _ = mimetypes.guess_type(path.name)
        raise ValueError(f"Unsupported file type: {suffix or mime or 'unknown'}")
    if suffix in _TEXT_EXTENSIONS:
        return _convert_text(path), "text"
    if suffix == ".docx":
        return _convert_docx(path), "docx-xml"
    if suffix in _OFFICE_EXTENSIONS:
        return _convert_office(path, tmpdir), "libreoffice-pdf"
    if suffix in _IMAGE_EXTENSIONS:
        return _ocr_image(path), "image-ocr"
    if suffix == ".pdf":
        text = "" if force_ocr else _extract_pdf_text(path)
        if text.strip():
            return _plain_text_to_markdown(text), "pdf-text"
        return _ocr_pdf(path, tmpdir), "pdf-ocr"
    raise ValueError(f"Unsupported file type: {suffix}")


def _convert_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    return text if path.suffix.lower() in {".md", ".markdown"} else _plain_text_to_markdown(text)


def _convert_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        parts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        line = "".join(parts).strip()
        if line:
            paragraphs.append(line)
    return "\n\n".join(paragraphs).strip() + "\n"


def _convert_office(path: Path, tmpdir: Path) -> str:
    libreoffice = shutil.which("libreoffice")
    if not libreoffice:
        raise ValueError("LibreOffice is required to convert this Office format.")
    subprocess.run(
        [libreoffice, "--headless", "--convert-to", "pdf", "--outdir", str(tmpdir), str(path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )
    pdf_path = tmpdir / f"{path.stem}.pdf"
    if not pdf_path.is_file():
        matches = list(tmpdir.glob("*.pdf"))
        if not matches:
            raise ValueError("LibreOffice did not produce a PDF output.")
        pdf_path = matches[0]
    text = _extract_pdf_text(pdf_path)
    return _plain_text_to_markdown(text) if text.strip() else _ocr_pdf(pdf_path, tmpdir)


def _extract_pdf_text(path: Path) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise ValueError("PyMuPDF is required for PDF text extraction.") from exc
    chunks: list[str] = []
    with fitz.open(path) as document:
        for page in document:
            text = page.get_text("text").strip()
            if text:
                chunks.append(text)
    return "\n\n".join(chunks)


def _ocr_pdf(path: Path, tmpdir: Path) -> str:
    _require_tesseract()
    if not shutil.which("pdftoppm"):
        raise ValueError("pdftoppm is required for PDF OCR.")
    image_prefix = tmpdir / "page"
    subprocess.run(
        ["pdftoppm", "-r", "200", "-png", str(path), str(image_prefix)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=180,
    )
    page_text: list[str] = []
    for image in sorted(tmpdir.glob("page-*.png")):
        text = _run_tesseract(image)
        if text.strip():
            page_text.append(text.strip())
    return _plain_text_to_markdown("\n\n".join(page_text))


def _ocr_image(path: Path) -> str:
    _require_tesseract()
    return _plain_text_to_markdown(_run_tesseract(path))


def _require_tesseract() -> None:
    if not _ENABLE_OCR:
        raise ValueError("OCR is disabled by DOCUMENT_ENABLE_OCR=false.")
    if not shutil.which("tesseract"):
        raise ValueError("tesseract is required for OCR.")


def _run_tesseract(path: Path) -> str:
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", _OCR_LANG],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )
    return result.stdout


def _plain_text_to_markdown(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            blocks.append(" ".join(current))
            current = []
    if current:
        blocks.append(" ".join(current))
    return "\n\n".join(blocks).strip() + "\n"


def _with_metadata(markdown: str, source: Path, method: str) -> str:
    title = source.stem.replace("_", " ").replace("-", " ").strip() or source.name
    front_matter = {
        "title": title,
        "source_file": source.name,
        "conversion_method": method,
        "service": "agent-wiki-documents",
        "service_version": _AGENT_VERSION,
    }
    lines = ["---"]
    for key, value in front_matter.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + markdown


def _safe_output_name(value: Any, source: Path) -> str:
    filename = _safe_filename(str(value or "").strip() or f"{source.stem}.md")
    if not filename.lower().endswith(".md"):
        filename = f"{Path(filename).stem}.md"
    return filename


def _safe_filename(value: str) -> str:
    name = Path(value).name
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", ".", " "} else "_" for char in name).strip()
    return cleaned or "document"


def create_starlette_app() -> Starlette:
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8080"))
    streamable_http = StreamableHTTPSessionManager(
        app=app,
        event_store=None,
        json_response=False,
        stateless=True,
    )

    async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if path not in {"/mcp", "/mcp/"}:
            response = PlainTextResponse("Not found", status_code=404)
            await response(scope, receive, send)
            return
        request = Request(scope, receive)
        if request.method == "GET" and _wants_html(request):
            scheme = "https" if request.url.scheme == "https" else "http"
            endpoint_url = f"{scheme}://{request.headers.get('host', f'{host}:{port}')}/mcp/"
            response = HTMLResponse(_render_landing_page(endpoint_url, scheme))
            await response(scope, receive, send)
            return

        mcp_scope = dict(scope)
        mcp_scope["path"] = "/"
        mcp_scope["root_path"] = f"{scope.get('root_path', '').rstrip('/')}/mcp"
        await streamable_http.handle_request(mcp_scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with streamable_http.run():
            yield

    middleware = [
        Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
        Middleware(_BearerAuthMiddleware),
    ]
    return Starlette(routes=[Mount("/", app=handle_mcp)], middleware=middleware, lifespan=lifespan)


def main() -> None:
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8080"))
    _DOCUMENT_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    _DOCUMENT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[document-mcp] Streamable HTTP on http://{host}:{port}/mcp")
    uvicorn.run(create_starlette_app(), host=host, port=port)


if __name__ == "__main__":
    main()
