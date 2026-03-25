"""Plotly chart functions for commodity flow intelligence.

Each function returns a plotly Figure. Designed for interactive exploration
in Jupyter/Colab with hover tooltips, zoom, and annotation callouts.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Consistent color palette
COLORS = {
    "oil": "#2563eb",
    "natgas": "#7c3aed",
    "composite": "#dc2626",
    "forecast": "#f97316",
    "warning": "#f59e0b",
    "critical": "#ef4444",
    "ok": "#22c55e",
    "neutral": "#64748b",
    "spr": "#f97316",
    "commercial": "#2563eb",
    "gasoline": "#22c55e",
    "distillate": "#2563eb",
    "jet": "#7c3aed",
    "propane": "#f97316",
    "heating_oil": "#ea580c",
    "wti": "#1e293b",
}

LAYOUT_DEFAULTS = dict(
    template="plotly_white",
    font=dict(family="Inter, system-ui, sans-serif", size=12),
    hovermode="x unified",
    margin=dict(l=60, r=30, t=60, b=40),
)


def plot_scorecard(scorecard: pd.DataFrame) -> go.Figure:
    """Composite gap scorecard with STEO forecast overlay."""
    actual = scorecard[~scorecard["is_forecast"]]
    forecast = scorecard[scorecard["is_forecast"]]

    fig = go.Figure()

    # Oil z-score
    fig.add_trace(
        go.Scatter(
            x=actual.index,
            y=actual["oil_import_z"],
            name="Oil Import Z",
            line=dict(color=COLORS["oil"], width=1.5),
            hovertemplate="Oil: %{y:.2f}<extra></extra>",
        )
    )

    # NatGas z-score
    fig.add_trace(
        go.Scatter(
            x=actual.index,
            y=actual["natgas_import_z"],
            name="NatGas Import Z",
            line=dict(color=COLORS["natgas"], width=1.5),
            hovertemplate="NatGas: %{y:.2f}<extra></extra>",
        )
    )

    # Composite
    fig.add_trace(
        go.Scatter(
            x=actual.index,
            y=actual["composite_gap_score"],
            name="Composite Gap Score",
            line=dict(color=COLORS["composite"], width=3),
            hovertemplate="Composite: %{y:.2f}<extra></extra>",
        )
    )

    # STEO forecast
    if not forecast.empty:
        bridge = pd.concat([actual.tail(1), forecast])
        fig.add_trace(
            go.Scatter(
                x=bridge.index,
                y=bridge["composite_gap_score"],
                name="STEO Forecast",
                line=dict(color=COLORS["forecast"], width=2, dash="dash"),
                hovertemplate="Forecast: %{y:.2f}<extra></extra>",
            )
        )
        fig.add_vrect(
            x0=forecast.index.min(),
            x1=forecast.index.max(),
            fillcolor=COLORS["warning"],
            opacity=0.05,
            annotation_text="Forecast",
            annotation_position="top left",
        )

    # Threshold lines
    fig.add_hline(
        y=-1,
        line=dict(color=COLORS["warning"], dash="dash", width=1),
        annotation_text="Warning (-1\u03c3)",
        annotation_position="bottom left",
    )
    fig.add_hline(
        y=-2,
        line=dict(color=COLORS["critical"], dash="dash", width=1),
        annotation_text="Critical (-2\u03c3)",
        annotation_position="bottom left",
    )
    fig.add_hline(y=0, line=dict(color="black", width=0.5))

    # Shade critical zone
    critical_mask = actual["composite_gap_score"] < -2
    if critical_mask.any():
        for start, end in _contiguous_ranges(actual.index[critical_mask]):
            fig.add_vrect(x0=start, x1=end, fillcolor=COLORS["critical"], opacity=0.15)

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title="Composite Delivery Gap Scorecard",
        yaxis_title="Z-Score (negative = below normal)",
        legend=dict(orientation="h", y=-0.15),
        height=450,
    )
    return fig


def plot_elasticity_curve(risk_curve: pd.DataFrame, current_wti: float) -> go.Figure:
    """Supply elasticity: production at risk vs WTI price."""
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=["Production at Risk (bbl/d)", "% of US Production at Risk"],
    )

    # Absolute
    fig.add_trace(
        go.Scatter(
            x=risk_curve["wti_price"],
            y=risk_curve["production_at_risk_bbl_d"],
            fill="tozeroy",
            fillcolor="rgba(239,68,68,0.15)",
            line=dict(color=COLORS["critical"], width=2.5),
            hovertemplate="$%{x}/bbl: %{y:,.0f} bbl/d at risk<extra></extra>",
            name="At Risk (bbl/d)",
        ),
        row=1,
        col=1,
    )

    # Percentage
    fig.add_trace(
        go.Scatter(
            x=risk_curve["wti_price"],
            y=risk_curve["pct_at_risk"],
            fill="tozeroy",
            fillcolor="rgba(239,68,68,0.15)",
            line=dict(color=COLORS["critical"], width=2.5),
            hovertemplate="$%{x}/bbl: %{y:.1f}% at risk<extra></extra>",
            name="At Risk (%)",
        ),
        row=1,
        col=2,
    )

    # WTI reference line on both
    for col in [1, 2]:
        fig.add_vline(
            x=current_wti,
            row=1,
            col=col,
            line=dict(color=COLORS["wti"], width=2.5, dash="dash"),
            annotation_text=f"Current WTI ${current_wti:.0f}",
        )

    # 25% threshold on pct chart
    fig.add_hline(
        y=25,
        row=1,
        col=2,
        line=dict(color=COLORS["warning"], dash="dot"),
        annotation_text="25% threshold",
    )

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title="US Shale Marginal Cost Curve — What Breaks at Each Price?",
        showlegend=False,
        height=400,
    )
    fig.update_xaxes(title_text="WTI Price ($/bbl)")
    return fig


def plot_days_of_supply(df_dos: pd.DataFrame) -> go.Figure:
    """Days of supply by product with danger thresholds."""
    products = sorted(df_dos["product"].unique())
    n = len(products)
    fig = make_subplots(
        rows=1,
        cols=min(n, 4),
        subplot_titles=[
            df_dos[df_dos["product"] == p]["product_name"].iloc[0]
            if "product_name" in df_dos.columns
            else p
            for p in products[:4]
        ],
    )

    thresholds = {"EPM0": 25, "EPD0": 30, "EPJK": 25, "EPLLPZ": 40, "EPPR": 50}
    prod_colors = {
        "EPM0": COLORS["gasoline"],
        "EPD0": COLORS["distillate"],
        "EPJK": COLORS["jet"],
        "EPLLPZ": COLORS["propane"],
        "EPPR": COLORS["neutral"],
    }

    for i, prod in enumerate(products[:4]):
        sub = df_dos[df_dos["product"] == prod].sort_values("date")
        col = i + 1
        c = prod_colors.get(prod, COLORS["neutral"])

        fig.add_trace(
            go.Scatter(
                x=sub["date"],
                y=sub["days_of_supply"],
                line=dict(color=c, width=2),
                hovertemplate="%{y:.1f} days<extra></extra>",
                name=prod,
                showlegend=False,
            ),
            row=1,
            col=col,
        )

        if prod in thresholds:
            fig.add_hline(
                y=thresholds[prod],
                row=1,
                col=col,
                line=dict(color=COLORS["critical"], dash="dot", width=1),
                annotation_text=f"{thresholds[prod]}d",
            )

        fig.update_yaxes(title_text="Days" if col == 1 else "", row=1, col=col)

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title="Days of Supply by Product",
        height=350,
    )
    return fig


def plot_seasonal_comparison(df_seasonal: pd.DataFrame, product: str) -> go.Figure:
    """Current year stocks vs 5-year seasonal range."""
    sub = df_seasonal[df_seasonal["product"] == product].sort_values("week_of_year")
    name = sub["product_name"].iloc[0] if "product_name" in sub.columns else product

    fig = go.Figure()

    # 5-year range (shaded band)
    fig.add_trace(
        go.Scatter(
            x=sub["week_of_year"],
            y=sub["max_5yr"],
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=sub["week_of_year"],
            y=sub["min_5yr"],
            fill="tonexty",
            fillcolor="rgba(100,116,139,0.15)",
            line=dict(width=0),
            name="5yr Range",
            hovertemplate="5yr range: %{y:,.0f}<extra></extra>",
        )
    )

    # 5-year average
    fig.add_trace(
        go.Scatter(
            x=sub["week_of_year"],
            y=sub["avg_5yr"],
            line=dict(color=COLORS["neutral"], dash="dash", width=1.5),
            name="5yr Avg",
            hovertemplate="5yr avg: %{y:,.0f}<extra></extra>",
        )
    )

    # Current year
    fig.add_trace(
        go.Scatter(
            x=sub["week_of_year"],
            y=sub["current"],
            line=dict(color=COLORS["composite"], width=2.5),
            name="Current Year",
            hovertemplate="Current: %{y:,.0f} MBBL<br>Week %{x}<extra></extra>",
        )
    )

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=f"{name} — Current Year vs 5-Year Seasonal Range",
        xaxis_title="Week of Year",
        yaxis_title="MBBL",
        height=400,
    )
    return fig


def plot_spr_status(df_spr: pd.DataFrame) -> go.Figure:
    """SPR vs commercial crude stocks — stacked area with share trend."""
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=["Crude Oil Stocks: SPR vs Commercial", "SPR Share of Total"],
    )

    fig.add_trace(
        go.Scatter(
            x=df_spr["date"],
            y=df_spr["commercial_mbbl"],
            fill="tozeroy",
            fillcolor="rgba(37,99,235,0.3)",
            line=dict(color=COLORS["commercial"], width=1),
            name="Commercial",
            hovertemplate="Commercial: %{y:,.0f} MBBL<extra></extra>",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df_spr["date"],
            y=df_spr["total_mbbl"],
            fill="tonexty",
            fillcolor="rgba(249,115,22,0.3)",
            line=dict(color=COLORS["spr"], width=1),
            name="SPR",
            hovertemplate="Total: %{y:,.0f} MBBL<extra></extra>",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df_spr["date"],
            y=df_spr["spr_pct"],
            fill="tozeroy",
            fillcolor="rgba(249,115,22,0.15)",
            line=dict(color=COLORS["spr"], width=2),
            name="SPR %",
            showlegend=False,
            hovertemplate="SPR: %{y:.1f}%<extra></extra>",
        ),
        row=1,
        col=2,
    )

    fig.add_hline(
        y=50, row=1, col=2, line=dict(color=COLORS["neutral"], dash="dash"), annotation_text="50%"
    )

    fig.update_layout(**LAYOUT_DEFAULTS, height=400, title="Strategic Petroleum Reserve Status")
    fig.update_yaxes(title_text="MBBL", row=1, col=1)
    fig.update_yaxes(title_text="SPR %", row=1, col=2)
    return fig


def plot_basin_breakevens(status: pd.DataFrame, current_wti: float) -> go.Figure:
    """Basin breakeven vs WTI — horizontal bars with profitability color."""
    status = status.sort_values("breakeven_usd_bbl")

    color_map = {
        "profitable": COLORS["ok"],
        "marginal": COLORS["warning"],
        "at risk": COLORS["critical"],
    }
    colors = [color_map.get(s, COLORS["neutral"]) for s in status["status"]]

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            y=status["basin"],
            x=status["breakeven_usd_bbl"],
            orientation="h",
            marker_color=colors,
            text=[f"${m:+.0f}" for m in status["margin_usd_bbl"]],
            textposition="outside",
            textfont=dict(size=11),
            hovertemplate=(
                "%{y}<br>Breakeven: $%{x:.1f}/bbl<br>"
                "Margin: %{text}<br>Play: %{customdata}<extra></extra>"
            ),
            customdata=status["play"] if "play" in status.columns else None,
        )
    )

    fig.add_vline(
        x=current_wti,
        line=dict(color=COLORS["wti"], width=2.5, dash="dash"),
        annotation_text=f"WTI ${current_wti:.0f}",
    )

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=f"Basin Breakeven vs WTI ${current_wti:.0f}/bbl",
        xaxis_title="Breakeven Price ($/bbl)",
        height=400,
    )
    return fig


def plot_futures_divergence(df_futures: pd.DataFrame) -> go.Figure:
    """Commodity futures z-scores — divergence from physical gap."""
    fig = go.Figure()

    symbol_colors = {
        "CL=F": COLORS["oil"],
        "NG=F": COLORS["natgas"],
        "RB=F": COLORS["gasoline"],
        "HO=F": COLORS["heating_oil"],
    }

    for symbol in df_futures["symbol"].unique():
        sub = df_futures[df_futures["symbol"] == symbol].sort_values("date")
        name = sub["name"].iloc[0] if "name" in sub.columns else symbol
        c = symbol_colors.get(symbol, COLORS["neutral"])

        fig.add_trace(
            go.Scatter(
                x=sub["date"],
                y=sub["futures_z"],
                name=name,
                line=dict(color=c, width=1.5),
                hovertemplate=f"{name}<br>Z: %{{y:.2f}}<br>${{customdata:.2f}}<extra></extra>",
                customdata=sub["close"],
            )
        )

    fig.add_hline(y=1, line=dict(color=COLORS["ok"], dash="dash", width=0.8))
    fig.add_hline(y=-1, line=dict(color=COLORS["critical"], dash="dash", width=0.8))
    fig.add_hline(y=0, line=dict(color="black", width=0.5))

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title="Commodity Futures Z-Scores — Physical vs Market",
        yaxis_title="Price Z-Score",
        legend=dict(orientation="h", y=-0.15),
        height=400,
    )
    return fig


def plot_risk_dashboard(
    scorecard: pd.DataFrame,
    status: pd.DataFrame,
    df_spr: pd.DataFrame,
    df_dos: pd.DataFrame,
    current_wti: float,
) -> go.Figure:
    """Executive risk dashboard — 2x2 grid for NB03."""
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=[
            "Composite Gap Score (12mo)",
            "Basin Profitability",
            "Days of Supply (Latest)",
            "SPR Level",
        ],
        vertical_spacing=0.15,
        horizontal_spacing=0.1,
    )

    # TL: Scorecard last 12 months
    actual = scorecard[~scorecard["is_forecast"]]
    recent = actual.tail(52) if len(actual) > 52 else actual
    fig.add_trace(
        go.Scatter(
            x=recent.index,
            y=recent["composite_gap_score"],
            line=dict(color=COLORS["composite"], width=2.5),
            fill="tozeroy",
            fillcolor="rgba(220,38,38,0.1)",
            name="Gap Score",
            showlegend=False,
            hovertemplate="%{y:.2f}\u03c3<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_hline(y=-1, row=1, col=1, line=dict(color=COLORS["warning"], dash="dash", width=1))
    fig.add_hline(y=0, row=1, col=1, line=dict(color="black", width=0.3))

    # TR: Basin breakevens
    status_sorted = status.sort_values("breakeven_usd_bbl")
    color_map = {
        "profitable": COLORS["ok"],
        "marginal": COLORS["warning"],
        "at risk": COLORS["critical"],
    }
    bar_colors = [color_map.get(s, COLORS["neutral"]) for s in status_sorted["status"]]
    fig.add_trace(
        go.Bar(
            y=status_sorted["basin"],
            x=status_sorted["breakeven_usd_bbl"],
            orientation="h",
            marker_color=bar_colors,
            name="Breakeven",
            showlegend=False,
            hovertemplate="%{y}: $%{x:.0f}/bbl<extra></extra>",
        ),
        row=1,
        col=2,
    )
    fig.add_vline(x=current_wti, row=1, col=2, line=dict(color=COLORS["wti"], width=2, dash="dash"))

    # BL: Days of supply latest
    if not df_dos.empty:
        latest_dos = df_dos.sort_values("date").groupby("product").last().reset_index()
        thresholds = {"EPM0": 25, "EPD0": 30, "EPJK": 25, "EPLLPZ": 40}
        dos_colors = []
        for _, row in latest_dos.iterrows():
            thresh = thresholds.get(row["product"], 30)
            dos_colors.append(
                COLORS["critical"] if row["days_of_supply"] < thresh else COLORS["ok"]
            )

        fig.add_trace(
            go.Bar(
                x=latest_dos["product_name"]
                if "product_name" in latest_dos.columns
                else latest_dos["product"],
                y=latest_dos["days_of_supply"],
                marker_color=dos_colors,
                name="DoS",
                showlegend=False,
                hovertemplate="%{x}: %{y:.0f} days<extra></extra>",
            ),
            row=2,
            col=1,
        )

    # BR: SPR level
    if not df_spr.empty:
        fig.add_trace(
            go.Scatter(
                x=df_spr["date"],
                y=df_spr["spr_mbbl"] / 1000,
                line=dict(color=COLORS["spr"], width=2),
                fill="tozeroy",
                fillcolor="rgba(249,115,22,0.15)",
                name="SPR",
                showlegend=False,
                hovertemplate="%{y:.0f}M bbl<extra></extra>",
            ),
            row=2,
            col=2,
        )
        fig.update_yaxes(title_text="Million bbl", row=2, col=2)

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title="Commodity Flow Intelligence — Risk Dashboard",
        height=650,
        showlegend=False,
    )
    return fig


def build_signal_table(
    scorecard: pd.DataFrame,
    df_imports: pd.DataFrame,
    df_dos: pd.DataFrame,
    df_spr: pd.DataFrame,
    status: pd.DataFrame,
    df_dpr: pd.DataFrame,
) -> pd.DataFrame:
    """Compute signal status table for market briefing."""
    signals: list[dict] = []
    actual = scorecard[~scorecard["is_forecast"]]

    # Composite gap score
    if not actual.empty:
        latest_z = actual["composite_gap_score"].iloc[-1]
        signals.append(
            {
                "Signal": "Composite Gap Score",
                "Current": f"{latest_z:.1f}\u03c3",
                "Threshold": "-1.0\u03c3",
                "Status": "\U0001f534 ALERT"
                if latest_z < -2
                else "\u26a0\ufe0f WARNING"
                if latest_z < -1
                else "\u2705 OK",
            }
        )

    # PADD 3 import gap
    if not df_imports.empty:
        padd3 = df_imports[df_imports["duoarea"] == "PADD 3"].sort_values("date")
        if len(padd3) >= 12:
            ma12 = padd3["value"].rolling(12).mean().iloc[-1]
            latest_val = padd3["value"].iloc[-1]
            pct_gap = (latest_val - ma12) / ma12 * 100
            signals.append(
                {
                    "Signal": "PADD 3 Import Gap",
                    "Current": f"{pct_gap:+.0f}%",
                    "Threshold": "-10%",
                    "Status": "\U0001f534 ALERT"
                    if pct_gap < -15
                    else "\u26a0\ufe0f WARNING"
                    if pct_gap < -10
                    else "\u2705 OK",
                }
            )

    # Days of supply per product
    thresholds = {"EPM0": ("Gasoline DoS", 25), "EPD0": ("Distillate DoS", 30)}
    if not df_dos.empty:
        latest_dos = df_dos.sort_values("date").groupby("product").last()
        for prod, (label, thresh) in thresholds.items():
            if prod in latest_dos.index:
                dos_val = latest_dos.loc[prod, "days_of_supply"]
                signals.append(
                    {
                        "Signal": label,
                        "Current": f"{dos_val:.0f}d",
                        "Threshold": f"{thresh}d",
                        "Status": "\U0001f534 ALERT"
                        if dos_val < thresh * 0.8
                        else "\u26a0\ufe0f WATCH"
                        if dos_val < thresh
                        else "\u2705 OK",
                    }
                )

    # SPR level
    if not df_spr.empty:
        latest_spr = df_spr.dropna().iloc[-1]["spr_mbbl"]
        signals.append(
            {
                "Signal": "SPR Level",
                "Current": f"{latest_spr / 1000:.0f}M bbl",
                "Threshold": "400M bbl",
                "Status": "\u26a0\ufe0f LOW" if latest_spr < 400_000 else "\u2705 OK",
            }
        )

    # Basins below breakeven
    n_at_risk = (status["status"] == "at risk").sum()
    n_total = len(status)
    signals.append(
        {
            "Signal": "Basins Below Breakeven",
            "Current": f"{n_at_risk}/{n_total}",
            "Threshold": "3/7",
            "Status": "\U0001f534 ALERT"
            if n_at_risk >= 3
            else "\u26a0\ufe0f WATCH"
            if n_at_risk >= 2
            else "\u2705 OK",
        }
    )

    # Rig count trend
    if not df_dpr.empty:
        latest_rigs = df_dpr.sort_values("date").groupby("basin")["rig_count"].last().sum()
        rigs_3mo_ago = df_dpr.sort_values("date").groupby("basin").nth(-3)
        if "rig_count" in rigs_3mo_ago.columns:
            rigs_3mo = rigs_3mo_ago["rig_count"].sum()
            if rigs_3mo > 0:
                rig_trend = (latest_rigs - rigs_3mo) / rigs_3mo * 100
                signals.append(
                    {
                        "Signal": "Rig Count Trend (3mo)",
                        "Current": f"{rig_trend:+.0f}%",
                        "Threshold": "-10%",
                        "Status": "\u26a0\ufe0f DECLINING"
                        if rig_trend < -10
                        else "\u26a0\ufe0f WATCH"
                        if rig_trend < -5
                        else "\u2705 OK",
                    }
                )

    return pd.DataFrame(signals)


def plot_distillate_sankey() -> go.Figure:
    """Distillate supply chain Sankey: crude → refinery → products → end use.

    Volumes are approximate annual US averages (million bbl/d) from EIA.
    """
    # Nodes: source → intermediate → product → end use
    labels = [
        # Sources (0-2)
        "Domestic Crude (13.5M)",
        "Imported Crude (6.3M)",
        "NGL / Other (3.2M)",
        # Refinery (3)
        "US Refineries",
        # Products (4-9)
        "Motor Gasoline (9.0M)",
        "Distillate Fuel Oil (5.0M)",
        "Jet Fuel / Kerosene (1.7M)",
        "Residual Fuel Oil (0.3M)",
        "LPG / Propane (2.5M)",
        "Other Products (4.0M)",
        # Distillate end use (10-14)
        "On-Highway Diesel (3.3M)",
        "Heating Oil (0.5M)",
        "Industrial / Farm (0.7M)",
        "Railroad / Marine (0.3M)",
        "Electric Power (0.2M)",
    ]

    # Links: source → target, value in million bbl/d
    sources = [0, 1, 2, 3, 3, 3, 3, 3, 3, 5, 5, 5, 5, 5]
    targets = [3, 3, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    values = [13.5, 6.3, 3.2, 9.0, 5.0, 1.7, 0.3, 2.5, 4.0, 3.3, 0.5, 0.7, 0.3, 0.2]

    # Colors by product type
    link_colors = [
        "rgba(37,99,235,0.3)",  # domestic crude
        "rgba(37,99,235,0.2)",  # imported crude
        "rgba(100,116,139,0.2)",  # NGL
        "rgba(34,197,94,0.3)",  # gasoline
        "rgba(234,88,12,0.4)",  # distillate (highlighted)
        "rgba(124,58,237,0.3)",  # jet fuel
        "rgba(100,116,139,0.2)",  # resid
        "rgba(249,115,22,0.3)",  # LPG
        "rgba(100,116,139,0.2)",  # other
        "rgba(234,88,12,0.5)",  # diesel (highlighted)
        "rgba(234,88,12,0.4)",  # heating oil
        "rgba(234,88,12,0.3)",  # industrial
        "rgba(234,88,12,0.3)",  # railroad
        "rgba(234,88,12,0.2)",  # electric
    ]

    node_colors = (
        ["#2563eb"] * 3  # sources
        + ["#64748b"]  # refinery
        + ["#22c55e", "#ea580c", "#7c3aed", "#94a3b8", "#f97316", "#94a3b8"]  # products
        + ["#ea580c"] * 5  # distillate end use
    )

    fig = go.Figure(
        go.Sankey(
            arrangement="snap",
            node=dict(
                pad=15,
                thickness=20,
                line=dict(color="black", width=0.5),
                label=labels,
                color=node_colors,
            ),
            link=dict(source=sources, target=targets, value=values, color=link_colors),
        )
    )

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title="US Petroleum Supply Chain — Distillate Flow Highlighted (million bbl/d)",
        height=500,
    )
    return fig


def plot_seasonal_decomposition(
    series: pd.Series, period: int = 52, title: str = "Seasonal Decomposition"
) -> go.Figure:
    """STL decomposition of a time series into trend, seasonal, residual.

    Uses robust STL (Loess) from statsmodels. Residual spikes indicate
    structural breaks or supply disruptions not explained by normal patterns.
    """
    from statsmodels.tsa.seasonal import STL

    stl = STL(series.dropna(), period=period, robust=True)
    result = stl.fit()

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        subplot_titles=["Observed", "Trend", "Seasonal", "Residual"],
        vertical_spacing=0.05,
    )

    fig.add_trace(
        go.Scatter(
            x=series.index,
            y=series.values,
            line=dict(color=COLORS["oil"], width=1),
            name="Observed",
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=result.trend.index,
            y=result.trend.values,
            line=dict(color=COLORS["composite"], width=2),
            name="Trend",
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=result.seasonal.index,
            y=result.seasonal.values,
            line=dict(color=COLORS["natgas"], width=1),
            name="Seasonal",
            showlegend=False,
        ),
        row=3,
        col=1,
    )

    # Residuals with anomaly highlighting
    residuals = result.resid
    resid_std = residuals.std()
    anomaly_mask = residuals.abs() > 2 * resid_std

    fig.add_trace(
        go.Scatter(
            x=residuals.index,
            y=residuals.values,
            line=dict(color=COLORS["neutral"], width=1),
            name="Residual",
            showlegend=False,
        ),
        row=4,
        col=1,
    )

    if anomaly_mask.any():
        fig.add_trace(
            go.Scatter(
                x=residuals.index[anomaly_mask],
                y=residuals.values[anomaly_mask],
                mode="markers",
                marker=dict(color=COLORS["critical"], size=6),
                name="Anomaly (>2\u03c3)",
                hovertemplate="Residual: %{y:,.0f}<extra>Anomaly</extra>",
            ),
            row=4,
            col=1,
        )

    fig.add_hline(
        y=2 * resid_std, row=4, col=1, line=dict(color=COLORS["critical"], dash="dot", width=0.8)
    )
    fig.add_hline(
        y=-2 * resid_std, row=4, col=1, line=dict(color=COLORS["critical"], dash="dot", width=0.8)
    )

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=title,
        height=600,
        showlegend=False,
    )
    return fig


def _contiguous_ranges(idx: pd.DatetimeIndex) -> list[tuple]:
    """Find contiguous date ranges for shading."""
    if len(idx) == 0:
        return []
    ranges = []
    start = idx[0]
    prev = idx[0]
    for d in idx[1:]:
        if (d - prev).days > 45:  # gap > 45 days = new range
            ranges.append((start, prev))
            start = d
        prev = d
    ranges.append((start, prev))
    return ranges
