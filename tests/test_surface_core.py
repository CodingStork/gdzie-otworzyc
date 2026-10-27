"""Testy rdzenia v3: rozpad odległości, model Huffa, siatka i wybór maksimów."""
import math

import numpy as np
import pytest

from backend.app.analysis.surface import (
    A0, competition_density, decay, demand_potential, huff_expected, make_grid, top_points,
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
