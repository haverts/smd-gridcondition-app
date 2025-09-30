import streamlit as st
import pandas as pd
import pyodbc
import plotly.graph_objects as go

# --- SQL Config ---
server = '192.168.7.8'
database = 'NEW_WESM2'
username = 'sa'
password = 'm0s-$md'

conn_str = f"DRIVER={{SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}"

# --- Load Data ---
def load_data(start_date=None, end_date=None):
    query = """
    SELECT DELIVERY_DATE, delivery_hour, 
           luzon_demand, luzon_pmin,
           visayas_demand, visayas_pmin,
           mindanao_demand, mindanao_pmin,
           lvm_system_demand, lvm_pmin
    FROM dbo.GridUpdate
    """
    if start_date and end_date:
        query += f" WHERE DELIVERY_DATE BETWEEN '{start_date}' AND '{end_date}'"

    with pyodbc.connect(conn_str) as conn:
        df = pd.read_sql(query, conn)

    df["delivery_hour"] = df["delivery_hour"].astype(int)
    mask = df["delivery_hour"] == 24
    df.loc[mask, "delivery_hour"] = 0
    df.loc[mask, "DELIVERY_DATE"] = pd.to_datetime(df.loc[mask, "DELIVERY_DATE"]) + pd.Timedelta(days=1)
    df["timestamp"] = pd.to_datetime(df["DELIVERY_DATE"]) + pd.to_timedelta(df["delivery_hour"], unit="h")

    numeric_cols = [
        "luzon_demand", "luzon_pmin",
        "visayas_demand", "visayas_pmin",
        "mindanao_demand", "mindanao_pmin",
        "lvm_system_demand", "lvm_pmin"
    ]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
    df[["luzon_pmin","visayas_pmin","mindanao_pmin","lvm_pmin"]] = df[["luzon_pmin","visayas_pmin","mindanao_pmin","lvm_pmin"]].ffill()
    df = df.dropna(subset=["luzon_demand","visayas_demand","mindanao_demand","lvm_system_demand"], how="all")
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    return df

# --- Streamlit Config ---
st.set_page_config(page_title="SMD Monitoring", layout="wide")

# --- Meta Tags for Link Preview ---
st.markdown("""
<head>
    <title>SMD Monitoring</title>
    <meta name="description" content="Real-time monitoring of grid demand and PMIN compliance.">
    <meta property="og:title" content="SMD Grid Monitoring">
    <meta property="og:description" content="Real-time monitoring of grid demand and PMIN compliance.">
</head>
""", unsafe_allow_html=True)

# --- Custom CSS ---
st.markdown("""
<style>
.stTitle {
    font-size: 16px;
    font-weight: 500;
    color: #ffffff;
    text-align: center;
    padding: 6px 12px;
    background-color: #001f4d;
    border-radius: 6px;
    margin: 5px 0 10px 0;
}
.card {
    background-color: rgba(255,255,255,0.88);
    padding:10px;
    border-radius:8px;
    text-align:center;
    margin-bottom:8px;
    font-size:13px;
}
.graph-card {
    background-color: rgba(255,255,255,0.88);
    padding:12px;
    border-radius:10px;
    margin-bottom:15px;
}
</style>
""", unsafe_allow_html=True)

# --- Title ---
st.markdown('<div class="stTitle">SMD Monitoring with Minimum Stable Load</div>', unsafe_allow_html=True)

# --- Sidebar Filters ---
with st.sidebar:
    st.header("Date Filter")
    start_date = st.date_input("Start Date")
    end_date = st.date_input("End Date")
    load_button = st.button("Load Data")

if load_button:
    df = load_data(start_date, end_date)
    if df.empty:
        st.warning("⚠️ No data found for the selected date range.")
    else:
        regions = {
            "Luzon":["luzon_demand","luzon_pmin"],
            "Visayas":["visayas_demand","visayas_pmin"],
            "Mindanao":["mindanao_demand","mindanao_pmin"],
            "System":["lvm_system_demand","lvm_pmin"]
        }

        # --- Tabs for Regions ---
        tabs = st.tabs(list(regions.keys()))
        for i, region in enumerate(regions.keys()):
            with tabs[i]:
                y_cols = regions[region]
                df["satisfies_pmin"] = df[y_cols[0]] >= df[y_cols[1]]
                compliance_rate = df["satisfies_pmin"].mean() * 100
                intervals_below = (~df["satisfies_pmin"]).sum()

                # --- Metrics Cards ---
                metric_cols = st.columns(5)
                metric_cols[0].markdown(f'<div class="card"><b>🔺 Peak Demand</b><br>{df[y_cols[0]].max():,.0f} MW</div>', unsafe_allow_html=True)
                metric_cols[1].markdown(f'<div class="card"><b>⚖️ Avg Demand</b><br>{df[y_cols[0]].mean():,.0f} MW</div>', unsafe_allow_html=True)
                metric_cols[2].markdown(f'<div class="card"><b>🔻 Min Demand</b><br>{df[y_cols[0]].min():,.0f} MW</div>', unsafe_allow_html=True)
                metric_cols[3].markdown(f'<div class="card"><b>✅ Compliance Rate</b><br>{compliance_rate:.1f}%</div>', unsafe_allow_html=True)
                metric_cols[4].markdown(f'<div class="card"><b>⚠️ Intervals Below PMIN</b><br>{intervals_below}</div>', unsafe_allow_html=True)

                # --- Graph (Interactive Plotly with Download Toolbar) ---
                with st.container():
                    fig = go.Figure()

                    # Demand & PMIN lines
                    fig.add_trace(go.Scatter(
                        x=df["timestamp"],
                        y=df[y_cols[0]],
                        mode='lines+markers',
                        name='Demand',
                        line=dict(color="#1f77b4", width=2),
                        marker=dict(size=6)
                    ))
                    fig.add_trace(go.Scatter(
                        x=df["timestamp"],
                        y=df[y_cols[1]],
                        mode='lines+markers',
                        name='PMIN',
                        line=dict(color="#ff7f0e", width=2),
                        marker=dict(size=6)
                    ))

                    # Violations
                    viol_df = df[~df["satisfies_pmin"]]
                    fig.add_trace(go.Scatter(
                        x=viol_df["timestamp"],
                        y=viol_df[y_cols[0]],
                        mode='markers',
                        name='Demand < PMIN',
                        marker=dict(color='red', symbol='x', size=12)
                    ))

                    # Layout
                    fig.update_layout(
                        yaxis=dict(
                            title="MW", 
                            range=[0, df[y_cols[0]].max()*1.1],
                            showline=True,
                            linecolor="#001f4d",
                            linewidth=2,
                            mirror=True
                        ),
                        xaxis=dict(
                            title="Delivery Hour / Delivery Date",
                            showline=True,
                            linecolor="#001f4d",
                            linewidth=2,
                            mirror=True
                        ),
                        legend=dict(yanchor="top", y=1, xanchor="left", x=1),
                        margin=dict(l=40, r=20, t=40, b=40),
                        template="plotly_white",
                        plot_bgcolor='white',
                        paper_bgcolor='white',
                        autosize=True,
                    )

                    # Show chart with toolbar download option
                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                        config={
                            "responsive": True,
                            "toImageButtonOptions": {
                                "format": "png",
                                "filename": f"{region}_graph",
                                "scale": 2
                            }
                        }
                    )

                # --- Violations Table ---
                with st.expander("⚠️ Intervals Below PMIN"):
                    st.dataframe(df.loc[~df["satisfies_pmin"], ["timestamp"] + y_cols], use_container_width=True)
