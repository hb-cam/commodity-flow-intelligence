# commodity-flow-intelligence

Physical commodity flow analytics -- delivery gap detection, wellhead economics,
and derivative supply chain signals using public EIA, USGS, and AIS data.

## Thesis

Helium has no substitute and is extracted as a byproduct of natural gas
processing (cryogenic separation). **Natural gas import/production disruptions
are a leading indicator for helium supply gaps.** This project tracks physical
commodity flows to detect delivery anomalies before they surface in spot prices.

## Project Structure

```
src/commodity_flow/       Python library
  config.py               .env loading, PADD/basin definitions
  eia.py                  EIA API v2 client (imports, stocks, STEO, DPR)
  ais.py                  AISstream.io async websocket tanker tracker
  synthetic.py            Synthetic data generators (EIA/USGS/Fed schemas)
  analysis.py             Z-score gap detection, composite scorecard, breakeven analysis
  futures.py              Yahoo Finance futures (WTI, NatGas, RBOB, Heating Oil)

notebooks/
  01_delivery_gap_analysis.ipynb   PADD import gaps, stock drawdowns, NatGas/helium,
                                   composite scorecard + STEO overlay, futures overlay,
                                   AIS tanker tracker, derivative commodity map
  02_wellhead_economics.ipynb      Basin breakeven analysis, production-at-risk curves,
                                   supply elasticity, rig count trends, scorecard integration

tests/                    pytest test suite (35 tests)
```

## Notebooks

### 01 — Delivery Gap Analysis

Analyzes crude oil tanker import delivery gaps by US PADD district, with
derivative commodity tracking for helium, natural gas, gasoline, propane/NGLs,
and lithium.

- PADD-level import gap detection (trailing 12-month z-score)
- Weekly stock drawdown alerting
- Natural gas imports as helium supply leading indicator
- Helium supply-demand gap + BLM price signal
- Composite gap scorecard with STEO forward projections
- Commodity futures z-score overlay (WTI, NatGas, RBOB, Heating Oil)
- Real-time AIS tanker tracking (when API key configured)
- Derivative commodity map with tradeable instruments

### 02 — Wellhead Economics by Basin

Marginal cost curves by producing basin (Permian, Eagle Ford, Bakken,
DJ/Niobrara, Appalachian, Haynesville, Anadarko).

- Basin breakeven vs WTI price (profitable / marginal / at-risk)
- Production-at-risk analysis
- Supply elasticity curve (WTI sweep $30–$100)
- Rig count trends with decline detection
- Production efficiency (output per rig)
- Breakeven trend over time
- Integration with delivery gap scorecard

## Data Sources

| Source | Coverage | Access |
|--------|----------|--------|
| [EIA API v2](https://www.eia.gov/opendata/) | Crude imports, stocks, STEO, DPR | Free, key required |
| [AISstream.io](https://aisstream.io) | Real-time AIS vessel tracking | Free websocket API |
| [USGS MCS](https://www.usgs.gov/centers/national-minerals-information-center) | Helium production (annual) | Public domain |
| Dallas/KC Fed Energy Surveys | Basin breakeven estimates (quarterly) | Public |
| Yahoo Finance | Commodity futures (WTI, NG, RBOB, HO) | Free |

## Setup

```bash
git clone https://github.com/hb-cam/commodity-flow-intelligence.git
cd commodity-flow-intelligence

# Install dependencies
uv sync

# Copy and configure API keys (optional — runs on synthetic data without them)
cp .env.example .env
# Edit .env with your API keys

# Run notebooks
uv run jupyter lab

# Run tests
uv run pytest tests/ -v
```

### API Keys (optional)

For live data mode, configure in `.env`:

```
EIA_API_KEY=your-key-here        # https://www.eia.gov/opendata/register.php
AISSTREAM_API_KEY=your-key-here  # https://aisstream.io
USE_LIVE_API=true
```

Without API keys, both notebooks run on synthetic data that mirrors real EIA schemas
with injected disruption patterns.

## License

MIT
