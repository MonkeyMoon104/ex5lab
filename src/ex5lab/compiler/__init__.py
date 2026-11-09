"""MetaEditor environment discovery, version provenance, and controlled compilation."""

from ex5lab.compiler.env import discover_metaeditor, discover_mql5_include
from ex5lab.compiler.fixed_path import (
    UnauthorizedStagingPathError,
    authorize_staging_path,
    compile_at_path,
    ensure_under_mql5,
    run_fixed_path_series,
    run_variable_path_series,
)
from ex5lab.compiler.version import provenance_record, query_file_version_windows

__all__ = [
    "UnauthorizedStagingPathError",
    "authorize_staging_path",
    "discover_metaeditor",
    "discover_mql5_include",
    "ensure_under_mql5",
    "provenance_record",
    "query_file_version_windows",
    "compile_at_path",
    "run_fixed_path_series",
    "run_variable_path_series",
]