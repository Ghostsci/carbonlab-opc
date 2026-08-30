"""Fail-closed document text reading and structured field extraction."""

from __future__ import annotations

import csv
import datetime as dt
import io
import math
import unicodedata
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class DocumentType(str, Enum):
    INVOICE = "invoice"
    ELECTRICITY_BILL = "electricity_bill"
    PRODUCTION_REPORT = "production_report"
    UNKNOWN = "unknown"


@dataclass
class OCRResult:
    document_type: DocumentType
    fields: dict[str, str]
    confidence: float
    raw_text: str
    tables: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    read_status: str = "read"
    reader: str = "unknown"


class DocumentReadError(ValueError):
    """The supplied file is malformed, unsafe, or not valid for its suffix."""


class DocumentReaderUnavailable(ValueError):
    """The file may be valid, but no safe reader is configured for it."""


class OCRService:
    """Read supported business documents without inventing OCR output.

    UTF-8 text, text-layer PDFs, and XLSX workbooks are read locally. Image
    documents deliberately abstain until a real OCR adapter is configured;
    binary placeholder text is never returned as document content.
    """

    MAX_FILE_BYTES = 10 * 1024 * 1024
    # Text-layer PDFs and structured workbooks have different density and
    # memory profiles. Keep the PDF boundary conservative while allowing a
    # governed 1,000-row business workbook without removing XLSX safeguards.
    MAX_PDF_EXTRACTED_CHARS = 100_000
    MAX_XLSX_EXTRACTED_CHARS = 250_000
    MAX_PDF_PAGES = 50
    MAX_XLSX_SHEETS = 20
    MAX_XLSX_ROWS_PER_SHEET = 5_000
    MAX_XLSX_COLUMNS = 100
    MAX_XLSX_ARCHIVE_MEMBERS = 2_000
    MAX_XLSX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024

    def __init__(self, use_llm_fallback: bool = True):
        # Kept for API compatibility. Unsafe implicit LLM/OCR fallback is not
        # used; callers must configure a real image OCR adapter explicitly.
        self.use_llm_fallback = use_llm_fallback

    def process(
        self,
        file_path: str | Path,
        doc_type_hint: DocumentType | None = None,
    ) -> OCRResult:
        path = Path(file_path)
        if not path.exists():
            return self._failed_result(
                f"File not found: {file_path}",
                read_status="reject",
                reader="failed",
            )
        if not path.is_file():
            return self._failed_result(
                "Document path is not a regular file.",
                read_status="reject",
                reader="failed",
            )

        try:
            text, reader = self._extract_text(path)
        except DocumentReaderUnavailable as exc:
            return self._failed_result(
                str(exc),
                read_status="abstain",
                reader="unavailable",
            )
        except DocumentReadError as exc:
            return self._failed_result(
                str(exc),
                read_status="reject",
                reader="failed",
            )
        except OSError:
            return self._failed_result(
                "Document could not be read.",
                read_status="reject",
                reader="failed",
            )

        if not text.strip():
            return self._failed_result(
                "No text extracted from document.",
                read_status="abstain",
                reader=reader,
            )

        doc_type = doc_type_hint or self._detect_type(text)
        if doc_type == DocumentType.UNKNOWN:
            return OCRResult(
                document_type=DocumentType.UNKNOWN,
                fields={},
                confidence=0,
                raw_text=text,
                errors=["Document type could not be determined; no fields were extracted."],
                read_status="abstain",
                reader=reader,
            )

        try:
            fields = extract_fields(text, doc_type)
        except ValueError as exc:
            return OCRResult(
                document_type=doc_type,
                fields={},
                confidence=0,
                raw_text=text,
                errors=[str(exc)],
                read_status="abstain",
                reader=reader,
            )
        except Exception:
            return OCRResult(
                document_type=doc_type,
                fields={},
                confidence=0,
                raw_text=text,
                errors=["Structured field extraction failed."],
                read_status="reject",
                reader=reader,
            )
        confidence = self._estimate_confidence(text, fields, doc_type)
        if not any(value.strip() for value in fields.values()):
            return OCRResult(
                document_type=doc_type,
                fields=fields,
                confidence=0,
                raw_text=text,
                errors=["No supported structured fields were extracted."],
                read_status="abstain",
                reader=reader,
            )

        return OCRResult(
            document_type=doc_type,
            fields=fields,
            confidence=round(confidence, 1),
            raw_text=text,
            tables=self._extract_tables(text),
            read_status="read",
            reader=reader,
        )

    def _failed_result(
        self,
        error: str,
        *,
        read_status: str,
        reader: str,
    ) -> OCRResult:
        return OCRResult(
            document_type=DocumentType.UNKNOWN,
            fields={},
            confidence=0,
            raw_text="",
            errors=[error],
            read_status=read_status,
            reader=reader,
        )

    def _extract_text(self, path: Path) -> tuple[str, str]:
        try:
            file_size = path.stat().st_size
        except OSError as exc:
            raise DocumentReadError("Document metadata could not be read.") from exc
        if file_size > self.MAX_FILE_BYTES:
            raise DocumentReadError("Document exceeds the 10 MB processing limit.")

        suffix = path.suffix.lower()
        if suffix in {".txt", ".csv"}:
            try:
                content = path.read_bytes()
            except OSError as exc:
                raise DocumentReadError("Text document could not be read.") from exc
            return self._decode_text(content), "text"
        if suffix == ".pdf":
            return self._extract_pdf(path), "pypdf"
        if suffix == ".xlsx":
            return self._extract_xlsx(path), "openpyxl"
        if suffix == ".xls":
            raise DocumentReaderUnavailable(
                "Legacy .xls reader is not configured; convert the file to .xlsx or CSV."
            )
        if suffix in {".png", ".jpg", ".jpeg"}:
            raise DocumentReaderUnavailable(
                "Image OCR is not configured; the document requires OCR or human review."
            )
        raise DocumentReaderUnavailable(
            f"No document reader is configured for {suffix or 'this file type'}."
        )

    def _decode_text(self, content: bytes) -> str:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentReadError("Text document is not valid UTF-8.") from exc
        self._validate_text(text, source="Text document")
        return text

    def _validate_text(self, text: str, *, source: str) -> None:
        if "\x00" in text:
            raise DocumentReadError(f"{source} contains binary NUL bytes.")
        control_count = sum(
            1
            for character in text
            if unicodedata.category(character) == "Cc"
            and character not in {"\n", "\r", "\t"}
        )
        if control_count:
            raise DocumentReadError(f"{source} contains binary control characters.")

    def _extract_pdf(self, path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise DocumentReaderUnavailable(
                "PDF text reader is not installed; pypdf is required."
            ) from exc

        try:
            reader = PdfReader(str(path), strict=True)
            if reader.is_encrypted:
                raise DocumentReadError("Encrypted PDF cannot be processed.")
            if len(reader.pages) > self.MAX_PDF_PAGES:
                raise DocumentReadError(
                    f"PDF exceeds the {self.MAX_PDF_PAGES}-page processing limit."
                )

            page_texts: list[str] = []
            extracted_chars = 0
            for page in reader.pages:
                page_text = page.extract_text() or ""
                extracted_chars += len(page_text) + 1
                if extracted_chars > self.MAX_PDF_EXTRACTED_CHARS:
                    raise DocumentReadError("PDF extracted text exceeds the processing limit.")
                page_texts.append(page_text)
        except (DocumentReadError, DocumentReaderUnavailable):
            raise
        except Exception as exc:
            raise DocumentReadError("PDF is malformed or unreadable.") from exc

        text = "\n".join(page_texts)
        if not text.strip():
            raise DocumentReaderUnavailable(
                "PDF has no readable text layer; image OCR or human review is required."
            )
        self._validate_text(text, source="PDF text layer")
        return text

    def _extract_xlsx(self, path: Path) -> str:
        self._validate_xlsx_archive(path)
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise DocumentReaderUnavailable(
                "XLSX reader is not installed; openpyxl is required."
            ) from exc

        try:
            workbook = load_workbook(
                filename=path,
                read_only=True,
                data_only=True,
                keep_links=False,
            )
        except Exception as exc:
            raise DocumentReadError("XLSX workbook is malformed or unreadable.") from exc

        lines: list[str] = []
        extracted_chars = 0
        try:
            if len(workbook.worksheets) > self.MAX_XLSX_SHEETS:
                raise DocumentReadError(
                    f"XLSX exceeds the {self.MAX_XLSX_SHEETS}-sheet processing limit."
                )

            for worksheet in workbook.worksheets:
                if worksheet.max_row and worksheet.max_row > self.MAX_XLSX_ROWS_PER_SHEET:
                    raise DocumentReadError(
                        "XLSX exceeds the row-per-sheet processing limit."
                    )
                if worksheet.max_column and worksheet.max_column > self.MAX_XLSX_COLUMNS:
                    raise DocumentReadError(
                        "XLSX exceeds the column-per-sheet processing limit."
                    )

                sheet_lines: list[str] = []
                for row_index, row in enumerate(
                    worksheet.iter_rows(values_only=True),
                    start=1,
                ):
                    if row_index > self.MAX_XLSX_ROWS_PER_SHEET:
                        raise DocumentReadError(
                            "XLSX exceeds the row-per-sheet processing limit."
                        )
                    if len(row) > self.MAX_XLSX_COLUMNS:
                        raise DocumentReadError(
                            "XLSX exceeds the column-per-sheet processing limit."
                        )
                    cells = [self._cell_text(value) for value in row]
                    if not any(cells):
                        continue
                    line = self._csv_line(cells)
                    sheet_lines.append(line)
                    extracted_chars += len(line) + 1
                    if extracted_chars > self.MAX_XLSX_EXTRACTED_CHARS:
                        raise DocumentReadError(
                            "XLSX extracted text exceeds the processing limit."
                        )

                if sheet_lines:
                    title = str(worksheet.title).replace("\r", " ").replace("\n", " ")
                    heading = f"[Sheet: {title}]"
                    lines.append(heading)
                    lines.extend(sheet_lines)
                    extracted_chars += len(heading) + 1
                    if extracted_chars > self.MAX_XLSX_EXTRACTED_CHARS:
                        raise DocumentReadError(
                            "XLSX extracted text exceeds the processing limit."
                        )
        finally:
            workbook.close()

        text = "\n".join(lines)
        self._validate_text(text, source="XLSX content")
        return text

    def _validate_xlsx_archive(self, path: Path) -> None:
        try:
            with zipfile.ZipFile(path) as archive:
                members = archive.infolist()
                names = {member.filename for member in members}
                if len(members) > self.MAX_XLSX_ARCHIVE_MEMBERS:
                    raise DocumentReadError("XLSX archive contains too many members.")
                if any(member.flag_bits & 0x1 for member in members):
                    raise DocumentReadError("Encrypted XLSX workbooks cannot be processed.")
                if sum(member.file_size for member in members) > self.MAX_XLSX_UNCOMPRESSED_BYTES:
                    raise DocumentReadError("XLSX archive expands beyond the processing limit.")
                required_members = {"[Content_Types].xml", "xl/workbook.xml"}
                if not required_members.issubset(names):
                    raise DocumentReadError("XLSX archive is missing required workbook data.")
        except DocumentReadError:
            raise
        except (OSError, zipfile.BadZipFile) as exc:
            raise DocumentReadError("XLSX workbook is malformed or unreadable.") from exc

    def _cell_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, dt.datetime):
            return value.isoformat(sep=" ", timespec="seconds")
        if isinstance(value, dt.date):
            return value.isoformat()
        if isinstance(value, float):
            return format(value, ".15g") if math.isfinite(value) else ""
        return str(value).replace("\r", " ").replace("\n", " ")

    def _csv_line(self, cells: list[str]) -> str:
        output = io.StringIO()
        csv.writer(output, lineterminator="").writerow(cells)
        return output.getvalue()

    def _detect_type(self, text: str) -> DocumentType:
        normalized = text.casefold()
        signals = {
            DocumentType.INVOICE: ("发票代码", "发票号码", "价税合计", "invoice"),
            DocumentType.ELECTRICITY_BILL: (
                "电费",
                "用电量",
                "有功电量",
                "总电量",
                "kwh",
                "kw·h",
                "供电公司",
            ),
            DocumentType.PRODUCTION_REPORT: (
                "生产报表",
                "生产报告",
                "合格产量",
                "生产产量",
                "产量",
                "产出",
            ),
        }
        scores = {
            document_type: sum(keyword in normalized for keyword in keywords)
            for document_type, keywords in signals.items()
        }
        best_type = max(scores, key=scores.get)
        return best_type if scores[best_type] else DocumentType.UNKNOWN

    def _estimate_confidence(
        self,
        text: str,
        fields: dict[str, str],
        doc_type: DocumentType | None = None,
    ) -> float:
        del text  # Reserved for a future reader-quality signal.
        if not fields:
            return 0.0
        populated = sum(1 for value in fields.values() if value.strip())
        if not populated:
            return 0.0

        confidence = min(95.0, (populated / len(fields)) * 100)
        if doc_type == DocumentType.ELECTRICITY_BILL:
            if not fields.get("electricity_kwh"):
                confidence = min(confidence, 40.0)
            elif not fields.get("period"):
                confidence = min(confidence, 60.0)
        elif doc_type == DocumentType.PRODUCTION_REPORT:
            if not fields.get("production_output"):
                confidence = min(confidence, 40.0)
        return confidence

    def _extract_tables(self, text: str) -> list[dict[str, Any]]:
        """Reserved for a future layout-aware table adapter."""
        del text
        return []


_ocr_service = OCRService()


def extract_fields(text: str, doc_type: DocumentType) -> dict[str, str]:
    from backend.ai.extractors import (
        ElectricityBillExtractor,
        InvoiceExtractor,
        ProductionReportExtractor,
    )

    if doc_type == DocumentType.INVOICE:
        return InvoiceExtractor().extract(text)
    if doc_type == DocumentType.ELECTRICITY_BILL:
        return ElectricityBillExtractor().extract(text)
    if doc_type == DocumentType.PRODUCTION_REPORT:
        return ProductionReportExtractor().extract(text)
    return {}
