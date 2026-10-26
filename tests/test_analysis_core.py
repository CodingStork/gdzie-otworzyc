import math

import numpy as np
import pytest

from backend.app.analysis.kernel import kernel_sums, to_metric
from backend.app.analysis.resolution import choose_resolution, effective_bandwidth_km
from backend.app.analysis.scoring import percentile_rank, pick_top, quantile_breaks, score


def test_choose_resolution():
    assert [choose_resolution(r) for r in (1, 15, 15.1, 50, None)] == [8, 8, 7, 7, 6]


def test_effective_bandwidth_has_floor_from_hex_spacing():
    assert effective_bandwidth_km(0.3, 8) == pytest.approx(0.6 * 0.80)   # za małe h → podniesione
    assert effective_bandwidth_km(15, 8) == 15                          # duże h bez zmian
    assert effective_bandwidth_km(1, 6) == pytest.approx(0.6 * 5.6)


def test_kernel_single_source():
    t = np.array([[0.0, 0.0], [1000.0, 0.0], [5000.0, 0.0]])
    out = kernel_sums(t, np.array([[0.0, 0.0]]), np.array([10.0]), bandwidth_m=1000)
    assert out[0] == pytest.approx(10.0)
    assert out[1] == pytest.approx(10 * math.exp(-0.5))
    assert out[2] == 0.0                         # > 3h → obcięte


def test_kernel_multi_column():
    out = kernel_sums(np.zeros((1, 2)), np.zeros((2, 2)), np.array([[1.0, 2.0], [3.0, 4.0]]), 500)
    assert out.shape == (1, 2) and out[0].tolist() == [4.0, 6.0]


def test_kernel_empty_sources():
    out = kernel_sums(np.zeros((3, 2)), np.zeros((0, 2)), np.zeros(0), 500)
    assert out.tolist() == [0.0, 0.0, 0.0]
    out2 = kernel_sums(np.zeros((3, 2)), np.zeros((0, 2)), np.zeros((0, 2)), 500)
    assert out2.shape == (3, 2) and not out2.any()


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


def test_quantile_breaks_unique_and_increasing():
    b = quantile_breaks(np.arange(100.0), k=5)
    assert len(b) == 4 and b == sorted(b) and len(set(b)) == 4
    assert quantile_breaks(np.zeros(10), k=5) == [0.0]     # same zera → jedna granica
    assert quantile_breaks(np.array([]), k=5) == []


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
