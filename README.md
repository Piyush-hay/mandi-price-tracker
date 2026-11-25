\# District Mandi Price \& Volatility Tracker (Madhya Pradesh)



An automated agricultural data-engineering pipeline and interactive web dashboard tracking daily wholesale commodity prices and intra-day market volatility across APMC mandis in Madhya Pradesh, with a regional focus on Dhar and the Malwa-Nimar agricultural belt.



\## Problem Statement

Smallholder farmers frequently face information asymmetry across neighboring wholesale markets (\*mandis\*), where modal prices for identical crops can vary by hundreds of rupees per quintal on the same day. This tool aggregates official government mandi records to highlight cross-mandi arbitrage gaps and intra-day price swings.



\## Architecture \& Tech Stack

\- \*\*Data Ingestion (`fetch\_mandi\_data.py`):\*\* Connects to India's Open Government Data Platform (`data.gov.in` AGMARKNET API), normalizes dates and commodity prices, and logs sync metadata.

\- \*\*Storage (`mandi\_prices.db`):\*\* Relational SQLite database with deduplication constraints (`UNIQUE` composite keys) and fetch audit logs.

\- \*\*Web Dashboard (`app.py`):\*\* Interactive Streamlit + Chart.js interface displaying regional modal averages, highest-paying mandis, cross-mandi arbitrage spreads, and min–modal–max volatility bands.



\## How to Run Locally

```bash

pip install requests streamlit

python fetch\_mandi\_data.py

python -m streamlit run app.py

