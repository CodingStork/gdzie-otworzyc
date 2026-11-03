"""Testy rdzenia v3: rozpad odległości, model Huffa, siatka i wybór maksimów."""
import math

import numpy as np
import pytest

from backend.app.analysis.surface import (
    A0, competition_density, decay, demand_potential, huff_expected, make_grid, peaks_and_edge, top_points,
)


def test_decay_cutoff():
    v = decay(np.array([0.0, 1000.0, 4001.0]), 1000)
    assert v[0] == 1 and v[1] == pytest.approx(math.exp(-1)) and v[2] == 0


def test_huff_no_competitors():
    E = huff_expected(np.array([[0.0, 0.0]]), np.array([[1000.0, 0.0]]), np.array([100.0]), np.empty((0, 2)), 1000)
    f = math.exp(-1)
    assert E[0] == pytest.approx(100 * f / (f + 0 + A0))          # = 50


def test_huff_competitor_reduces():
    g = np.array([[0.0, 0.0]]); dem = np.array([[0.0, 0.0]]); w = np.array([100.0])
    alone = huff_expected(g, dem, w, np.empty((0, 2)), 1000)[0]
    shared = huff_expected(g, dem, w, np.array([[0.0, 0.0]]), 1000)[0]
    assert shared == pytest.approx(100 * 1 / (1 + 1 + A0)) and shared < alone


def test_huff_blocks_give_same_result():
    rng = np.random.default_rng(1)
    g = rng.uniform(0, 5000, (4500, 2)); dem = rng.uniform(0, 5000, (300, 2)); w = rng.uniform(1, 50, 300)
    comp = rng.uniform(0, 5000, (20, 2))
    E = huff_expected(g, dem, w, comp, 800)
    assert E.shape == (4500,) and np.allclose(E[:5], huff_expected(g[:5], dem, w, comp, 800))


def test_potential_and_density():
    g = np.array([[0.0, 0.0]])
    assert demand_potential(g, np.array([[1000.0, 0.0]]), np.array([10.0]), 1000)[0] == pytest.approx(10 * math.exp(-1))
    assert competition_density(g, np.array([[0.0, 0.0], [9000.0, 0.0]]), 1000)[0] == pytest.approx(1.0)
    assert competition_density(g, np.empty((0, 2)), 1000)[0] == 0


def test_grid_covers_circle():
    xy, mask, cell, nx, ny = make_grid(np.array([0.0, 0.0]), 10_000)
    assert cell == pytest.approx(10_000 / 90, rel=0.01) and mask.sum() == pytest.approx(math.pi * 90**2, rel=0.03)
    assert xy[0, 1] > xy[-1, 1]                                    # pierwszy wiersz = północ
    assert len(xy) == nx * ny == len(mask)


def test_top_points_separation():
    xy = np.array([[0.0, 0.0], [100.0, 0.0], [5000.0, 0.0], [9000.0, 0.0]])
    values = np.array([100.0, 90.0, 50.0, 0.0])
    mask = np.ones(4, bool)
    assert top_points(values, xy, mask, 500) == [0, 2]            # 1 odpada (100 m od 0), 3 ma wartość 0
    assert top_points(values, xy, np.array([False, True, True, True]), 500) == [1, 2]


def test_peaks_only_inside_and_highest():
    """Szczyt = wszyscy sąsiedzi w obszarze i żaden nie jest wyższy; punkt krawędzi nigdy nie jest szczytem."""
    yy, xx = np.mgrid[0:5, 0:5]
    hill = (10 - (yy - 2) ** 2 - (xx - 2) ** 2).astype(float).ravel()        # szczyt w środku siatki 5 × 5
    mask = np.ones(25, bool)
    peaks, edge = peaks_and_edge(hill, mask, 5, 5)
    assert np.flatnonzero(peaks).tolist() == [12]
    assert edge.sum() == 16 and not edge[12]


def test_ramp_rising_towards_edge_has_no_peak():
    """Wartości rosną w stronę krawędzi (najlepsze miejsce leży poza obszarem) — nie ma czego nazwać „najlepszym miejscem”."""
    ramp = np.tile(np.arange(5, dtype=float), 5)                            # rośnie na wschód
    peaks, edge = peaks_and_edge(ramp, np.ones(25, bool), 5, 5)
    assert not peaks.any() and edge.any()


def test_peaks_respect_mask_holes():
    hill = np.zeros(25)
    hill[12] = 5
    mask = np.ones(25, bool)
    mask[13] = False                                                        # sąsiad poza obszarem → nie wiemy, czy to szczyt
    peaks, _ = peaks_and_edge(hill, mask, 5, 5)
    assert not peaks[12]
