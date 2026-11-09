"""Construct-backed EX5 prefix helpers - re-exports evidence-based header parser.

Do not hardcode EX5\\x01 as a universal magic. Signature is ASCII "EX5";
offset-3 is an empirical program-kind byte.
"""

from __future__ import annotations

from ex5lab.binary.ex5_header import (
    EMPIRICAL_KIND_BYTES,
    EX5_SIGNATURE,
    HAS_CONSTRUCT,
    build_construct_schema,
    parse_ex5_prefix,
    parse_verified_prefix,
)

# Historical mistaken constant - kept only as a named alias for script-kind
# prefix, NOT as universal magic.
SCRIPT_KIND_PREFIX = EX5_SIGNATURE + bytes([0x01])
VERIFIED_MAGIC = SCRIPT_KIND_PREFIX  # deprecated alias; do not use for validation

__all__ = [
    "EMPIRICAL_KIND_BYTES",
    "EX5_SIGNATURE",
    "HAS_CONSTRUCT",
    "SCRIPT_KIND_PREFIX",
    "VERIFIED_MAGIC",
    "build_construct_schema",
    "parse_ex5_prefix",
    "parse_verified_prefix",
]
