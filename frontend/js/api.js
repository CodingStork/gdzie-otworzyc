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
// Heatmapa widocznego fragmentu mapy; `signal` pozwala przerwać zapytanie, gdy użytkownik ruszył mapą dalej.
export const view = (params, signal) => get('/api/view', params, signal);
// Dokładne liczby w okręgu zasięgu wokół klikniętego punktu (dymek).
export const point = (params) => get('/api/point', params);
export const getPoi = (type, bbox) => get('/api/poi', { type, bbox: bbox.join(',') });
export const geocode = (q) => get('/api/geocode', { q });
export const getMeta = () => get('/api/meta');
