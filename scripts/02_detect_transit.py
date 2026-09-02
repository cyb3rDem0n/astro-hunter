import numpy as np
import lightkurve as lk
import matplotlib.pyplot as plt

TARGET = "TIC 261136679"
SECTOR = 1

print("Downloading TESS light curve...")

lc = lk.search_lightcurve(
    TARGET,
    mission="TESS",
    sector=SECTOR,
    author="SPOC"
).download()

# Basic cleaning
lc = lc.remove_nans().normalize()

# Detrend: fondamentale
flat_lc = lc.flatten(window_length=401).remove_outliers(sigma=5)

print("Computing Box Least Squares periodogram...")

periods = np.linspace(1.0, 10.0, 10000)
durations = np.linspace(0.05, 0.2, 20)

periodogram = flat_lc.to_periodogram(
    method="bls",
    period=periods,
    duration=durations
)

best_period = periodogram.period_at_max_power
best_duration = periodogram.duration_at_max_power
best_transit_time = periodogram.transit_time_at_max_power

print()
print("=== DETECTION RESULT ===")
print(f"Best period: {best_period:.6f}")
print(f"Transit duration: {best_duration}")
print(f"Transit time: {best_transit_time}")

# Plot flattened light curve
flat_lc.scatter()
plt.title("Flattened TESS Light Curve - Pi Mensae")
plt.tight_layout()
plt.savefig("outputs/pi_mensae_flattened.png", dpi=150)
plt.close()

# Plot periodogram
periodogram.plot()
plt.title("BLS Periodogram - Pi Mensae")
plt.tight_layout()
plt.savefig("outputs/pi_mensae_bls.png", dpi=150)
plt.close()

# Fold on best period
folded = flat_lc.fold(period=best_period, epoch_time=best_transit_time)
folded.scatter()
plt.title(f"Folded Light Curve - Period = {best_period.value:.5f} d")
plt.tight_layout()
plt.savefig("outputs/pi_mensae_folded.png", dpi=150)
plt.close()

print()
print("Saved:")
print("outputs/pi_mensae_flattened.png")
print("outputs/pi_mensae_bls.png")
print("outputs/pi_mensae_folded.png")