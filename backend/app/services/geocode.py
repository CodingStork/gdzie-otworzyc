"""Wyszukiwarka adresów: proxy do Nominatim (geokoder OpenStreetMap).

Dlaczego proxy, a nie zapytania z przeglądarki: polityka Nominatim wymaga identyfikującego
User-Agent, limitu 1 zapytania na sekundę i unikania powtórek — to łatwiej zagwarantować w jednym
miejscu (z pamięcią podręczną), niż w każdej przeglądarce osobno.
"""
import threading
import time

import httpx

from backend.app.config import USER_AGENT

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MIN_QUERY_LENGTH = 3
MAX_RESULTS = 5
MAX_CACHE_ENTRIES = 500


class GeocoderUnavailable(Exception):
    """Nominatim nie odpowiada albo zwrócił błąd."""


class Geocoder:
    def __init__(self, client: httpx.Client, min_interval_s: float = 1.0, base_url: str = NOMINATIM_URL):
        self.client = client
        self.min_interval_s = min_interval_s
        self.base_url = base_url
        self._cache: dict[str, list[dict]] = {}
        self._lock = threading.Lock()         # jedno zapytanie naraz → łatwo dotrzymać odstępu
        self._last_request: float | None = None

    def search(self, q: str) -> list[dict]:
        """Do 5 wyników `{name, lat, lng}` dla zapytania; krótsze niż 3 znaki → [] bez zapytania do sieci."""
        q = q.strip()
        if len(q) < MIN_QUERY_LENGTH:
            return []
        key = q.lower()
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            self._wait_for_turn()
            try:
                resp = self.client.get(self.base_url, headers={"User-Agent": USER_AGENT}, params={
                    "q": q, "format": "jsonv2", "countrycodes": "pl", "limit": MAX_RESULTS, "accept-language": "pl"})
                self._last_request = time.monotonic()
                if resp.status_code >= 400:
                    raise GeocoderUnavailable(f"Nominatim: HTTP {resp.status_code}")
                items = resp.json()
                results = [{"name": it["display_name"], "lat": float(it["lat"]), "lng": float(it["lon"])}
                           for it in items][:MAX_RESULTS]
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
                raise GeocoderUnavailable(str(e)) from e
            if len(self._cache) >= MAX_CACHE_ENTRIES:
                self._cache.pop(next(iter(self._cache)))      # wyrzucamy najstarszy wpis
            self._cache[key] = results
            return results

    def _wait_for_turn(self) -> None:
        """Dotrzymuje odstępu min_interval_s od poprzedniego zapytania do Nominatim."""
        if self._last_request is None:
            return
        remaining = self.min_interval_s - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)
