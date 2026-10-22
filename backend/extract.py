"""Document ingestion: text, PDF, DOCX, XLSX, PPTX. Scanned PDFs use vision OCR when possible."""
import asyncio
import io
import zipfile

from fastapi import HTTPException, UploadFile

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_DOC_CHARS = 20000
TEXT_EXTENSIONS = {
    "txt", "md", "markdown", "csv", "tsv", "json", "log", "yaml", "yml", "xml", "html", "css",
    "js", "jsx", "ts", "tsx", "py", "java", "c", "cpp", "h", "go", "rs", "sql", "sh", "rb", "php",
    "ini", "toml",
}


def _read_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("This PDF is password protected.")
    parts, total = [], 0
    for page in reader.pages[:150]:
        t = page.extract_text() or ""
        parts.append(t)
        total += len(t)
        if total > MAX_DOC_CHARS * 2:
            break
    return "\n\n".join(parts)


def _read_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text)


def _read_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    lines = []
    for sheet in wb.worksheets[:8]:
        lines.append(f"# Sheet: {sheet.title}")
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i > 200:
                lines.append("…")
                break
            vals = ["" if c is None else str(c) for c in row[:20]]
            if any(vals):
                lines.append("\t".join(vals))
    return "\n".join(lines)


def _read_pptx(data: bytes) -> str:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    parts = []
    for i, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                texts.append(shape.text)
        if texts:
            parts.append(f"# Slide {i}\n" + "\n".join(texts))
    return "\n\n".join(parts)


def looks_like_office_zip(data: bytes) -> bool:
    return data[:2] == b"PK" and zipfile.is_zipfile(io.BytesIO(data))


async def extract_bytes(name: str, data: bytes, content_type: str = "") -> dict:
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 10 MB.")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    try:
        if ext == "pdf":
            text = await asyncio.to_thread(_read_pdf, data)
        elif ext == "docx":
            text = await asyncio.to_thread(_read_docx, data)
        elif ext in {"xlsx", "xlsm"}:
            text = await asyncio.to_thread(_read_xlsx, data)
        elif ext == "pptx":
            text = await asyncio.to_thread(_read_pptx, data)
        elif ext in TEXT_EXTENSIONS or content_type.startswith("text/"):
            text = data.decode("utf-8", errors="replace")
        else:
            raise HTTPException(
                status_code=415,
                detail="This file type is not supported. Try PDF, DOCX, XLSX, PPTX, text, code, CSV or an image.",
            )
    except HTTPException:
        raise
    except Exception as e:
        detail = str(e) if isinstance(e, ValueError) else "Could not read this file."
        raise HTTPException(status_code=422, detail=detail)

    text = text.replace("\x00", "").strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail="No readable text found. For scanned PDFs, attach a photo of the page instead.",
        )
    return {
        "name": name[:120],
        "text": text[:MAX_DOC_CHARS],
        "truncated": len(text) > MAX_DOC_CHARS,
        "chars": len(text),
    }


async def extract_upload(file: UploadFile) -> dict:
    name = (file.filename or "file")[:120]
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    return await extract_bytes(name, data, file.content_type or "")
