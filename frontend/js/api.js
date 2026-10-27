// Cienka warstwa nad fetch: wołamy backend i zamieniamy błędy na czytelne, polskie komunikaty.

async function get(path, params = {}, signal) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') query.set(key, value);
  }
  let response;
  try {
    response = await fetch(`${path}?${query}`, { signal });
  } catch (e) {
    if (e.name === 'AbortError') throw e;   // przerwane przez nas (nowsze zapytanie) — nie jest błędem dla użytkownika
    throw new Error('Brak połączenia z serwerem. Sprawdź, czy aplikacja działa.');
  }
  if (!response.ok) {
    let message = `Błąd serwera (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') message = body.detail;
      else if (Array.isArray(body.detail)) message = 'Nieprawidłowe parametry zapytania';
    } catch (e) { /* odpowiedź nie jest JSON-em — zostaje komunikat ogólny */ }
    throw new Error(message);
  }
  return response.json();
}

export const getCatalog = () => get('/api/catalog');
// Mapa okolicy wybranego miejsca (mgła); `signal` pozwala przerwać zapytanie, gdy użytkownik zmienił ustawienia.
export const surface = (params, signal) => get('/api/surface', params, signal);
// Szczegóły klikniętego punktu: liczby w okręgu zasięgu, model Huffa, komórki do narysowania.
export const point = (params) => get('/api/point', params);
// Firmy danego typu w prostokącie — tylko do narysowania konkurentów w szczegółach punktu.
export const getPoi = (type, bbox) => get('/api/poi', { type, bbox: bbox.join(',') });
export const geocode = (q) => get('/api/geocode', { q });
export const getMeta = () => get('/api/meta');
