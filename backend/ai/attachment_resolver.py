"""Backward-compatible import path for assistant attachments."""

from backend.ai.def_attachments import AttachmentResolver, get_attachment_definitions

__all__ = ["AttachmentResolver", "get_attachment_definitions"]
