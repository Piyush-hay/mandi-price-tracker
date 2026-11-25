import html
import json
import os
import sqlite3
import statistics
import subprocess
import sys
import streamlit as st
import streamlit.components.v1 as components

DB_FILE = "mandi_prices.db"
MALWA_NIMAR_DISTRICTS = ["Dhar", "Indore", "Ujjain", "Ratlam", "Dewas", "Khargone"]
PRIORITY_CROPS = [
    "Soyabean",
    "Soybean",
    "Wheat",
    "Maize",
    "Onion",
    "Garlic",
    "Bengal Gram(Gram)(Whole)",
    "Black Gram(Urd Beans)(Whole)",
]

st.set_page_config(
    page_title="District Mandi Price & Volatility Tracker",
    page_icon="🌾",
    layout="wide",
)


@st.cache_data(ttl=120)
def load_data():
    if not os.path.exists(DB_FILE):
        return [], []
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT arrival_date, state, district, market, commodity,
               variety, grade, min_price, max_price, modal_price
        FROM mandi_prices
        WHERE modal_price IS NOT NULL AND modal_price > 0
    """)
    rows = []
    for r in cur.fetchall():
        modal_p = float(r["modal_price"])
        min_p = float(r["min_price"]) if r["min_price"] is not None else modal_p
        max_p = float(r["max_price"]) if r["max_price"] is not None else modal_p
        spread_rs = max(0.0, max_p - min_p)
        vol_pct = (spread_rs / modal_p * 100.0) if modal_p > 0 else 0.0
        rows.append({
            "arrival_date": r["arrival_date"],
            "state": r["state"],
            "district": r["district"],
            "market": r["market"],
            "commodity": r["commodity"],
            "variety": r["variety"] or "Other",
            "grade": r["grade"] or "FAQ",
            "min_price": min_p,
            "max_price": max_p,
            "modal_price": modal_p,
            "spread_rs": spread_rs,
            "intraday_vol_pct": vol_pct,
        })

    try:
        cur.execute("SELECT * FROM fetch_logs ORDER BY id DESC LIMIT 5")
        logs = [dict(x) for x in cur.fetchall()]
    except Exception:
        logs = []
    conn.close()
    return rows, logs


def order_commodities(commodities):
    unique_items = sorted(set(commodities))
    prioritized = [c for c in PRIORITY_CROPS if c in unique_items]
    remaining = [c for c in unique_items if c not in prioritized]
    return prioritized + remaining


st.title("🌾 District Mandi Price & Volatility Tracker")
st.caption(
    "Live AGMARKNET Wholesale Price Intelligence & Market Volatility Dashboard — Madhya Pradesh"
)

with st.sidebar:
    st.header("Data & Region Controls")
    if st.button("🔄 Fetch Latest Live Mandi Data", use_container_width=True):
        if os.path.exists("fetch_mandi_data.py"):
            with st.spinner("Pulling latest records from data.gov.in..."):
                res = subprocess.run(
                    [sys.executable, "fetch_mandi_data.py"],
                    capture_output=True,
                    text=True,
                )
            st.cache_data.clear()
            if res.returncode == 0:
                st.success("Database updated with latest mandi rates!")
            else:
                st.error("Fetch encountered an issue. Showing stored database records.")
        else:
            st.info("Showing stored database snapshot.")

rows, logs = load_data()

if not rows:
    st.warning("No records found in mandi_prices.db. Run `python fetch_mandi_data.py` first.")
    st.stop()

malwa_rows = [r for r in rows if r["district"] in MALWA_NIMAR_DISTRICTS]

with st.sidebar:
    region_options = ["All Madhya Pradesh Districts"]
    if malwa_rows:
        region_options.insert(
            0, "Malwa-Nimar Belt (Dhar, Indore, Ujjain, Ratlam, Dewas, Khargone)"
        )
    selected_region = st.selectbox("Geographic Scope", region_options)

    scoped_rows = malwa_rows if selected_region.startswith("Malwa-Nimar") else rows
    commodities = order_commodities([r["commodity"] for r in scoped_rows if r["commodity"]])
    selected_crop = st.selectbox("Select Commodity", commodities)

    crop_rows = [r for r in scoped_rows if r["commodity"] == selected_crop]
    districts_in_crop = ["All Districts"] + sorted({r["district"] for r in crop_rows if r["district"]})
    selected_district = st.selectbox("Filter by District", districts_in_crop)

    if selected_district != "All Districts":
        crop_rows = [r for r in crop_rows if r["district"] == selected_district]

    if logs:
        st.divider()
        st.markdown("**Pipeline Sync Status**")
        st.write(f"Last synced: `{logs[0]['fetched_at']}`")
        st.write(f"Total rows in SQLite: `{len(rows):,}`")

latest_date = max(r["arrival_date"] for r in crop_rows)
latest_day_rows = [r for r in crop_rows if r["arrival_date"] == latest_date]

avg_modal = statistics.mean(r["modal_price"] for r in latest_day_rows)
best_row = max(latest_day_rows, key=lambda r: r["modal_price"])
low_row = min(latest_day_rows, key=lambda r: r["modal_price"])
cross_mandi_spread = best_row["modal_price"] - low_row["modal_price"]
avg_intraday_vol = statistics.mean(r["intraday_vol_pct"] for r in latest_day_rows)

c1, c2, c3, c4 = st.columns(4)
c1.metric(
    label=f"Avg Modal Rate ({latest_date})",
    value=f"₹{avg_modal:,.0f} / qtl",
)
c2.metric(
    label="Highest Paying Mandi",
    value=f"₹{best_row['modal_price']:,.0f} / qtl",
    delta=f"{best_row['market']} ({best_row['district']})",
)
c3.metric(
    label="Cross-Mandi Arbitrage Gap",
    value=f"₹{cross_mandi_spread:,.0f} / qtl",
    delta=f"Lowest: {low_row['market']}",
    delta_color="off",
)
c4.metric(
    label="Avg Intra-Day Price Volatility",
    value=f"{avg_intraday_vol:.1f}%",
    delta="Max–Min Swing %",
    delta_color="inverse",
)

st.divider()

grouped = {}
for r in latest_day_rows:
    key = (r["district"], r["market"])
    if key not in grouped:
        grouped[key] = {"mins": [], "modals": [], "maxs": []}
    grouped[key]["mins"].append(r["min_price"])
    grouped[key]["modals"].append(r["modal_price"])
    grouped[key]["maxs"].append(r["max_price"])

bar_items = []
for (dist, mkt), vals in grouped.items():
    bar_items.append({
        "label": f"{mkt} ({dist})",
        "min": round(min(vals["mins"]), 1),
        "modal": round(statistics.mean(vals["modals"]), 1),
        "max": round(max(vals["maxs"]), 1),
    })
bar_items.sort(key=lambda x: x["modal"], reverse=True)
bar_items = bar_items[:15]

labels_json = json.dumps([x["label"] for x in bar_items])
mins_json = json.dumps([x["min"] for x in bar_items])
modals_json = json.dumps([x["modal"] for x in bar_items])
maxs_json = json.dumps([x["max"] for x in bar_items])

col_left, col_right = st.columns([1.2, 1])

with col_left:
    st.subheader(f"Mandi Price Comparison — {selected_crop} ({latest_date})")
    chart1_html = f"""
    <div style="background:#ffffff;border-radius:10px;padding:12px;border:1px solid #e2e8f0;height:390px;">
      <canvas id="barChart"></canvas>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
      new Chart(document.getElementById('barChart'), {{
        type: 'bar',
        data: {{
          labels: {labels_json},
          datasets: [{{
            label: 'Modal Price (₹/Quintal)',
            data: {modals_json},
            backgroundColor: '#16a34a',
            borderRadius: 6
          }}]
        }},
        options: {{
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ title: {{ display: true, text: 'Modal Price (₹/Quintal)' }} }}
          }}
        }}
      }});
    </script>
    """
    components.html(chart1_html, height=420)

with col_right:
    st.subheader("Min – Modal – Max Volatility Spread")
    chart2_html = f"""
    <div style="background:#ffffff;border-radius:10px;padding:12px;border:1px solid #e2e8f0;height:390px;">
      <canvas id="spreadChart"></canvas>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
      new Chart(document.getElementById('spreadChart'), {{
        type: 'bar',
        data: {{
          labels: {labels_json},
          datasets: [
            {{ label: 'Min ₹/qtl', data: {mins_json}, backgroundColor: '#ef4444', borderRadius: 4 }},
            {{ label: 'Modal ₹/qtl', data: {modals_json}, backgroundColor: '#16a34a', borderRadius: 4 }},
            {{ label: 'Max ₹/qtl', data: {maxs_json}, backgroundColor: '#2563eb', borderRadius: 4 }}
          ]
        }},
        options: {{
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          scales: {{
            x: {{ title: {{ display: true, text: 'Price Range (₹/Quintal)' }} }}
          }}
        }}
      }});
    </script>
    """
    components.html(chart2_html, height=420)

unique_dates = sorted({r["arrival_date"] for r in crop_rows})
if len(unique_dates) > 1:
    st.subheader(f"Multi-Day Price Trajectory — {selected_crop}")
    date_avgs = []
    for d in unique_dates:
        vals = [r["modal_price"] for r in crop_rows if r["arrival_date"] == d]
        date_avgs.append(round(statistics.mean(vals), 1))
    trend_html = f"""
    <div style="background:#ffffff;border-radius:10px;padding:12px;border:1px solid #e2e8f0;height:310px;">
      <canvas id="trendChart"></canvas>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
      new Chart(document.getElementById('trendChart'), {{
        type: 'line',
        data: {{
          labels: {json.dumps(unique_dates)},
          datasets: [{{
            label: 'Avg Modal Price (₹/Quintal)',
            data: {json.dumps(date_avgs)},
            borderColor: '#15803d',
            backgroundColor: 'rgba(22, 163, 74, 0.15)',
            fill: true,
            tension: 0.25
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false
        }}
      }});
    </script>
    """
    components.html(trend_html, height=340)
else:
    st.info(
        "📅 Multi-day trend lines automatically unlock as you run the daily fetcher across multiple dates (each run appends new daily prices to `mandi_prices.db`)."
    )

st.subheader("Verified Mandi Records Table")
sorted_table = sorted(
    crop_rows,
    key=lambda r: (r["arrival_date"], r["modal_price"]),
    reverse=True,
)

rows_html = []
for r in sorted_table:
    rows_html.append(
        f"<tr>"
        f"<td>{html.escape(str(r['arrival_date']))}</td>"
        f"<td>{html.escape(str(r['district']))}</td>"
        f"<td>{html.escape(str(r['market']))}</td>"
        f"<td>{html.escape(str(r['commodity']))}</td>"
        f"<td>{html.escape(str(r['variety']))}</td>"
        f"<td style='text-align:right;'>₹{r['min_price']:,.0f}</td>"
        f"<td style='text-align:right;font-weight:600;color:#15803d;'>₹{r['modal_price']:,.0f}</td>"
        f"<td style='text-align:right;'>₹{r['max_price']:,.0f}</td>"
        f"<td style='text-align:right;'>{r['intraday_vol_pct']:.2f}%</td>"
        f"</tr>"
    )

table_html = f"""
<div style="max-height:420px;overflow-y:auto;border:1px solid #cbd5e1;border-radius:8px;">
  <table style="width:100%;border-collapse:collapse;font-family:sans-serif;font-size:14px;">
    <thead style="position:sticky;top:0;background:#1e293b;color:#ffffff;">
      <tr>
        <th style="padding:10px;text-align:left;">Date</th>
        <th style="padding:10px;text-align:left;">District</th>
        <th style="padding:10px;text-align:left;">Mandi (APMC)</th>
        <th style="padding:10px;text-align:left;">Commodity</th>
        <th style="padding:10px;text-align:left;">Variety</th>
        <th style="padding:10px;text-align:right;">Min (₹/qtl)</th>
        <th style="padding:10px;text-align:right;">Modal (₹/qtl)</th>
        <th style="padding:10px;text-align:right;">Max (₹/qtl)</th>
        <th style="padding:10px;text-align:right;">Volatility (%)</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</div>
"""
st.markdown(table_html, unsafe_allow_html=True)