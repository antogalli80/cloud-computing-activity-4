from app.core.audit import DatabaseAudit
from app.core.domain import Context, DomainError
from app.exception_handlers import build_error_response

ERRORS = {
    "invalid_credentials": (401, "The supplied credentials are invalid."),
    "invalid_session": (401, "The session token is invalid or has been revoked."),
    "session_expired": (401, "The session has expired."),
    "active_session_exists": (409, "An active session already exists for this user."),
    "user_already_exists": (409, "A user with this identity already exists."),
    "file_not_found": (404, "The requested file was not found."),
    "file_content_missing": (409, "All source files must have content."),
    "invalid_merge_sources": (422, "Provide 2-10 distinct positive IDs."),
    "invalid_pdf": (415, "Sources must be readable, unencrypted PDFs."),
    "pdf_limit_exceeded": (413, "PDF size or page limit exceeded."),
    "upload_too_large": (413, "Upload limit exceeded."),
    "authentication_unavailable": (503, "Authentication is temporarily unavailable."),
    "content_unavailable": (503, "Content is temporarily unavailable."),
    "content_integrity_failure": (503, "Content integrity verification failed."),
}


async def domain_error_handler(request, exception: DomainError):
    code, message = ERRORS.get(exception.code, (500, "The operation could not be completed."))
    await DatabaseAudit("api").record(
        exception.code,
        Context(request.state.request_id),
        actor_id=getattr(request.state, "actor_id", None),
        outcome="rejected",
    )
    return build_error_response(request, code, exception.code, message)
