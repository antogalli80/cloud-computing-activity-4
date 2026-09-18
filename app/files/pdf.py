from io import BytesIO

from pypdf import PdfReader, PdfWriter


class InvalidPdfError(Exception):
    """Raised when a source is not a readable, unencrypted PDF."""


class PdfLimitExceededError(Exception):
    """Raised when PDF processing exceeds configured resource limits."""


def merge_pdf_content(
    sources: list[bytes],
    *,
    max_pages: int,
    max_output_bytes: int,
) -> bytes:
    """Validate and merge PDF byte sequences in their requested order."""

    writer = PdfWriter()
    page_count = 0
    try:
        for content in sources:
            if not content.startswith(b"%PDF-"):
                raise InvalidPdfError
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted or not reader.pages:
                raise InvalidPdfError
            page_count += len(reader.pages)
            if page_count > max_pages:
                raise PdfLimitExceededError
            for page in reader.pages:
                writer.add_page(page)

        destination = BytesIO()
        writer.write(destination)
        merged = destination.getvalue()
    except (InvalidPdfError, PdfLimitExceededError):
        raise
    except Exception as exception:
        raise InvalidPdfError from exception

    if len(merged) > max_output_bytes:
        raise PdfLimitExceededError
    return merged
