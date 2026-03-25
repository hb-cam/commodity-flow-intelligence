# Commodity Flow Intelligence

Physical commodity flow analytics -- delivery gap detection, wellhead economics, and derivative supply chain signals using public government data.

## Thesis

Helium has no substitute and is extracted as a byproduct of natural gas processing. **Natural gas import and production disruptions are a leading indicator for helium supply gaps.** More broadly, physical delivery data from the EIA reveals supply-demand imbalances weeks before they surface in spot prices.

This project combines:
- **PADD-level crude import gap detection** using trailing z-scores
- **Wellhead economics** linking basin breakeven costs to shut-in risk
- **Commodity futures overlays** to identify physical-vs-market divergence
- **Real-time tanker tracking** via AIS vessel data

All analysis runs on free, public data. No API keys are required to explore the notebooks -- synthetic data mirrors real EIA schemas with injected disruption patterns.

---

### Run the Notebooks

#### Run in Colab
Both notebooks are configured to run in **Google Colab** with zero local setup.

| Notebook | Focus | Link |
| :--- | :--- | :--- |
| **Delivery Gap Analysis** | PADD import gaps, stock drawdowns, NatGas/helium correlation, composite scorecard, futures overlay, AIS tanker tracking | [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/hb-cam/commodity-flow-intelligence/blob/main/notebooks/01_delivery_gap_analysis.ipynb) |
| **Wellhead Economics** | Basin breakeven analysis, production-at-risk curves, supply elasticity, rig count trends, scorecard integration | [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/hb-cam/commodity-flow-intelligence/blob/main/notebooks/02_wellhead_economics.ipynb) |

