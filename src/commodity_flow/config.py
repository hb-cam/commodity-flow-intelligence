"""Configuration: environment variables, PADD definitions, basin constants."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")

# API keys
EIA_API_KEY: str | None = os.getenv("EIA_API_KEY")
AISSTREAM_API_KEY: str | None = os.getenv("AISSTREAM_API_KEY")
USE_LIVE_API: bool = os.getenv("USE_LIVE_API", "false").lower() in ("true", "1", "yes")

# Petroleum Administration for Defense Districts
PADDS: dict[str, str] = {
    "PADD 1": "East Coast",
    "PADD 2": "Midwest",
    "PADD 3": "Gulf Coast",
    "PADD 4": "Rocky Mountain",
    "PADD 5": "West Coast",
}

# EIA duoarea codes for PADDs (API uses -Z00 suffix)
PADD_DUOAREA_CODES: dict[str, str] = {
    "PADD 1": "R10-Z00",
    "PADD 2": "R20-Z00",
    "PADD 3": "R30-Z00",
    "PADD 4": "R40-Z00",
    "PADD 5": "R50-Z00",
}

# Approximate import baselines (thousand barrels/month) for synthetic data
PADD_IMPORT_BASELINES: dict[str, int] = {
    "PADD 1": 40_000,
    "PADD 2": 8_000,
    "PADD 3": 130_000,
    "PADD 4": 2_000,
    "PADD 5": 20_000,
}

# Approximate stock baselines (thousand barrels) for synthetic data
PADD_STOCK_BASELINES: dict[str, int] = {
    "PADD 1": 12_000,
    "PADD 2": 95_000,
    "PADD 3": 270_000,
    "PADD 4": 22_000,
    "PADD 5": 50_000,
}

# Producing basins for wellhead economics
BASINS: dict[str, dict[str, str]] = {
    "Permian": {"state": "TX/NM", "play": "Wolfcamp/Bone Spring/Spraberry"},
    "Eagle Ford": {"state": "TX", "play": "Eagle Ford Shale"},
    "Bakken": {"state": "ND/MT", "play": "Bakken/Three Forks"},
    "DJ/Niobrara": {"state": "CO/WY", "play": "Niobrara/Codell"},
    "Appalachian": {"state": "PA/WV/OH", "play": "Marcellus/Utica"},
    "Haynesville": {"state": "LA/TX", "play": "Haynesville/Bossier"},
    "Anadarko": {"state": "OK", "play": "SCOOP/STACK/Woodford"},
}

# Matplotlib defaults
PLOT_STYLE = "seaborn-v0_8-darkgrid"
PLOT_FIGSIZE = (14, 6)
PLOT_FONTSIZE = 11
