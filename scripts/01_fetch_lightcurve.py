from pathlib import Path
import sys

import matplotlib.pyplot as plt

from astro_hunter.domains.exoplanets.photometry.tess 
import download_tess_lightcurve

TARGET = "TIC 261136679"  # Pi Mensae
SECTOR = 1


def main() -> None:
    search, raw_lc, clean_lc = download_tess_lightcurve(TARGET, SECTOR)

    print("\n=== MAST SEARCH RESULT ===")
    print(search)
    print("\n=== LIGHT CURVE ===")
    print(f"Target: {TARGET}")
    print(f"Sector: {SECTOR}")
    print(f"Raw cadences: {len(raw_lc)}")
    print(f"Clean cadences: {len(clean_lc)}")
    print(f"Time span: {(clean_lc.time[-1] - clean_lc.time[0]).to_value('day'):.2f} d")

    processed = ROOT / "data" / "processed" / "pi_mensae_sector1.csv"
    figure = ROOT / "outputs" / "pi_mensae_sector1.png"
    processed.parent.mkdir(parents=True, exist_ok=True)
    figure.parent.mkdir(parents=True, exist_ok=True)

    clean_lc.to_pandas().to_csv(processed, index=False)

    ax = clean_lc.scatter(s=2, title="Pi Mensae — TESS Sector 1")
    ax.set_xlabel("Time [BTJD]")
    ax.set_ylabel("Normalized flux")
    plt.tight_layout()
    plt.savefig(figure, dpi=160)

    print(f"Saved data: {processed}")
    print(f"Saved plot: {figure}")
    print("\nMilestone 1 complete: real TESS photometry downloaded and cleaned.")


if __name__ == "__main__":
    main()