> [!TIP]
> **Using live EIA data in Colab:** When the notebook opens, you will be prompted to enter your [EIA API key](https://www.eia.gov/opendata/register.php) (free, instant registration). Press Enter to skip and use synthetic data instead.

#### Run locally
```bash
git clone https://github.com/hb-cam/commodity-flow-intelligence.git
cd commodity-flow-intelligence
uv sync
uv run jupyter lab
```

Open either notebook from the `notebooks/` directory. Both ship with synthetic data so you can read and run them without any API keys.

### Run Tests

```bash
uv run pytest -v                       # All 111 tests
uv run pytest tests/test_security.py   # Security checks only
uv run pytest tests/test_verification.py  # Domain sanity checks only
```

---

## What's Inside

| Path | Description |
|------|-------------|
| `notebooks/01_delivery_gap_analysis.ipynb` | PADD import gaps, stock drawdowns, NatGas/helium, composite scorecard + STEO forward overlay, futures z-scores, AIS tanker tracker, derivative commodity map |
| `notebooks/02_wellhead_economics.ipynb` | Basin breakevens vs WTI, production-at-risk, supply elasticity curve, rig count trends, output per rig, scorecard integration |
| `src/commodity_flow/eia.py` | EIA API v2 client -- crude imports, stocks, STEO projections, natural gas imports |
| `src/commodity_flow/analysis.py` | Z-score gap detection, composite scorecard, breakeven analysis, supply curves |
| `src/commodity_flow/futures.py` | Yahoo Finance futures overlay (WTI, NatGas, RBOB, Heating Oil) |
| `src/commodity_flow/ais.py` | AISstream.io async websocket client for real-time tanker tracking |
| `src/commodity_flow/synthetic.py` | Synthetic data generators baselined to real EIA/USGS/Fed survey data |
| `src/commodity_flow/provenance.py` | Data provenance tracker -- logs live vs synthetic source per dataset |
| `src/commodity_flow/refresh.py` | Data refresh pipeline with 20 built-in validation checks |
| `tests/` | 111 tests: domain verification, security, analysis, EIA client, provenance, futures, AIS |

## Data Sources

All data sources are free and publicly available.

| Source | What It Provides | Access |
|--------|-----------------|--------|
| [EIA API v2](https://www.eia.gov/opendata/) | Crude imports by PADD, weekly petroleum stocks, STEO forward projections, natural gas imports (pipeline + LNG split) | Free, [register for key](https://www.eia.gov/opendata/register.php) |
| [AISstream.io](https://aisstream.io) | Real-time AIS vessel tracking -- tanker positions, ETAs, destinations | Free websocket API |
| [USGS Mineral Commodity Summaries](https://www.usgs.gov/centers/national-minerals-information-center) | Helium production and supply (annual) | Public domain |
| Dallas / Kansas City Fed Energy Surveys | Basin-level breakeven price estimates (quarterly) | Public |
| [Yahoo Finance](https://finance.yahoo.com) | Commodity futures: WTI crude, natural gas, RBOB gasoline, heating oil | Free, no key needed |

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- A free [EIA API key](https://www.eia.gov/opendata/register.php) (optional -- synthetic data works without it)

### Setup

```bash
git clone https://github.com/hb-cam/commodity-flow-intelligence.git
cd commodity-flow-intelligence

# Install dependencies
uv sync

# Configure API keys (optional)
cp .env.example .env
# Edit .env and add your keys
```

### API Keys

| Key | Required? | How to Get |
|-----|-----------|-----------|
| EIA API | Optional | Free at [eia.gov/opendata](https://www.eia.gov/opendata/register.php) -- enables live import/stock/STEO data |
| AISstream.io | Optional | Free at [aisstream.io](https://aisstream.io) -- enables real-time tanker tracking |

Set them in `.env`:
```
EIA_API_KEY=your-key-here
AISSTREAM_API_KEY=your-key-here
USE_LIVE_API=true
```

Without keys, both notebooks run on synthetic data that mirrors real EIA schemas with injected disruption patterns for realistic analysis.

## Key Concepts

### Delivery Gap Detection
Each PADD (Petroleum Administration for Defense District) has a trailing 12-month import average. When actual imports fall more than 1 standard deviation below this norm, a **delivery gap** is flagged. Gaps across multiple PADDs compound into the composite scorecard.

### Composite Gap Scorecard
Blends oil import z-scores with natural gas import z-scores into a single delivery-risk metric. The STEO forward overlay extends the scorecard into forecast territory using EIA's Short Term Energy Outlook.

### Wellhead Economics
At prevailing WTI price, which producing basins are above or below breakeven? When price drops below marginal cost, wells shut in, supply contracts, and delivery gaps widen downstream. The **supply elasticity curve** sweeps WTI from $30 to $100 and plots cumulative production at risk.

### Physical vs. Market Divergence
The futures overlay compares physical delivery gap z-scores with commodity futures price z-scores. **Divergence** suggests the physical supply is tighter or looser than the market is pricing.

## Tech Stack

- **Python:** pandas, numpy, matplotlib, requests, aiohttp, yfinance
- **Data:** EIA API v2, AISstream.io, USGS, Dallas/KC Fed Surveys, Yahoo Finance
- **Package management:** uv
- **Testing:** pytest (111 tests -- domain verification, security, analysis, integration)

## Contributing

Contributions are welcome. Whether you are adding a new data source, improving the analysis, or fixing a bug:

1. **Fork & Clone**: Fork the repository and clone locally.
2. **Setup**: Run `uv sync` to install all dependencies.
3. **Branch**: Create a feature branch (`git checkout -b feature/your-feature`).
4. **Test**: Run `uv run pytest -v` before submitting. All 111 tests should pass.
5. **PR**: Open a pull request with a clear description.

> [!NOTE]
> Both notebooks include a **data provenance table** that tracks which datasets are live vs synthetic, row counts, and date ranges. If you add a new data source, wire it through `provenance.py` and `refresh.py`.

## Contact

- **LinkedIn:** [hicksbruce](https://www.linkedin.com/in/hicksbruce)
- **GitHub:** [@hb-cam](https://github.com/hb-cam)

---

**License:** MIT -- see [LICENSE](LICENSE) for details.
