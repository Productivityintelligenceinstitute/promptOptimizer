from pathlib import Path
from pypdf import PdfReader
from docx import Document

def read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

def read_docx(path: Path) -> str:
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def read_file(path: Path) -> str:
    from constants.file_types import PDF_EXT, TEXT_EXTS, DOC_EXTS
    ext = path.suffix.lower()

    if ext == PDF_EXT:
        return read_pdf(path)
    if ext in DOC_EXTS:
        return read_docx(path)
    if ext in TEXT_EXTS:
        return read_text(path)

    raise ValueError(f"Unsupported file type: {path.name}")
