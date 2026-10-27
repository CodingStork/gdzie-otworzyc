import numpy as np
import pytest

from backend.app.analysis.kernel import to_latlng, to_metric


def test_to_metric_distance():
    xy = to_metric(np.array([52.0, 52.0]), np.array([19.0, 19.01]))
    assert np.linalg.norm(xy[0] - xy[1]) == pytest.approx(686, rel=0.02)  # 0,01° dł. na 52°N


def test_roundtrip():
    lat, lng = to_latlng(to_metric(np.array([52.23]), np.array([21.01])))
    assert lat[0] == pytest.approx(52.23) and lng[0] == pytest.approx(21.01)
