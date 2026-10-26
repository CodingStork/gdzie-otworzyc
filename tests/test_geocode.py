import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes
from backend.app.config import USER_AGENT
from backend.app.main import app
from backend.app.services import geocode as geocode_module
from backend.app.services.geocode import Geocoder, GeocoderUnavailable

NOMINATIM_REPLY = [
    {"display_name": "Opole, województwo opolskie, Polska", "lat": "50.6683", "lon": "17.9231", "importance": 0.7},
    {"display_name": "Opole Lubelskie, Polska", "lat": "51.1456", "lon": "21.9690"},
]


def _geocoder(handler, **kw):
    kw.setdefault("min_interval_s", 0.0)
    return Geocoder(httpx.Client(transport=httpx.MockTransport(handler)), **kw)


def test_geocode_short_query():
    calls = []
    g = _geocoder(lambda req: calls.append(req) or httpx.Response(200, json=[]))
    assert g.search("  a ") == [] and g.search("") == [] and g.search("ab") == []
    assert calls == []


def test_geocode_maps_fields_and_params():
    seen = []

    def handler(req):
        seen.append((dict(req.url.params), req.headers["user-agent"]))
        return httpx.Response(200, json=NOMINATIM_REPLY)

    out = _geocoder(handler).search("Opole")
    assert out[0] == {"name": "Opole, województwo opolskie, Polska", "lat": 50.6683, "lng": 17.9231}
    assert isinstance(out[0]["lat"], float) and len(out) == 2
    params, user_agent = seen[0]
    assert params == {"q": "Opole", "format": "jsonv2", "countrycodes": "pl", "limit": "5", "accept-language": "pl"}
    assert user_agent == USER_AGENT


def test_geocode_returns_at_most_five():
    many = [{"display_name": f"M{i}", "lat": "50", "lon": "17"} for i in range(8)]
    assert len(_geocoder(lambda req: httpx.Response(200, json=many)).search("Miasto")) == 5


def test_geocode_cache():
    calls = []
    g = _geocoder(lambda req: calls.append(1) or httpx.Response(200, json=NOMINATIM_REPLY))
    first = g.search("Opole")
    assert g.search("  OPOLE ") == first        # klucz: po strip i lower
    assert len(calls) == 1


def test_geocode_polish_chars():
    seen = []
    g = _geocoder(lambda req: seen.append(req.url.params["q"]) or httpx.Response(200, json=[]))
    g.search("Łódź Piotrkowska")
    assert seen == ["Łódź Piotrkowska"]


def test_geocode_upstream_errors_raise_and_are_not_cached():
    state = {"code": 500}

    def handler(req):
        return httpx.Response(state["code"], json=NOMINATIM_REPLY if state["code"] == 200 else {})

    g = _geocoder(handler)
    with pytest.raises(GeocoderUnavailable):
        g.search("Opole")
    state["code"] = 200
    assert len(g.search("Opole")) == 2               # błąd nie został zapamiętany


def test_geocode_network_error_and_bad_json():
    def broken(req):
        raise httpx.ConnectError("brak sieci")

    with pytest.raises(GeocoderUnavailable):
        _geocoder(broken).search("Opole")
    with pytest.raises(GeocoderUnavailable):
        _geocoder(lambda req: httpx.Response(200, text="to nie json")).search("Opole")


def test_geocode_throttles_between_requests(monkeypatch):
    sleeps = []
    monkeypatch.setattr(geocode_module.time, "sleep", sleeps.append)
    monkeypatch.setattr(geocode_module.time, "monotonic", lambda: 100.0)      # zegar stoi
    g = _geocoder(lambda req: httpx.Response(200, json=[]), min_interval_s=1.0)
    g.search("Opole")
    assert sleeps == []                            # pierwsze zapytanie bez czekania
    g.search("Nysa")
    assert sleeps == [1.0]                          # drugie, "natychmiast" po pierwszym → czekamy pełną sekundę


@pytest.fixture
def api_with_geocoder():
    def build(handler):
        g = _geocoder(handler)
        app.dependency_overrides[routes.get_geocoder] = lambda: g
        return TestClient(app)
    yield build
    app.dependency_overrides.clear()


def test_api_geocode_returns_list(api_with_geocoder):
    client = api_with_geocoder(lambda req: httpx.Response(200, json=NOMINATIM_REPLY))
    j = client.get("/api/geocode", params={"q": "Opole"}).json()
    assert j[0]["lat"] == 50.6683 and j[0]["name"].startswith("Opole")
    assert client.get("/api/geocode", params={"q": "x"}).json() == []
    assert client.get("/api/geocode").json() == []


def test_geocode_upstream_error(api_with_geocoder):
    client = api_with_geocoder(lambda req: httpx.Response(500))
    r = client.get("/api/geocode", params={"q": "Opole"})
    assert r.status_code == 502 and "Wyszukiwarka adresów chwilowo niedostępna" in r.text
