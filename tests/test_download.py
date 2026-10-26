import zipfile

import httpx
import pytest

from backend.app.config import USER_AGENT
from etl.download import download, extract_member


def test_download_writes_and_skips(tmp_path):
    calls = []

    def handler(req):
        calls.append(req.url)
        return httpx.Response(200, content=b"abc")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = download("https://x/f.bin", tmp_path / "f.bin", client=client)
    assert p.read_bytes() == b"abc"
    download("https://x/f.bin", tmp_path / "f.bin", client=client)
    assert len(calls) == 1  # drugi raz pominięty
    assert not (tmp_path / "f.bin.part").exists()


def test_download_force_downloads_again(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, content=b"abc")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    download("https://x/f.bin", tmp_path / "f.bin", client=client)
    download("https://x/f.bin", tmp_path / "f.bin", force=True, client=client)
    assert len(calls) == 2


def test_download_sends_user_agent(tmp_path):
    seen = []

    def handler(req):
        seen.append(req.headers["user-agent"])
        return httpx.Response(200, content=b"x")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    download("https://x/f.bin", tmp_path / "f.bin", client=client)
    assert seen == [USER_AGENT]


def test_download_error_leaves_no_file(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(404)))
    try:
        download("https://x/f.bin", tmp_path / "f.bin", client=client)
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError("oczekiwano HTTPStatusError")
    assert not (tmp_path / "f.bin").exists()


def test_extract_member(tmp_path):
    zip_path = tmp_path / "a.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("a/x.txt", b"TXT")
        z.writestr("a/ESTAT_Census_2021_V3.parquet", b"PQ")
    out = extract_member(zip_path, "V3.parquet", tmp_path / "out.parquet")
    assert out.read_bytes() == b"PQ"


def test_extract_member_is_atomic(tmp_path, monkeypatch):
    """Przerwane wypakowywanie nie może zostawić kompletnie wyglądającego, ale ucięte pliku."""
    zip_path = tmp_path / "a.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("x.csv", b"1234567890")
    dest = tmp_path / "out.csv"

    class Boom(Exception):
        pass

    real_open = zipfile.ZipFile.open

    def broken_open(self, *a, **kw):
        f = real_open(self, *a, **kw)
        original_read = f.read
        state = {"n": 0}

        def read(n=-1):
            state["n"] += 1
            if state["n"] > 1:
                raise Boom()
            return original_read(4)
        f.read = read
        return f

    monkeypatch.setattr(zipfile.ZipFile, "open", broken_open)
    with pytest.raises(Boom):
        extract_member(zip_path, ".csv", dest)
    assert not dest.exists()
