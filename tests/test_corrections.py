import numpy as np
import pandas as pd
import pytest

from coastaldunes.corrections import apply_corrections


def records():
    return pd.DataFrame(
        {
            "row": [0],
            "col": [0],
            "from_class": [2],
            "to_class": [5],
            "reason": ["Synthetic test"],
            "source": ["Invented example"],
        }
    )


def test_corrections_preserve_input_and_require_expected_source():
    a = np.full((2, 2), 2)
    result, log = apply_corrections(a, records())
    assert result[0, 0] == 5
    assert a[0, 0] == 2
    bad = records()
    bad["from_class"] = 1
    with pytest.raises(ValueError):
        apply_corrections(a, bad)


def test_corrections_cannot_expand_the_domain():
    a = np.full((2, 2), 2)
    a[0, 0] = -1
    with pytest.raises(ValueError):
        apply_corrections(a, records())


def test_duplicate_or_undocumented_edits_rejected():
    a = np.full((2, 2), 2)
    with pytest.raises(ValueError):
        apply_corrections(a, pd.concat([records(), records()]))
    missing = records()
    missing["reason"] = ""
    with pytest.raises(ValueError):
        apply_corrections(a, missing)
