import numpy as np
import pandas as pd
import pytest

from coastaldunes.analysis import annual_climate, class_areas, evaluate, landscape_metrics
from coastaldunes.planning import priority_scores, relate_changes


def test_areas_have_explicit_hectare_units_and_exclude_nodata():
    table = class_areas(np.array([[5, 5], [-1, 8]]), 900).set_index("class_code")
    assert table.loc[5, "area_ha"] == pytest.approx(0.18)
    assert table.loc[8, "area_ha"] == pytest.approx(0.09)
    assert table.pixels.sum() == 3


def test_high_persistence_accuracy_does_not_hide_missed_change():
    base = np.full((10, 10), 2)
    actual = base.copy()
    actual[0, 0] = 5
    result, _, _ = evaluate(base, actual, base)
    assert result["overall_accuracy"] == 0.99
    assert result["figure_of_merit"] == 0
    assert result["missed_changes"] == 1


def test_predicted_ghost_is_an_error_on_known_reference():
    base = np.array([[2, 2, -1, 8]])
    actual = np.array([[5, 2, 5, 8]])
    pred = np.array([[8, 2, -1, 8]])
    result, _, cm = evaluate(base, actual, pred)
    assert result["evaluated_pixels"] == 2
    assert result["overall_accuracy"] == 0.5
    assert cm[5, 8] == 1
    assert result["wrong_change_destination"] == 1


def test_figure_of_merit_counts_wrong_destination_and_false_change():
    base = np.array([[2, 2, 2, 2]])
    actual = np.array([[5, 5, 5, 2]])
    pred = np.array([[5, 1, 2, 5]])
    result, _, _ = evaluate(base, actual, pred)
    assert result["figure_of_merit"] == 0.25
    assert [
        result[k]
        for k in ["change_hits", "wrong_change_destination", "missed_changes", "false_changes"]
    ] == [1, 1, 1, 1]


def test_no_change_fom_is_undefined_instead_of_perfect():
    a = np.full((2, 2), 2)
    assert evaluate(a, a, a)[0]["figure_of_merit"] is None


def test_forest_classes_are_merged_before_patch_labelling():
    a = np.array([[1, 2], [0, 3]])
    metrics = landscape_metrics(a, 10)
    assert metrics["forest_patch_count"] == 1
    assert metrics["forest_largest_patch_percent"] == 75
    assert metrics["forest_edge_density_m_per_ha"] == 500


def test_diagonal_connectivity_is_an_explicit_choice():
    a = np.array([[2, 0], [0, 2]])
    assert landscape_metrics(a, 30, 4)["forest_patch_count"] == 2
    assert landscape_metrics(a, 30, 8)["forest_patch_count"] == 1


def test_monthly_rainfall_rate_is_converted_by_calendar_days():
    a = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=12, freq="MS"),
            "temperature": 20.0,
            "wind_speed": 3.0,
            "precipitation": 1.0,
        }
    )
    assert annual_climate(a, "mean_daily_rate").iloc[0].precipitation_total == 366
    assert annual_climate(a, "monthly_total").iloc[0].precipitation_total == 12
    with pytest.raises(ValueError):
        annual_climate(a.iloc[:-1], "mean_daily_rate")


def test_climate_duplicate_months_and_sentinels_are_rejected():
    a = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-15"],
            "temperature": 20.0,
            "wind_speed": 3.0,
            "precipitation": 1.0,
        }
    )
    with pytest.raises(ValueError):
        annual_climate(a, "monthly_total")
    a = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=12, freq="MS"),
            "temperature": 20.0,
            "wind_speed": -999.0,
            "precipitation": 1.0,
        }
    )
    with pytest.raises(ValueError):
        annual_climate(a, "mean_daily_rate")


def test_priority_uses_supplied_binary_judgements_only():
    df = pd.DataFrame({"zone_id": ["A", "B"], "housing": [1, 0], "fields": [1, 1]})
    result = priority_scores(df, ["housing", "fields"])
    assert result.priority_score.tolist() == [2, 1]
    df.loc[0, "fields"] = 2
    with pytest.raises(ValueError):
        priority_scores(df, ["housing", "fields"])


def test_associations_do_not_mix_observed_and_simulated_intervals():
    fields = [
        "forest_largest_patch_percent",
        "forest_edge_density_m_per_ha",
        "sand_patch_density_per_100ha",
    ]
    metrics = pd.DataFrame(
        {
            "year": [2005, 2010, 2015, 2020, 2025],
            "phase": ["observed"] * 4 + ["simulated"],
            **{f: range(5) for f in fields},
        }
    )
    fronts = pd.DataFrame(
        {
            "site": ["A"] * 4,
            "from_year": [2005, 2010, 2015, 2020],
            "to_year": [2010, 2015, 2020, 2025],
            "sampled_max_signed_advance_m": [1, 2, 3, 4],
        }
    )
    joined, summary = relate_changes(metrics, fronts)
    assert joined.phase.tolist() == ["observed"] * 3 + ["scenario"]
    assert set(summary.phase) == {"observed", "scenario"}


def test_monthly_wind_direction_is_circular_and_rh_is_optional():
    a = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=12, freq="MS"),
            "temperature": 20.0,
            "wind_speed": 3.0,
            "precipitation": 1.0,
            "relative_humidity": 60.0,
            "wind_direction": [350, 10] * 6,
        }
    )
    result = annual_climate(a, "monthly_total").iloc[0]
    assert result.relative_humidity == 60
    assert min(result.wind_from_direction_deg, 360 - result.wind_from_direction_deg) < 2
