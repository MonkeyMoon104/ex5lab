"""Input validation for read-only binary analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Soft safety bound for research tooling (100 MiB). Oversized files are rejected,
# not truncated, so analysis remains deterministic and complete when accepted.
DEFAULT_MAX_BYTES = 100 * 1024 * 1024


class BinaryValidationError(ValueError):
    """Raised when an input cannot be safely analyzed as requested."""


@dataclass(frozen=True)
class ValidatedBinary:
    path: Path
    data: bytes
    size: int


def validate_and_read(
    path: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allow_empty: bool = False,
) -> ValidatedBinary:
    """Validate path readability/size and return file bytes.

    Raises BinaryValidationError for missing, unreadable, empty (unless allowed),
    truncated/zero-length unexpected, or oversized inputs.
    """
    p = Path(path)

    if not p.exists():
        raise BinaryValidationError(f"File not found: {p}")
    if not p.is_file():
        raise BinaryValidationError(f"Not a regular file: {p}")

    try:
        size = p.stat().st_size
    except OSError as exc:
        raise BinaryValidationError(f"Unable to stat file: {p} ({exc})") from exc

    if size < 0:
        raise BinaryValidationError(f"Invalid negative size reported for: {p}")
    if size == 0 and not allow_empty:
        raise BinaryValidationError(f"Empty file (0 bytes): {p}")
    if size > max_bytes:
        raise BinaryValidationError(
            f"File exceeds max size ({size} > {max_bytes} bytes): {p}"
        )

    try:
        data = p.read_bytes()
    except OSError as exc:
        raise BinaryValidationError(f"Unable to read file: {p} ({exc})") from exc

    if len(data) != size:
        raise BinaryValidationError(
            f"Truncated or inconsistent read for {p}: "
            f"stat={size}, read={len(data)}"
        )

    return ValidatedBinary(path=p.resolve(), data=data, size=size)


def looks_like_ex5_extension(path: str | Path) -> bool:
    """Heuristic filename check only  -  not a format proof."""
    return Path(path).suffix.lower() == ".ex5"
