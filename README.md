# commodity-flow-intelligence

Physical commodity flow analytics -- delivery gap detection, wellhead economics,
and derivative supply chain signals using public EIA, USGS, and AIS data.

## Thesis

Helium has no substitute and is extracted as a byproduct of natural gas
processing (cryogenic separation). **Natural gas import/production disruptions
are a leading indicator for helium supply gaps.** This project tracks physical
commodity flows to detect delivery anomalies before they surface in spot prices.

## Notebooks

### `commodity_delivery_gap_analysis.ipynb`

Analyzes crude oil tanker import delivery gaps by US PADD district, with
derivative commodity tracking for helium, natural gas, gasoline, propane/NGLs,
and lithium.

**Sections:**

1. Config + PADD definitions
2. EIA API v2 fetch functions (crude imports by PADD, weekly stocks, STEO)
3. Synthetic data generators matching EIA schema (runs without API key)
4. Data loading (live or synthetic toggle via `USE_LIVE_API`)
5. PADD-level import gap detection -- trailing 12-month z-score, red-zone highlighting
6. Weekly stock drawdown -- 4-week rate of change by PADD
7. Natural gas imports as helium leading indicator -- pipeline + LNG disruption flagging
8. Helium supply-demand gap + BLM price signal (USGS MCS structure)
9. Composite gap scorecard -- oil + natgas z-scores blended into single alert metric
10. AISstream.io tanker tracker -- async websocket for real-time vessel positions
11. Derivative commodity map -- crude, helium, LNG, gasoline, propane/NGL, lithium

**Modes:**

- `USE_LIVE_API = False` (default): Runs entirely on synthetic data -- no API key needed.
- `USE_LIVE_API = True`: Fetches live data from EIA API v2. Requires an API key.

### `wellhead_economics_by_basin.ipynb` *(planned)*

Marginal cost curves by producing basin (Permian, Eagle Ford, Bakken,
DJ/Niobrara, Appalachian). Compares prevailing WTI price against basin-level
breakeven costs to identify shut-in risk and supply contraction signals.

## Data Sources

| Source | Coverage | Access |
|--------|----------|--------|
| [EIA API v2](https://www.eia.gov/opendata/) | Crude imports, stocks, STEO, drilling productivity | Free, key required |
| [AISstream.io](https://aisstream.io) | Real-time AIS vessel tracking (tanker positions, ETAs) | Free websocket API |
| [USGS Mineral Commodity Summaries](https://www.usgs.gov/centers/national-minerals-information-center) | Helium production and supply (annual) | Public domain |
| Dallas Fed Energy Survey | Basin-level breakeven price estimates (quarterly) | Public |
| Kansas City Fed Energy Survey | Niobrara/DJ Basin breakeven coverage | Public |
| [EIA Drilling Productivity Report](https://www.eia.gov/petroleum/drilling/) | Production per rig, new-well rates by basin | Free |

## Setup

```bash
# Clone
git clone https://github.com/hb-cam/commodity-flow-intelligence.git
cd commodity-flow-intelligence

# Install dependencies
uv sync

# Run notebook
uv run jupyter lab
```

### API Keys (optional)

For live data mode, set these environment variables or edit the notebook config:

```bash
export EIA_API_KEY="your-key-here"        # https://www.eia.gov/opendata/register.php
export AISSTREAM_API_KEY="your-key-here"   # https://aisstream.io
```

## License

MIT
