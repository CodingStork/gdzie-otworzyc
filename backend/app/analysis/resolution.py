"""Wybór rozdzielczości siatki H3 zależnie od wielkości analizowanego obszaru."""

# Przybliżony odstęp między środkami sąsiednich heksagonów H3 [km] w Polsce.
HEX_SPACING_KM = {8: 0.80, 7: 2.11, 6: 5.6}


def choose_resolution(radius_km: float | None) -> int:
    """Im większy obszar, tym grubsza siatka (mniej heksagonów = szybciej i czytelniej).

    None oznacza "cała Polska" → res 6 (~9 tys. heksagonów).
    """
    if radius_km is None:
        return 6
    if radius_km <= 15:
        return 8
    return 7  # 15–50 km


def effective_bandwidth_km(bandwidth_km: float, res: int) -> float:
    """Szerokość pasma jądra nie może być mniejsza niż ~0,6 odstępu heksagonów.

    Przy zbyt wąskim jądrze każdy heksagon "widziałby" tylko samego siebie, a wynik
    zależałby od przypadkowego położenia siatki (problem MAUP).
    """
    return max(bandwidth_km, 0.6 * HEX_SPACING_KM[res])
