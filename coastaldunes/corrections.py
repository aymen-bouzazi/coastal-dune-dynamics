"""Optional expert corrections, kept separate from untouched model outputs."""

import numpy as np

from .model import check_array


def apply_corrections(array, records):
    required = {"row", "col", "from_class", "to_class", "reason", "source"}
    if not required <= set(records):
        raise ValueError("Corrections need row, col, from_class, to_class, reason and source.")
    a = check_array(array)
    edits = records.copy()
    for col in ("row", "col", "from_class", "to_class"):
        values = edits[col].to_numpy()
        if (
            not np.issubdtype(values.dtype, np.number)
            or not np.isfinite(values).all()
            or (values != np.floor(values)).any()
        ):
            raise ValueError("Correction coordinates/classes must be finite integers.")
        edits[col] = edits[col].astype(int)
    if edits.duplicated(["row", "col"]).any():
        raise ValueError("Duplicate cell corrections are ambiguous.")
    for col in ("reason", "source"):
        if edits[col].isna().any() or edits[col].astype(str).str.strip().eq("").any():
            raise ValueError("Every expert correction needs a reason and reference source.")
    corrected = a.copy()
    for edit in edits.itertuples():
        if not (0 <= edit.row < a.shape[0] and 0 <= edit.col < a.shape[1]):
            raise ValueError("Correction lies outside the raster dimensions.")
        if edit.to_class not in range(9) or edit.from_class not in range(9):
            raise ValueError("Corrections cannot turn outside/NoData into modelled land.")
        if a[edit.row, edit.col] != edit.from_class:
            raise ValueError(
                "Expected original class does not match; wrong map or stale correction."
            )
        corrected[edit.row, edit.col] = edit.to_class
    return corrected, edits
