"""Midia generativa local do Condor."""

from .intent import extract_image_prompt, is_image_request
from .local_image import LocalImageGenerator

__all__ = ["LocalImageGenerator", "extract_image_prompt", "is_image_request"]
