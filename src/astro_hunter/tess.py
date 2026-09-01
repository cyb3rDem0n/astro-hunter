from __future__ import annotations

import lightkurve as lk


def search_tess_lightcurve(target: str, sector: int):
    """Search MAST for a SPOC 2-minute TESS light curve."""
    return lk.search_lightcurve(
        target,
        mission="TESS",
        sector=sector,
        author="SPOC",
        exptime=120,
    )


def download_tess_lightcurve(target: str, sector: int):
    """Download the first matching TESS light curve and perform minimal cleaning."""
    search = search_tess_lightcurve(target, sector)
    if len(search) == 0:
        raise RuntimeError(f"No TESS light curve found for {target=} {sector=}")

    lc = search.download(quality_bitmask="default")
    if lc is None:
        raise RuntimeError("MAST returned no downloadable light curve")

    # SPOC products normally expose PDCSAP_FLUX, which has instrumental
    # systematics corrected by the mission pipeline. Select it explicitly
    # when it is present so our choice is visible rather than magical.
    if "pdcsap_flux" in lc.colnames:
        lc = lc.select_flux("pdcsap_flux")

    clean = lc.remove_nans().normalize().remove_outliers(sigma=6)
    return search, lc, clean
