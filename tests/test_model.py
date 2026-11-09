import numpy as np
import pytest

from coastaldunes.model import (
    Rules,
    estimate_transition,
    forecast,
    neighbourhood_support,
    step,
    transition_counts,
)


def only_sand_transition():
    matrix = np.eye(8)
    matrix[2] = 0
    matrix[2, 5] = 1
    return matrix


def test_transition_counts_require_same_pixels():
    a = np.array([[0, 1, -1], [5, 8, 2]])
    b = np.array([[1, 1, 5], [5, 2, 5]])
    counts = transition_counts(a, b)
    assert counts.sum() == 4
    assert counts[0, 1] == counts[1, 1] == counts[5, 5] == counts[2, 5] == 1


def test_absent_classes_retain_identity():
    maps = {2005: np.zeros((2, 2), int), 2010: np.zeros((2, 2), int)}
    matrix = estimate_transition(maps, [2005, 2010])
    np.testing.assert_array_equal(matrix, np.eye(8))


def test_mean_periods_and_pooled_counts_are_distinct():
    maps = {
        2005: np.array([[2, 2, 2, 2]]),
        2010: np.array([[2, 5, 5, 5]]),
        2015: np.array([[2, 5, 5, 5]]),
    }
    mean = estimate_transition(maps, [2005, 2010, 2015], "mean")
    pooled = estimate_transition(maps, [2005, 2010, 2015], "pooled")
    assert mean[2, 2] == pytest.approx(0.625)
    assert pooled[2, 2] == pytest.approx(0.4)
    np.testing.assert_allclose(mean.sum(axis=1), 1)


def test_nonquinquennial_intervals_rejected():
    with pytest.raises(ValueError):
        estimate_transition({}, [2005, 2025])


def test_directional_sand_support_moves_southeast_not_northwest():
    a = np.full((7, 7), 2)
    a[3, 3] = 5
    support = neighbourhood_support(a)[5]
    assert support[4, 4] > 0
    assert support[2, 2] == 0
    assert support[3, 4] > 0


def test_source_class_controls_transitions():
    a = np.full((5, 5), 2)
    a[1, 1] = 5
    a[2, 2] = 1  # Forest class 1 has only self-transition.
    rules = Rules(resistance=(0.0,) * 9, locked=(), rule="own_row")
    result = step(a, only_sand_transition(), rules)
    assert result[2, 2] == 1
    assert result[2, 1] == 5


def test_distant_sand_does_not_allow_a_local_transition():
    a = np.full((8, 8), 2)
    a[0, 0] = 5
    rules = Rules(resistance=(0.0,) * 9, locked=(), rule="own_row")
    result = step(a, only_sand_transition(), rules)
    assert result[6, 6] == 2  # no evidence retains the current class, not class 0


def test_agriculture_water_and_wet_sand_are_locked():
    a = np.full((5, 5), 5)
    a[2, 1:4] = [0, 6, 7]
    T = np.zeros((8, 8))
    T[:, 5] = 1
    result = step(a, T)
    np.testing.assert_array_equal(result[2, 1:4], [0, 6, 7])


def test_resistance_changes_the_decision():
    a = np.full((5, 5), 5)
    a[2, 2] = 2
    low = step(a, only_sand_transition(), Rules(resistance=(0.0,) * 9, locked=()))
    high = step(a, only_sand_transition(), Rules(resistance=(1.0,) * 9, locked=()))
    assert low[2, 2] == 5
    assert high[2, 2] == 2


def test_ghost_eligibility_and_outside_domain_are_distinct():
    a = np.full((7, 7), 5)
    a[2, 2] = 8
    a[4, 4] = -1
    result = step(a, np.eye(8))
    assert result[2, 2] == 5
    assert result[4, 4] == -1
    b = np.full((5, 5), 8)
    np.testing.assert_array_equal(step(b, np.eye(8)), b)


def test_sampled_updates_are_seeded_and_do_not_modify_inputs():
    a = np.full((20, 20), 5)
    a[::2, ::2] = 2
    before = a.copy()
    rules = Rules(allocation="sample")
    left = step(a, only_sand_transition(), rules, np.random.default_rng(42))
    right = step(a, only_sand_transition(), rules, np.random.default_rng(42))
    np.testing.assert_array_equal(left, right)
    np.testing.assert_array_equal(a, before)
    with pytest.raises(ValueError):
        step(a, np.eye(8), rules)


def test_invalid_class_and_matrix_fail_explicitly():
    with pytest.raises(ValueError):
        step(np.array([[255]]), np.eye(8))
    with pytest.raises(ValueError):
        step(np.array([[2]]), np.zeros((8, 8)))
    with pytest.raises(ValueError):
        step(np.array([[2.0]]), np.eye(8))


def test_dynamic_history_is_labelled_as_simulated_feedback():
    maps = {y: np.full((3, 3), 2) for y in [2005, 2010, 2015, 2020, 2025]}
    original = {y: a.copy() for y, a in maps.items()}
    result, audit = forecast(maps, sorted(maps), [2030, 2035])
    assert not audit[0]["contains_simulated_history"]
    assert audit[1]["contains_simulated_history"]
    assert audit[1]["transition_years"][-1] == 2030
    for year in maps:
        np.testing.assert_array_equal(maps[year], original[year])
    assert set(result) == {2030, 2035}


def test_fixed_history_never_uses_scenarios():
    maps = {y: np.full((3, 3), 2) for y in [2005, 2010, 2015, 2020, 2025]}
    _, audit = forecast(maps, sorted(maps), [2030, 2035], mode="fixed")
    assert not any(record["contains_simulated_history"] for record in audit)
    with pytest.raises(ValueError):
        forecast(maps, sorted(maps), [2030, 2040])


def test_half_resistance_is_not_an_unintended_static_class():
    a = np.full((5, 5), 5)
    a[2, 2] = 2
    matrix = np.eye(8)
    matrix[2] = 0
    matrix[2, 2], matrix[2, 5] = 0.3, 0.7
    result = step(a, matrix)  # dense-forest resistance is .5, not a lock
    assert result[2, 2] == 5


def realistic_matrix():
    # Typical land cover: forest mostly persists, sand never reverts.
    matrix = np.eye(8)
    matrix[2, 2], matrix[2, 5] = 0.9, 0.1
    return matrix


def test_sand_front_advances_downwind_with_realistic_persistence():
    a = np.full((9, 9), 2)
    a[:, :3] = 5  # sand strip on the west side
    result = step(a, realistic_matrix())
    assert (result[:, 3] == 5).any()  # first forest column east of the sand
    assert (result[:, 6:] == 2).all()  # forest far from the front stays forest
    assert (result[:, :3] == 5).all()


def test_sand_upwind_does_not_spread_northwest():
    a = np.full((9, 9), 2)
    a[6:, 6:] = 5  # sand in the south-east corner
    result = step(a, realistic_matrix())
    assert result[5, 5] == 2


def test_own_row_rule_freezes_persistent_classes():
    a = np.full((9, 9), 2)
    a[:, :3] = 5
    frozen = step(a, realistic_matrix(), Rules(rule="own_row"))
    np.testing.assert_array_equal(frozen, a)


def test_unknown_rule_rejected():
    with pytest.raises(ValueError):
        step(np.array([[2]]), np.eye(8), Rules(rule="quota"))
