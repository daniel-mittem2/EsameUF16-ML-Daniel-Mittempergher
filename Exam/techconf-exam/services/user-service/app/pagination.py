"""Pagination parsing and slicing helpers for the user-service.

``parse_pagination_params`` extracts ``page`` and ``page_size`` from the query
arguments, applying the contract defaults (``page=1``, ``page_size=20``) and
validating type and range. Empty, non-numeric, or non-integer values raise
``PaginationError`` which the routes layer converts to 422 (REQ-USR-F06).

``paginate`` slices a list into a page and reports ``total`` as the pre-slice
length (REQ-USR-F06-AC7, REQ-USR-B03-AC4).
"""
from __future__ import annotations

from typing import List, Tuple

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MIN_PAGE = 1
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 100


class PaginationError(ValueError):
    """Raised when a pagination parameter is invalid (maps to 422)."""


def _parse_int_param(args, name: str, default: int) -> int:
    """Parse a single query parameter as a strict integer.

    Rejects missing-but-empty strings, non-numeric values, and non-integer
    numeric strings (e.g. ``1.5``). Absent parameters fall back to ``default``.
    """
    raw = args.get(name)
    if raw is None:
        return default
    if isinstance(raw, bool):
        raise PaginationError(f"{name} must be an integer")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        # A float value is not an integer (e.g. 1.5); only integral floats coerce.
        if raw.is_integer():
            return int(raw)
        raise PaginationError(f"{name} must be an integer")
    # String handling: reject empty and non-integer strings.
    text = str(raw).strip()
    if text == "":
        raise PaginationError(f"{name} must not be empty")
    try:
        # int() rejects "1.5" and "abc" but accepts "10" and "-3".
        return int(text)
    except ValueError:
        raise PaginationError(f"{name} must be an integer")


def parse_pagination_params(args) -> Tuple[int, int]:
    """Extract and validate ``page`` and ``page_size`` from ``args``.

    Applies defaults (page=1, page_size=20), validates that both are integers,
    and enforces range: ``page >= 1`` and ``1 <= page_size <= 100``. Raises
    ``PaginationError`` on any violation.
    """
    page = _parse_int_param(args, "page", DEFAULT_PAGE)
    page_size = _parse_int_param(args, "page_size", DEFAULT_PAGE_SIZE)

    if page < MIN_PAGE:
        raise PaginationError("page must be >= 1")
    if page_size < MIN_PAGE_SIZE:
        raise PaginationError("page_size must be >= 1")
    if page_size > MAX_PAGE_SIZE:
        raise PaginationError(f"page_size must be <= {MAX_PAGE_SIZE}")

    return page, page_size


def paginate(items: List[dict], page: int, page_size: int) -> dict:
    """Return a UserPage dict for ``items`` sliced by ``page``/``page_size``.

    ``total`` is the length of ``items`` before slicing (post-filter,
    pre-pagination). A page beyond the last returns an empty ``items`` list
    with the correct ``total`` and requested page values.
    """
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "page": page,
        "page_size": page_size,
        "total": len(items),
    }
