import duckdb
import httpx
import pytest
import shapely.wkt
from shapely.geometry import Point

from etl import geocode_obreby
from etl.geocode_obreby import (
    UldkClient,
    UldkError,
    build_permits_hex,
    geocode_missing,
    parse_uldk_response,
    wkt_to_latlng,
)

SQUARE = "POLYGON((17.0 51.0,17.2 51.0,17.2 51.2,17.0 51.2,17.0 51.0))"
# prawdziwy kształt odpowiedzi ULDK (skrócone współrzędne)
REGION_REPLY = "0\n160602_4.0038|Namysłów|SRID=4326;MULTIPOLYGON(((17.0 51.0,17.2 51.0,17.2 51.2,17.0 51.2,17.0 51.0)))\n"
PARCEL_REPLY = "0\n160602_4.0038.178/11|SRID=4326;" + SQUARE + "\n"
NOT_FOUND = "-1 brak wyników"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Nie czekamy naprawdę między ponowieniami; zapamiętujemy żądane przerwy."""
    sleeps = []
    monkeypatch.setattr(geocode_obreby.time, "sleep", sleeps.append)
    return sleeps


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parse_three_field_reply():
    obreb_id, name, wkt = parse_uldk_response(REGION_REPLY)
    assert (obreb_id, name) == ("160602_4.0038", "Namysłów")
    assert wkt.startswith("MULTIPOLYGON") and "SRID" not in wkt


def test_parse_two_field_reply():
    obreb_id, name, wkt = parse_uldk_response(PARCEL_REPLY)
    assert obreb_id == "160602_4.0038.178/11" and name == "" and wkt == SQUARE


def test_parse_not_found_or_garbage_is_none():
    assert parse_uldk_response(NOT_FOUND) is None
    assert parse_uldk_response("0") is None          # sukces bez danych
    assert parse_uldk_response("") is None


def test_wkt_to_latlng_inside_polygon():
    lat, lng = wkt_to_latlng(SQUARE)
    assert shapely.wkt.loads(SQUARE).contains(Point(lng, lat))      # kolejność: lat, lng (ULDK daje x=lng, y=lat)
    assert (lat, lng) == pytest.approx((51.1, 17.1))


def test_wkt_to_latlng_concave_shape_stays_inside():
    l_shape = "POLYGON((0 0,10 0,10 1,1 1,1 10,0 10,0 0))"      # litera L: środek ciężkości leży poza figurą
    lat, lng = wkt_to_latlng(l_shape)
    assert shapely.wkt.loads(l_shape).contains(Point(lng, lat))


def test_client_region_sends_expected_request():
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        return httpx.Response(200, text=REGION_REPLY)

    name, lat, lng = UldkClient(_client(handler)).region("160602_4.0038")
    assert name == "Namysłów" and (lat, lng) == pytest.approx((51.1, 17.1))
    assert seen == [{"request": "GetRegionById", "id": "160602_4.0038", "result": "teryt,region,geom_wkt", "srid": "4326"}]


def test_client_commune_request_and_not_found():
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        return httpx.Response(200, text=NOT_FOUND)

    assert UldkClient(_client(handler)).commune("160602_4") is None
    assert seen[0]["request"] == "GetCommuneById" and seen[0]["result"] == "teryt,commune,geom_wkt"


def test_client_retries_on_server_errors(no_sleep):
    answers = iter([500, 502, 200])

    def handler(req):
        code = next(answers)
        return httpx.Response(code, text=REGION_REPLY if code == 200 else "błąd")

    assert UldkClient(_client(handler)).region("160602_4.0038") is not None
    assert no_sleep == [1, 2]


def test_client_gives_up_after_retries(no_sleep):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503)

    with pytest.raises(UldkError):
        UldkClient(_client(handler)).region("160602_4.0038")
    assert len(calls) == 4 and no_sleep == [1, 2, 4]       # pierwsze podejście + 3 ponowienia


def test_client_retries_network_errors(no_sleep):
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) < 2:
            raise httpx.ConnectError("brak sieci")
        return httpx.Response(200, text=REGION_REPLY)

    assert UldkClient(_client(handler)).region("160602_4.0038") is not None
    assert no_sleep == [1]


def _con_with_permits(ids):
    con = duckdb.connect()
    con.execute("CREATE TABLE permits_raw (source_id VARCHAR, source VARCHAR, kind VARCHAR, date DATE, obreb_id VARCHAR, terc VARCHAR)")
    for i, obreb in enumerate(ids):
        con.execute("INSERT INTO permits_raw VALUES (?, 'pozwolenie', 'sf', DATE '2026-01-15', ?, '1606024')", [f"id{i}", obreb])
    return con


def _handler_factory(regions: set[str], communes: set[str], log: list):
    def handler(req):
        p = req.url.params
        log.append((p["request"], p["id"]))
        if p["request"] == "GetRegionById":
            ok = p["id"] in regions
            return httpx.Response(200, text=f"0\n{p['id']}|Region {p['id']}|SRID=4326;{SQUARE}" if ok else NOT_FOUND)
        ok = p["id"] in communes
        return httpx.Response(200, text=f"0\n{p['id']}|Gmina|SRID=4326;{SQUARE}" if ok else NOT_FOUND)
    return handler


def test_geocode_missing_statuses_and_cache():
    con = _con_with_permits(["160602_4.0038", "160602_4.0038", "160603_1.0001", "160604_1.0001"])
    log = []
    uldk = UldkClient(_client(_handler_factory({"160602_4.0038"}, {"160603_1"}, log)))
    counts = geocode_missing(con, uldk, workers=2, batch=2)
    assert counts == {"region": 1, "commune": 1, "missing": 1, "error": 0}
    rows = dict((r[0], r[1:]) for r in con.execute("SELECT obreb_id, status, lat FROM obreb_geom").fetchall())
    assert rows["160602_4.0038"][0] == "region" and rows["160603_1.0001"][0] == "commune"
    assert rows["160604_1.0001"] == ("missing", None)
    assert ("GetCommuneById", "160603_1") in log             # fallback: gmina = część przed kropką
    first_calls = len(log)
    # drugie wywołanie: wszystko jest w cache (tabela obreb_geom) — zero zapytań
    assert geocode_missing(con, uldk) == {"region": 0, "commune": 0, "missing": 0, "error": 0}
    assert len(log) == first_calls


def test_geocode_missing_network_error_is_not_cached():
    con = _con_with_permits(["160602_4.0038"])
    state = {"fail": True}

    def handler(req):
        if state["fail"]:
            return httpx.Response(500)
        return httpx.Response(200, text=REGION_REPLY)

    uldk = UldkClient(_client(handler))
    assert geocode_missing(con, uldk)["error"] == 1
    assert con.execute("SELECT COUNT(*) FROM obreb_geom").fetchall()[0][0] == 0   # błąd nie jest zapamiętany
    state["fail"] = False
    assert geocode_missing(con, uldk)["region"] == 1                              # kolejne uruchomienie dokończy


def test_build_permits_hex_aggregates_by_month_and_kind():
    con = duckdb.connect()
    con.execute("CREATE TABLE permits_raw (source_id VARCHAR, source VARCHAR, kind VARCHAR, date DATE, obreb_id VARCHAR, terc VARCHAR)")
    con.execute("""INSERT INTO permits_raw VALUES
        ('a', 'pozwolenie', 'sf', DATE '2026-01-05', 'O1', ''),
        ('b', 'pozwolenie', 'sf', DATE '2026-01-25', 'O1', ''),
        ('c', 'pozwolenie', 'sf', DATE '2026-02-03', 'O1', ''),
        ('d', 'pozwolenie', 'mf', DATE '2026-01-05', 'O1', ''),
        ('e', 'pozwolenie', 'sf', DATE '2026-01-05', 'O_BRAK', '')""")
    con.execute("CREATE TABLE obreb_geom (obreb_id VARCHAR PRIMARY KEY, name VARCHAR, lat DOUBLE, lng DOUBLE, status VARCHAR)")
    con.execute("INSERT INTO obreb_geom VALUES ('O1', 'x', 51.1, 17.0, 'region'), ('O_BRAK', NULL, NULL, NULL, 'missing')")
    n = build_permits_hex(con)
    rows = con.execute("SELECT CAST(month AS VARCHAR), kind, n FROM permits_r8 ORDER BY 1, 2").fetchall()
    assert rows == [("2026-01-01", "mf", 1), ("2026-01-01", "sf", 2), ("2026-02-01", "sf", 1)]
    assert n == 3


# ---- Odporność na blokadę/śmieciowe odpowiedzi (ULDK potrafi przekierować na stronę-pułapkę) ----

def test_redirect_is_an_error_not_missing(no_sleep):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(302, headers={"Location": "https://integracja01.gugik.gov.pl/resp/uldk.php"})

    with pytest.raises(UldkError):
        UldkClient(_client(handler)).region("160602_4.0038")
    assert len(calls) == 4                      # przekierowania nie śledzimy, ponawiamy jak błąd serwera


def test_garbage_success_reply_is_an_error():
    garbage = "0\n0101000020E6100000000000000080564000000000008056400101010101010101"
    with pytest.raises(UldkError):
        UldkClient(_client(lambda req: httpx.Response(200, text=garbage))).region("160602_4.0038")
    with pytest.raises(UldkError):
        UldkClient(_client(lambda req: httpx.Response(200, text="0"))).region("160602_4.0038")
    with pytest.raises(UldkError):
        UldkClient(_client(lambda req: httpx.Response(200, text="-1 Błąd serwera"))).region("160602_4.0038")
    with pytest.raises(UldkError):
        UldkClient(_client(lambda req: httpx.Response(200, text=""))).region("160602_4.0038")


def test_geocode_missing_stops_when_server_blocks():
    con = _con_with_permits([f"160602_4.{i:04d}" for i in range(1, 9)])
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(302, headers={"Location": "https://x/"})

    counts = geocode_missing(con, UldkClient(_client(handler)), workers=1, batch=4)
    assert counts["error"] == 4 and counts["missing"] == 0        # po pierwszej porcji z samymi błędami przerywamy
    assert con.execute("SELECT COUNT(*) FROM obreb_geom").fetchall()[0][0] == 0


def test_geocode_missing_visits_ids_in_scattered_order():
    """Przerwany przebieg ma obejmować cały kraj, a nie kilka pierwszych województw (kolejność = hash id)."""
    ids = [f"{woj}0101_1.0001" for woj in ("02", "04", "06", "08", "10", "12", "14", "16", "18", "20", "22", "24")]
    con = _con_with_permits(ids)
    visited = []

    def handler(req):
        visited.append(req.url.params["id"])
        return httpx.Response(200, text=NOT_FOUND)

    geocode_missing(con, UldkClient(_client(handler)), workers=1, batch=100)
    regions = [i for i in visited if "." in i]
    assert sorted(regions) == sorted(ids) and regions != sorted(ids)      # nie alfabetycznie
