"""US Flight Delays - interactive dashboard on the gold layer of the data lake.

Run locally:   streamlit run app/streamlit_app.py
Data source:   Azure Blob Storage (if AZURE_STORAGE_CONNECTION_STRING is set as env var or
               Streamlit secret) or the local folder data/lake/gold.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

NAVY, ORANGE, GREY, GREEN = "#1F3864", "#E07A1F", "#9AA5B1", "#2E7D5B"
LOCAL_GOLD = Path(__file__).resolve().parents[1] / "data" / "lake" / "gold"
REPO_URL = "https://github.com/alvarolorenzoa/us-flight-delays-platform"
MARTS = ["mart_kpis_monthly", "mart_carrier_monthly", "mart_airport_daily", "mart_route_monthly",
         "mart_delay_causes_monthly", "mart_weather_impact", "mart_hourly_profile"]

st.set_page_config(page_title="US Flight Delays", page_icon="✈️", layout="wide")


# ----------------------------------------------------------------------------- data
def _secret(name: str) -> str:
    try:
        return st.secrets.get(name, "") or os.getenv(name, "")
    except Exception:  # no secrets file locally
        return os.getenv(name, "")


@st.cache_data(ttl=3600, show_spinner="Loading data from the lake...")
def load() -> tuple[dict[str, pd.DataFrame], str]:
    conn = _secret("AZURE_STORAGE_CONNECTION_STRING")
    if conn:
        from azure.storage.blob import ContainerClient
        c = ContainerClient.from_connection_string(conn, _secret("AZURE_CONTAINER") or "flights-lake")
        data = {m: pd.read_parquet(io.BytesIO(c.download_blob(f"gold/{m}.parquet").readall())) for m in MARTS}
        return data, "Azure Data Lake"
    return {m: pd.read_parquet(LOCAL_GOLD / f"{m}.parquet") for m in MARTS}, "local lake"


try:
    D, source = load()
except Exception as exc:  # friendly message instead of a stack trace
    st.error(f"Could not load the gold layer ({exc}). Run the pipeline first: `python -m ingestion.pipeline`.")
    st.stop()

kpis = D["mart_kpis_monthly"].sort_values("year_month")
months = kpis["year_month"].tolist()

# ----------------------------------------------------------------------------- header
st.markdown(
    f"""
    <div style="background:{NAVY};padding:18px 24px;border-radius:10px;margin-bottom:12px">
      <h2 style="color:white;margin:0">✈️ US Flight Delays &amp; Weather Impact</h2>
      <p style="color:#D6DEEA;margin:4px 0 0">
        {kpis['flights'].sum():,.0f} domestic flights · {months[0]} → {months[-1]} ·
        Sources: US DOT / BTS + Open-Meteo · Served from the {source}</p>
    </div>""",
    unsafe_allow_html=True,
)

sel = st.select_slider("Month", options=months, value=months[-1])
cur = kpis.set_index("year_month").loc[sel]
prev = kpis.set_index("year_month").shift(1).loc[sel]


def delta(col, fmt="{:+.1f}", unit=""):
    return None if pd.isna(prev[col]) else fmt.format(cur[col] - prev[col]) + unit


c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Flights", f"{cur['flights']:,.0f}", delta("flights", "{:+,.0f}"))
c2.metric("On-time arrivals", f"{cur['on_time_pct']:.1f}%", delta("on_time_pct", unit=" pp"))
c3.metric("Avg arrival delay", f"{cur['avg_arr_delay_min']:.1f} min", delta("avg_arr_delay_min", unit=" min"),
          delta_color="inverse")
c4.metric("Cancelled", f"{cur['cancellation_pct']:.2f}%", delta("cancellation_pct", "{:+.2f}", " pp"),
          delta_color="inverse")
c5.metric("Delay hours", f"{cur['total_delay_hours']:,.0f}", delta("total_delay_hours", "{:+,.0f}"),
          delta_color="inverse")


def style(fig, h=360):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=50, b=10), plot_bgcolor="white",
                      legend=dict(orientation="h", yanchor="top", y=-0.12, x=0, title_text=""),
                      font=dict(size=12))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#EEF1F5")
    return fig


t_over, t_air, t_apt, t_wx, t_route = st.tabs(["📈 Overview", "🛫 Airlines", "🗺️ Airports", "🌧️ Weather", "🔀 Routes"])

# ----------------------------------------------------------------------------- overview
with t_over:
    a, b = st.columns(2)
    fig = go.Figure()
    fig.add_bar(x=kpis["year_month"], y=kpis["flights"], name="Flights", marker_color="#D6DEEA")
    fig.add_scatter(x=kpis["year_month"], y=kpis["on_time_pct"], name="On-time %", mode="lines+markers",
                    line=dict(color=NAVY, width=3), yaxis="y2")
    lo = max(0, kpis["on_time_pct"].min() - 10)
    fig.update_layout(title="Monthly punctuality", yaxis=dict(title="Flights", showgrid=False),
                      yaxis2=dict(overlaying="y", side="right", title="On-time %", range=[lo, 100],
                                  gridcolor="#EEF1F5"))
    a.plotly_chart(style(fig), use_container_width=True)

    causes = D["mart_delay_causes_monthly"]
    fig = px.bar(causes, x="year_month", y="share_pct", color="cause", title="What causes the delay minutes?",
                 labels={"share_pct": "% of delay minutes", "year_month": ""},
                 color_discrete_sequence=[NAVY, ORANGE, "#5B8DB8", GREY, GREEN])
    b.plotly_chart(style(fig), use_container_width=True)

    hp = D["mart_hourly_profile"]
    fig = px.line(hp, x="scheduled_dep_hour", y="dep_delay_pct", markers=True,
                  title="Delays snowball during the day (departures delayed 15+ min, by scheduled hour)",
                  labels={"scheduled_dep_hour": "Scheduled departure hour", "dep_delay_pct": "% delayed"})
    fig.update_traces(line=dict(color=ORANGE, width=3))
    st.plotly_chart(style(fig, 300), use_container_width=True)

# ----------------------------------------------------------------------------- airlines
with t_air:
    cm = D["mart_carrier_monthly"]
    m = cm[cm["year_month"] == sel].sort_values("on_time_pct")
    fig = px.bar(m, x="on_time_pct", y="carrier_name", orientation="h", color="carrier_type",
                 text=m["on_time_pct"].map("{:.1f}%".format), title=f"On-time arrival rate by airline · {sel}",
                 labels={"on_time_pct": "On-time %", "carrier_name": "", "carrier_type": "Type"},
                 color_discrete_sequence=[NAVY, ORANGE, "#5B8DB8", GREY, GREEN])
    fig.update_xaxes(range=[max(0, m["on_time_pct"].min() - 10), 100])
    fig.update_yaxes(categoryorder="total ascending")  # rank by punctuality, not by colour group
    st.plotly_chart(style(fig, 460), use_container_width=True)
    st.dataframe(m.sort_values("on_time_rank")[["on_time_rank", "carrier_name", "carrier_type", "flights",
                 "on_time_pct", "avg_arr_delay_min", "cancellation_pct"]],
                 hide_index=True, use_container_width=True)

# ----------------------------------------------------------------------------- airports
with t_apt:
    ad = D["mart_airport_daily"]
    ad = ad[pd.to_datetime(ad["flight_date"]).dt.strftime("%Y-%m") == sel]
    agg = (ad.groupby(["airport_code", "airport_name", "city_name", "latitude", "longitude", "is_hub"], dropna=False)
             .apply(lambda g: pd.Series({
                 "departures": g["departures"].sum(),
                 "dep_delay_pct": (g["dep_delay_pct"] * g["departures"]).sum() / g["departures"].sum(),
                 "cancellation_pct": (g["cancellation_pct"] * g["departures"]).sum() / g["departures"].sum()}),
                    include_groups=False)
             .reset_index())
    hubs = agg[agg["is_hub"]]
    fig = px.scatter_geo(hubs, lat="latitude", lon="longitude", size="departures", color="dep_delay_pct",
                         hover_name="airport_name", scope="usa", color_continuous_scale=["#2E7D5B", "#F2C14E", "#C0504D"],
                         title=f"Hub airports · size = departures, colour = % delayed departures · {sel}",
                         labels={"dep_delay_pct": "% delayed"})
    st.plotly_chart(style(fig, 480), use_container_width=True)
    a, b = st.columns(2)
    a.markdown("**Most delayed hubs**")
    a.dataframe(hubs.nlargest(10, "dep_delay_pct")[["airport_code", "city_name", "departures", "dep_delay_pct"]]
                .round(1), hide_index=True, use_container_width=True)
    b.markdown("**Most punctual hubs**")
    b.dataframe(hubs.nsmallest(10, "dep_delay_pct")[["airport_code", "city_name", "departures", "dep_delay_pct"]]
                .round(1), hide_index=True, use_container_width=True)

# ----------------------------------------------------------------------------- weather
with t_wx:
    wx = D["mart_weather_impact"]
    order = ["Dry & calm", "Light rain", "Heavy rain", "Strong wind", "Snow"]
    allh = wx[wx["airport_code"] == "ALL HUBS"].set_index("weather_condition").reindex(order).dropna(how="all")
    allh = allh.reset_index()
    a, b = st.columns([3, 2])
    fig = px.bar(allh, x="weather_condition", y="dep_delay_pct", text=allh["dep_delay_pct"].map("{:.1f}%".format),
                 title="% of departures delayed 15+ min by weather at the origin hub (all hubs, full period)",
                 labels={"weather_condition": "", "dep_delay_pct": "% delayed"})
    fig.update_traces(marker_color=[NAVY if c == "Dry & calm" else ORANGE for c in allh["weather_condition"]])
    a.plotly_chart(style(fig), use_container_width=True)
    b.markdown("#### Reading the chart")
    base = allh.loc[allh["weather_condition"] == "Dry & calm", "dep_delay_pct"]
    worst = allh.sort_values("dep_delay_pct").iloc[-1]
    if len(base):
        b.markdown(f"- In dry & calm conditions **{base.iloc[0]:.1f}%** of departures leave 15+ minutes late.\n"
                   f"- With **{worst['weather_condition'].lower()}** it rises to **{worst['dep_delay_pct']:.1f}%** "
                   f"(**{worst['delay_uplift_pp']:+.1f} pp**), and cancellations reach "
                   f"**{worst['cancellation_pct']:.1f}%**.\n"
                   "- Weather is matched hour by hour: the conditions at the origin airport at the scheduled "
                   "departure hour.")
    per = wx[(wx["airport_code"] != "ALL HUBS") & (wx["weather_condition"] != "Dry & calm")]
    heat = per.pivot_table(index="airport_code", columns="weather_condition", values="delay_uplift_pp")
    heat = heat.reindex(columns=[c for c in order if c in heat.columns]).sort_values(heat.columns[0], ascending=False)
    fig = px.imshow(heat, color_continuous_scale="Oranges", aspect="auto", text_auto=".0f",
                    title="Extra delayed departures vs. dry & calm, by hub (percentage points)",
                    labels={"color": "pp"})
    st.plotly_chart(style(fig, 620), use_container_width=True)

# ----------------------------------------------------------------------------- routes
with t_route:
    rm = D["mart_route_monthly"]
    rm = rm[rm["year_month"] == sel]
    a, b = st.columns(2)
    busiest = rm.nlargest(15, "flights").sort_values("flights")
    fig = px.bar(busiest, x="flights", y="route", orientation="h", color="on_time_pct",
                 color_continuous_scale=["#C0504D", "#F2C14E", "#2E7D5B"], title=f"Busiest routes · {sel}",
                 labels={"route": "", "on_time_pct": "On-time %"})
    a.plotly_chart(style(fig, 520), use_container_width=True)
    worst = rm[rm["flights"] >= rm["flights"].quantile(0.5)].nsmallest(15, "on_time_pct").sort_values("on_time_pct",
                                                                                                      ascending=False)
    fig = px.bar(worst, x="on_time_pct", y="route", orientation="h", title="Least punctual busy routes",
                 text=worst["on_time_pct"].map("{:.0f}%".format), labels={"route": "", "on_time_pct": "On-time %"})
    fig.update_traces(marker_color=ORANGE)
    b.plotly_chart(style(fig, 520), use_container_width=True)

st.divider()
st.caption(f"Pipeline: BTS + Open-Meteo → Python ingestion → Azure Data Lake (bronze) → dbt + DuckDB "
           f"(silver/gold, 35 data tests) → this app. Refreshed monthly by GitHub Actions. "
           f"On-time = arrival < 15 min late (US DOT definition). [Source code]({REPO_URL})")
