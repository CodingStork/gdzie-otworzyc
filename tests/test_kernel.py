import numpy as np
import pytest

from backend.app.analysis.kernel import to_latlng, to_metric


def test_to_metric_distance():
    xy = to_metric(np.array([52.0, 52.0]), np.array([19.0, 19.01]))
    assert np.linalg.norm(xy[0] - xy[1]) == pytest.approx(686, rel=0.02)  # 0,01° dł. na 52°N


def test_roundtrip():
    lat, lng = to_latlng(to_metric(np.array([52.23]), np.array([21.01])))
    assert lat[0] == pytest.approx(52.23) and lng[0] == pytest.approx(21.01)


def test_local_frame_axes_follow_meridians():
    """Siatka mgły ma być wyrównana do północy: 30 km na północ od miejsca to ten sam południk (w EPSG:2180 byłoby ok. 2 km obok)."""
    from backend.app.analysis.kernel import LocalFrame
    frame = LocalFrame(53.43, 14.55)                                   # Szczecin
    lat, lng = frame.to_latlng(np.array([[0.0, 30_000.0], [30_000.0, 0.0]]))
    assert lng[0] == pytest.approx(14.55, abs=1e-3)
    assert lat[1] == pytest.approx(53.43, abs=1e-3)
    assert lat[0] - 53.43 == pytest.approx(30 / 111.2, rel=0.01)
