import asyncio

from app.core.domain import DomainError
from app.files.pdf import InvalidPdfError, PdfLimitExceededError, merge_pdf_content


class PypdfMerger:
    def __init__(self, max_pages, max_bytes):
        self.max_pages, self.max_bytes = max_pages, max_bytes

    async def merge(self, contents):
        try:
            return await asyncio.to_thread(
                merge_pdf_content,
                contents,
                max_pages=self.max_pages,
                max_output_bytes=self.max_bytes,
            )
        except InvalidPdfError as exc:
            raise DomainError("invalid_pdf") from exc
        except PdfLimitExceededError as exc:
            raise DomainError("pdf_limit_exceeded") from exc
