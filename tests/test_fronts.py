import numpy as np
import pytest
from shapely.geometry import LineString, MultiLineString, box

from coastaldunes.fronts import area_velocity, measure_features, transects


def test_report_area_velocity_equation():
    result = area_velocity(box(0, 0, 100, 20), LineString([(0, 10), (100, 10)]), 5)
    assert result["mean_advance_m"] == 20
    assert result["mean_velocity_m_per_year"] == 4
    with pytest.raises(ValueError):
        area_velocity(box(0, 0, 100, 20), LineString([(0, 10), (100, 10)]), 0)


def test_parallel_fronts_have_signed_twenty_metre_advance():
    old, new = LineString([(0, 0), (0, 100)]), LineString([(20, 0), (20, 100)])
    data = transects(old, new, box(-10, -10, 30, 110), 90, 10, 50)
    np.testing.assert_allclose(data.distance_m, 20)
    assert data.status.eq("ok").all()


def test_retreat_has_negative_sign():
    old, new = LineString([(0, 0), (0, 100)]), LineString([(-20, 0), (-20, 100)])
    data = transects(old, new, box(-30, -10, 30, 110), 90, 10, 50)
    np.testing.assert_allclose(data.distance_m, -20)


def test_missing_intersections_are_not_zero():
    old, new = LineString([(0, 0), (0, 100)]), LineString([(20, 200), (20, 300)])
    data = transects(old, new, box(-30, -10, 30, 310), 90, 10, 50)
    assert data.distance_m.isna().all()


def test_multipart_fronts_are_not_truncated_to_first_component():
    old = MultiLineString([[(0, 0), (0, 10)], [(0, 40), (0, 50)]])
    new = LineString([(20, -10), (20, 100)])
    data = transects(old, new, box(-30, -20, 30, 110), 90, 5, 50)
    assert set(data.component) == {0, 1}
    np.testing.assert_allclose(data.distance_m, 20)


def test_duplicate_feature_keys_are_rejected():
    feature = {
        "properties": {"site": "A", "kind": "front", "year": 2005},
        "geometry": LineString([(0, 0), (0, 10)]),
    }
    with pytest.raises(ValueError):
        measure_features([feature, feature], 90, 10, 50, "nearest")
