"""Architecture-document parsing and normalization."""

from .parser import DocumentError, parse_architecture_documents, render_review_report

__all__ = ["DocumentError", "parse_architecture_documents", "render_review_report"]
