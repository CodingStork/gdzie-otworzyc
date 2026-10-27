import math

import h3
import numpy as np
import pytest

from backend.app.analysis.kernel import catchment_sums, to_metric
from backend.app.analysis.resolution import (
    choose_compute_res,
    display_res_for_zoom,
    snap_bbox,
)
from backend.app.analysis.scoring import (
    legend_values,
    percentile_rank,
    pick_top,
    score,
    weighted_parent_mean,
)


# ---- v2: poziomy szczegółowości, okrąg zasięgu, agregacja ----

def test_display_res_for_zoom():
    assert [display_res_for_zoom(z) for z in (5, 6, 7, 8, 9, 10, 11, 12, 16)] == [5, 5, 6, 6, 7, 8, 8, 9, 9]


def test_snap_bbox_outward():
    assert snap_bbox((21.03, 52.21, 21.07, 52.26), 8) == (21.0, 52.0, 21.25, 52.5)
    assert snap_bbox((21.0, 52.0, 21.25, 52.5), 8) == (21.0, 52.0, 21.25, 52.5)    # już na siatce: bez zmian


def test_compute_res_city_vs_country():
    assert choose_compute_res((20.9, 52.1, 21.2, 52.35), 1.5, 9) == 9          # miasto
    assert choose_compute_res((14.1, 49.0, 24.2, 54.9), 1.5, 5) == 8           # cała Polska, mały zasięg
    assert choose_compute_res((14.1, 49.0, 24.2, 54.9), 20, 5) in (6, 7)       # cała Polska, duży zasięg


def test_compute_res_never_finer_than_needed_by_display():
    # przy dużym przybliżeniu display_res = 9 i nie ma gdzie schodzić poniżej; nie schodzimy też poniżej display_res
    assert choose_compute_res((14.1, 49.0, 24.2, 54.9), 20, 8) >= 8


def test_catchment_disk_counts():
    t = np.array([[0.0, 0.0]]); src = np.array([[0, 0], [900, 0], [1100, 0]], float)
    assert catchment_sums(t, src, np.array([1.0, 2.0, 4.0]), 1000)[0] == 3.0   # 1100 m poza okręgiem


def test_catchment_multi_column_and_empty():
    out = catchment_sums(np.zeros((2, 2)), np.array([[0.0, 0.0], [10.0, 0.0]]), np.array([[1.0, 2.0], [3.0, 4.0]]), 50)
    assert out.shape == (2, 2) and out[0].tolist() == [4.0, 6.0]
    assert catchment_sums(np.zeros((3, 2)), np.zeros((0, 2)), np.zeros(0), 50).tolist() == [0.0, 0.0, 0.0]


def test_weighted_parent_mean():
    parent = h3.latlng_to_cell(52.23, 21.01, 8)
    kids = np.array(sorted(h3.cell_to_children(parent, 9))[:2])
    p, v = weighted_parent_mean(kids, np.array([10.0, 20.0]), np.array([3.0, 1.0]), 8)
    assert list(p) == [parent] and v[0] == pytest.approx(12.5, rel=1e-4)


def test_weighted_parent_mean_keeps_columns_and_zero_weights():
    parent = h3.latlng_to_cell(52.23, 21.01, 8)
    kids = np.array(sorted(h3.cell_to_children(parent, 9))[:2])
    p, v = weighted_parent_mean(kids, np.array([[10.0, 1.0], [20.0, 3.0]]), np.array([0.0, 0.0]), 8)
    assert v.shape == (1, 2) and v[0].tolist() == pytest.approx([15.0, 2.0])   # wagi 0 → zwykła średnia (dzięki ε)


def test_legend_values():
    assert legend_values(np.arange(101.0)) == [0, 25, 50, 75, 90, 100]
    assert legend_values(np.array([])) == []


def test_to_metric_distance():
    xy = to_metric(np.array([52.0, 52.0]), np.array([19.0, 19.01]))
    assert np.linalg.norm(xy[0] - xy[1]) == pytest.approx(686, rel=0.02)  # 0,01° dł. na 52°N


def test_score_no_competition():
    assert score(np.array([100.0]), np.array([0.0]))[0] == 100.0
    assert score(np.array([100.0]), np.array([3.0]))[0] == 25.0


def test_percentile_rank():
    assert percentile_rank(np.array([10.0, 30.0, 20.0])).tolist() == [0, 100, 50]
    assert percentile_rank(np.array([5.0, 5.0, 5.0])).tolist() == [50, 50, 50]   # remisy → ranga średnia
    assert percentile_rank(np.array([7.0])).tolist() == [100]
    assert percentile_rank(np.array([])).tolist() == []


def test_pick_top_respects_separation_and_demand_floor():
    xy = np.array([[0, 0], [100, 0], [5000, 0], [9000, 0]], float)
    scores = np.array([10, 9, 8, 50.0]); D = np.array([100, 100, 100, 1.0])
    assert pick_top(scores, D, xy, min_sep_m=1000, n=5) == [0, 2]   # 3 odpada (D poniżej kwartyla), 1 za blisko 0


def test_pick_top_separation_larger_than_area():
    xy = np.array([[0, 0], [300, 0]], float)
    assert len(pick_top(np.array([2.0, 1.0]), np.array([5.0, 5.0]), xy, min_sep_m=30000)) == 1


def test_pick_top_limits_to_n_and_skips_nonpositive_scores():
    xy = np.array([[i * 10000.0, 0] for i in range(10)])
    scores = np.arange(10, dtype=float)       # idx 0 ma score 0 → odpada
    D = np.ones(10)
    top = pick_top(scores, D, xy, min_sep_m=1000, n=5)
    assert top == [9, 8, 7, 6, 5]
    assert 0 not in pick_top(scores, D, xy, min_sep_m=1000, n=20)


def test_pick_top_empty():
    assert pick_top(np.array([]), np.array([]), np.zeros((0, 2)), min_sep_m=1000) == []
