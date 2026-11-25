"""Document parsing: file -> ordered segments with page, section and kind.
All parsing happens on this machine; nothing is sent anywhere."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class ParseError(Exception):
    pass


@dataclass
class Segment:
    page: int
    section: str
    text: str
    kind: str = "text"  # text | table


_MD_H = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_NUM_H = re.compile(r"^\s*(\d+(?:\.\d+)*[.)-]?|[أ-ي]\)|[٠-٩]+[.)-])\s+(\S.{1,90})$")


def _is_heading(line: str, numbered_ok: bool = True) -> str | None:
    s = line.strip()
    if not s or len(s) > 100:
        return None
    mh = _MD_H.match(s)
    if mh:
        return mh.group(2).strip(" #*")
    if s.endswith((":", "：")) and len(s) < 70 and "|" not in s and len(s.split()) <= 8:
        return s.rstrip(":： ")
    if s.isupper() and len(s.split()) <= 8 and len(s) > 3:
        return s
    mn = _NUM_H.match(s)
    if numbered_ok and mn and not s.endswith((".", "؛", "،")) and len(s.split()) <= 10 and not re.search(r"\d{4}", mn.group(2)):
        return s
    return None


def _table_text(rows: list[list[str]]) -> str:
    rows = [[(c or "").strip().replace("\n", " ") for c in r] for r in rows if any((c or "").strip() for c in r)]
    return "\n".join(" | ".join(r) for r in rows)


def _text_segments(text: str, page: int, section: str = "") -> tuple[list[Segment], str]:
    segs, buf, table = [], [], []

    def flush():
        nonlocal buf, table
        if buf:
            segs.append(Segment(page, section, "\n".join(buf).strip()))
            buf = []
        if table:
            segs.append(Segment(page, section, "\n".join(table), "table"))
            table = []

    lines = text.splitlines()
    numbered = [bool(_NUM_H.match(l.strip())) for l in lines]

    def neighbour(i, step):
        j = i + step
        while 0 <= j < len(lines) and not lines[j].strip():
            j += step
        return numbered[j] if 0 <= j < len(lines) else False

    for idx, line in enumerate(lines):
        if line.count("|") >= 2 or " | " in line:
            if re.fullmatch(r"[\s|:\-]+", line):
                continue
            if buf:
                flush()
            table.append(" | ".join(c.strip() for c in line.strip().strip("|").split("|")))
            continue
        if table:
            flush()
        # a numbered line inside a run of numbered lines is a list item, not a heading
        h = _is_heading(line, numbered_ok=not (neighbour(idx, 1) or neighbour(idx, -1)))
        if h:
            flush()
            section = h
            continue
        if line.strip():
            buf.append(line.strip())
        elif buf:
            flush()
    flush()
    return [s for s in segs if s.text], section


def parse_txt(path: Path) -> list[Segment]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1256", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    segs, section = [], ""
    for i, page in enumerate(text.split("\f"), 1):
        s, section = _text_segments(page, i, section)
        segs += s
    return segs


def parse_docx(path: Path) -> list[Segment]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    d = docx.Document(str(path))
    segs, section, page, buf = [], "", 1, []

    def flush():
        nonlocal buf
        if buf:
            segs.append(Segment(page, section, "\n".join(buf)))
            buf = []

    for child in d.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, d)
            text = p.text.strip()
            style = (p.style.name or "").lower() if p.style is not None else ""
            if text and (style.startswith("heading") or style.startswith("title") or "عنوان" in style):
                flush()
                section = text
            elif text:
                h = _is_heading(text) if len(text) < 80 and text.endswith(":") else None
                if h:
                    flush()
                    section = h
                else:
                    buf.append(text)
            if 'w:br w:type="page"' in child.xml or "lastRenderedPageBreak" in child.xml:
                flush()
                page += 1
        elif tag == "tbl":
            flush()
            t = Table(child, d)
            rows = []
            for r in t.rows:
                cells, seen = [], set()
                for c in r.cells:
                    if id(c._tc) in seen:
                        continue
                    seen.add(id(c._tc))
                    cells.append(c.text)
                rows.append(cells)
            txt = _table_text(rows)
            if txt:
                segs.append(Segment(page, section, txt, "table"))
    flush()
    return segs


def _ocr_pdf_page(path: Path, index: int) -> str:
    try:
        import pypdfium2
        import pytesseract
    except ImportError:
        return ""
    if not shutil.which("tesseract"):
        return ""
    pdf = pypdfium2.PdfDocument(str(path))
    img = pdf[index].render(scale=2.5).to_pil()
    try:
        return pytesseract.image_to_string(img, lang="ara+eng")
    except Exception:
        return pytesseract.image_to_string(img)


def parse_pdf(path: Path) -> list[Segment]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    segs, section, empty = [], "", 0
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if len(text) < 20:
            text = _ocr_pdf_page(path, i).strip()
            if len(text) < 20:
                empty += 1
                continue
        s, section = _text_segments(text, i + 1, section)
        segs += s
    if not segs and empty:
        raise ParseError("This PDF is scanned images and no OCR engine is installed on the server. "
                         "Install Tesseract with Arabic language data (tesseract-ocr, tesseract-ocr-ara) and re-index.")
    return segs


def parse_xlsx(path: Path) -> list[Segment]:
    import openpyxl
    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    segs = []
    for i, ws in enumerate(wb.worksheets, 1):
        rows = [["" if c is None else str(c) for c in row] for row in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(x.strip() for x in r)]
        for start in range(0, len(rows), 25):  # keep header with every slice
            part = rows[start:start + 25]
            if start and rows:
                part = [rows[0]] + part
            txt = _table_text(part)
            if txt:
                segs.append(Segment(i, ws.title, txt, "table"))
    return segs


def parse_pptx(path: Path) -> list[Segment]:
    from pptx import Presentation
    prs = Presentation(str(path))
    segs = []
    for i, slide in enumerate(prs.slides, 1):
        title = slide.shapes.title.text.strip() if slide.shapes.title is not None and slide.shapes.title.has_text_frame else f"Slide {i}"
        body = []
        for sh in slide.shapes:
            if sh.has_text_frame and sh != slide.shapes.title:
                t = "\n".join(p.text for p in sh.text_frame.paragraphs if p.text.strip())
                if t:
                    body.append(t)
            if getattr(sh, "has_table", False) and sh.has_table:
                txt = _table_text([[c.text for c in r.cells] for r in sh.table.rows])
                if txt:
                    segs.append(Segment(i, title, txt, "table"))
        if body or title:
            segs.append(Segment(i, title, "\n".join([title] + body)))
    return segs


def _convert_legacy(path: Path, target: str) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ParseError(f"Legacy {path.suffix} files need LibreOffice on the server to be converted. "
                         f"Install it, or save the file as .{target} and upload again.")
    out = Path(tempfile.mkdtemp())
    subprocess.run([soffice, "--headless", "--convert-to", target, "--outdir", str(out), str(path)],
                   check=True, capture_output=True, timeout=120)
    res = list(out.glob(f"*.{target}"))
    if not res:
        raise ParseError("LibreOffice could not convert this file.")
    return res[0]


MAGIC = {".pdf": b"%PDF", ".docx": b"PK", ".xlsx": b"PK", ".pptx": b"PK", ".doc": b"\xd0\xcf\x11\xe0", ".xls": b"\xd0\xcf\x11\xe0"}


def validate(path: Path, filename: str):
    ext = Path(filename).suffix.lower()
    head = path.read_bytes()[:8]
    if not head:
        raise ParseError("The file is empty.")
    sig = MAGIC.get(ext)
    if sig and not head.startswith(sig):
        raise ParseError(f"The file content does not match its {ext} extension.")


def parse(path: Path, filename: str) -> list[Segment]:
    ext = Path(filename).suffix.lower()
    validate(path, filename)
    try:
        if ext in (".txt", ".md", ".csv"):
            return parse_txt(path)
        if ext == ".docx":
            return parse_docx(path)
        if ext == ".pdf":
            return parse_pdf(path)
        if ext == ".xlsx":
            return parse_xlsx(path)
        if ext == ".pptx":
            return parse_pptx(path)
        if ext == ".doc":
            return parse_docx(_convert_legacy(path, "docx"))
        if ext == ".xls":
            return parse_xlsx(_convert_legacy(path, "xlsx"))
    except ParseError:
        raise
    except Exception as e:  # corrupt file, encrypted PDF, …
        raise ParseError(f"Could not read this file: {e}") from e
    raise ParseError(f"Unsupported file type {ext}")
