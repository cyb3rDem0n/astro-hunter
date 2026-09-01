# Astro Hunter

Learning-first project for scientific analysis of open astronomical data.

## Milestone 1

Download a real TESS light curve for **Pi Mensae / TIC 261136679**, Sector 1,
perform minimal cleaning, save the processed time series, and plot it.

The known planet signal is deliberately **not** used by the code yet. The next
milestone will ask Box Least Squares (BLS) to recover the period from the data.

## Setup

Python 3.11 or 3.12 is recommended.

### Windows PowerShell

```powershell
cd astro-hunter
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts\01_fetch_lightcurve.py
```

### macOS / Linux

```bash
cd astro-hunter
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts/01_fetch_lightcurve.py
```

The first run needs an Internet connection because Lightkurve queries and
downloads data from MAST.

## Expected outputs

- `data/processed/pi_mensae_sector1.csv`
- `outputs/pi_mensae_sector1.png`

## Architecture, for now

```text
MAST/TESS
   |
   v
Lightkurve search/download
   |
   v
minimal cleaning
   |
   +--> CSV
   +--> plot
```

Keep it boring at first. Reproducible science before agents.
