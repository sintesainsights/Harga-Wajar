import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# Konfigurasi Halaman Streamlit
st.set_page_config(
    page_title="Indonesia Stock Valuation Dashboard (DCF, Relative, DDM)",
    page_icon="📈",
    layout="wide",
)

st.title("🇮🇩 Dashboard Valuasi Saham BEI (IDR)")
st.markdown(
    "Dashboard Profesional: DCF (CAPM), Relative Valuation (Forward EPS/BVPS &"
    " Rata-rata Multiples), & DDM dengan Margin of Safety."
)


@st.cache_data(ttl=3600)
def get_stock_data(ticker_symbol):
  try:
    stock = yf.Ticker(ticker_symbol)
    info = stock.info

    currency = info.get("currency", "IDR")
    balance_sheet = stock.balance_sheet
    cashflow = stock.cashflow

    current_price = info.get(
        "currentPrice",
        info.get("regularMarketPrice", info.get("previousClose", 0)),
    )
    shares_outstanding = info.get("sharesOutstanding", 0)
    market_cap = info.get("marketCap", current_price * shares_outstanding)

    total_debt = 0
    total_cash = 0
    if not balance_sheet.empty:
      for col in balance_sheet.columns:
        for row in balance_sheet.index:
          row_lower = str(row).lower()
          if (
              "cash" in row_lower
              and "cash and cash equivalents" in row_lower
              and total_cash == 0
          ):
            val = balance_sheet.loc[row, col]
            if pd.notna(val):
              total_cash = val
          elif "cash" in row_lower and total_cash == 0:
            val = balance_sheet.loc[row, col]
            if pd.notna(val):
              total_cash = val

          if (
              "total debt" in row_lower
              or "short long term debt" in row_lower
              or "long term debt" in row_lower
          ) and total_debt == 0:
            val = balance_sheet.loc[row, col]
            if pd.notna(val):
              total_debt = val

    fcf_list = []
    if not cashflow.empty:
      for col in cashflow.columns:
        ocf, capex = 0, 0
        for row in cashflow.index:
          row_lower = str(row).lower()
          if (
              "operating cash flow" in row_lower
              or "total cash from operating activities" in row_lower
          ):
            val = cashflow.loc[row, col]
            if pd.notna(val):
              ocf = val
          if "capital expenditures" in row_lower or "capex" in row_lower:
            val = cashflow.loc[row, col]
            if pd.notna(val):
              capex = abs(val)
        if ocf != 0:
          fcf_list.append(ocf - capex)

    dividends = stock.dividends

    return {
        "info": info,
        "currency": currency,
        "current_price": current_price,
        "shares_outstanding": shares_outstanding,
        "market_cap": market_cap,
        "total_debt": total_debt,
        "total_cash": total_cash,
        "fcf_list": fcf_list,
        "dividends": dividends,
    }, None
  except Exception as e:
    return None, str(e)


# --- SIDEBAR: PENCARIAN EMITEN & ASUMSI ---
st.sidebar.header("1. Pencarian Ticker Saham BEI")
user_ticker = (
    st.sidebar.text_input(
        "Ketik Kode Saham (Contoh: BBCA, ASII, KIJA, ADRO)", "KIJA"
    )
    .upper()
    .strip()
)
if not user_ticker.endswith(".JK") and user_ticker != "":
  ticker_full = user_ticker + ".JK"
else:
  ticker_full = user_ticker

data, err = get_stock_data(ticker_full)

# Ambil Kurs USDIDR terkini
usd_idr = 16000
try:
  fx = yf.Ticker("USDIDR=X").info
  usd_idr = fx.get("regularMarketPrice", fx.get("previousClose", 16000))
except:
  pass

if err or not data or data["current_price"] == 0:
  st.sidebar.error(
      f"Gagal memuat data untuk {ticker_full}. Pastikan kode saham valid."
  )
  st.stop()

info = data["info"]
currency = info.get("currency", "IDR")

# Deteksi mata uang USD untuk emiten global/komoditas
forced_usd_tickers = ["AADI.JK", "ADRO.JK", "PTBA.JK", "MEDC.JK", "INCO.JK"]
is_financials_in_usd = (
    (currency == "USD")
    or (ticker_full in forced_usd_tickers)
    or (
        data["current_price"] > 500
        and info.get("netIncomeToCommon", 0) > 0
        and info.get("netIncomeToCommon", 0) < 50_000_000
    )
)
fx_multiplier = usd_idr if is_financials_in_usd else 1.0

conv_msg = (
    f"USD -> Dikonversi ke IDR (Kurs ~{usd_idr:,.0f})"
    if is_financials_in_usd
    else "IDR (Native)"
)
st.sidebar.success(
    f"Emiten Aktif: {info.get('longName', ticker_full)} (Lapkeu in {conv_msg})"
)

st.sidebar.markdown("---")
st.sidebar.header("2. Asumsi Parameter Valuasi")

# A. Komponen WACC (CAPM)
st.sidebar.subheader("A. Komponen WACC (CAPM)")
risk_free_rate = (
    st.sidebar.number_input(
        "Risk-Free Rate Rf (%)", min_value=0.0, max_value=20.0, value=6.5, step=0.1
    )
    / 100
)
tax_rate = (
    st.sidebar.number_input(
        "Tax Perusahaan (%)", min_value=0.0, max_value=50.0, value=22.0, step=0.5
    )
    / 100
)
market_risk_premium = (
    st.sidebar.number_input(
        "Market Risk Premium (%)", min_value=0.0, max_value=20.0, value=6.0, step=0.1
    )
    / 100
)
beta = st.sidebar.number_input(
    "Beta Saham", min_value=0.0, max_value=3.0, value=1.0, step=0.05
)
cost_of_debt = (
    st.sidebar.number_input(
        "Cost of Debt Sebelum Pajak (%)",
        min_value=0.0,
        max_value=30.0,
        value=8.0,
        step=0.5,
    )
    / 100
)
debt_weight = (
    st.sidebar.slider("Bobot Utang (Debt Weight) %", 0, 100, 20, 5) / 100
)
equity_weight = 1.0 - debt_weight

cost_of_equity = risk_free_rate + (beta * market_risk_premium)
effective_cost_of_debt = cost_of_debt * (1 - tax_rate)
calculated_wacc = (equity_weight * cost_of_equity) + (
    debt_weight * effective_cost_of_debt
)
st.sidebar.info(f"⚡ **WACC Otomatis:** **{calculated_wacc*100:.2f}%**")

# B. Proyeksi DCF & Time Period
st.sidebar.subheader("B. Proyeksi DCF & Cash Flow")
projection_years = st.sidebar.selectbox(
    "Time Periode Cash Flow", options=[5, 10], index=0
)
fcf_growth_rate = (
    st.sidebar.slider(
        "Estimasi Pertumbuhan FCF Tahunan (%)", -10.0, 30.0, 8.0, 0.5
    )
    / 100
)
perpetual_growth = (
    st.sidebar.slider("Perpetual Growth Rate (%)", 0.0, 5.0, 2.5, 0.25) / 100
)

# C. Relative Valuation Multiples & Growth
st.sidebar.subheader("C. Relative Valuation (Rata-rata Multiples & Growth)")
avg_pe = st.sidebar.number_input(
    "Rata-rata PER (Historis/Peer)", min_value=1.0, max_value=100.0, value=12.0, step=0.5
)
avg_pbv = st.sidebar.number_input(
    "Rata-rata PBV (Historis/Peer)", min_value=0.1, max_value=10.0, value=1.0, step=0.1
)
avg_ev_ebitda = st.sidebar.number_input(
    "Rata-rata EV/EBITDA (Historis/Peer)", min_value=1.0, max_value=50.0, value=10.0, step=0.5
)
avg_ev_sales = st.sidebar.number_input(
    "Rata-rata EV/Sales (Historis/Peer)", min_value=0.1, max_value=20.0, value=2.0, step=0.2
)
earnings_growth_rate = (
    st.sidebar.slider(
        "Estimasi Pertumbuhan EPS / Laba (Growth Rate) %", -10.0, 30.0, 8.0, 0.5
    )
    / 100
)

# D. Margin of Safety & Entry Price
st.sidebar.subheader("D. Entry Price & Margin of Safety")
mos_percentage = (
    st.sidebar.selectbox(
        "Pilihan Margin of Safety (MoS)",
        options=[10, 15, 20, 25, 30, 35, 40, 45, 50],
        index=3,
    )
    / 100
)

# --- PROSES UTAMA DCF ---
current_price = data["current_price"]
shares = data["shares_outstanding"]
total_debt = data["total_debt"] * fx_multiplier
total_cash = data["total_cash"] * fx_multiplier
fcf_list = data["fcf_list"]

base_fcf = (
    fcf_list[0] * fx_multiplier
    if len(fcf_list) > 0
    else info.get("netIncomeToCommon", 1000000000) * fx_multiplier * 0.5
)
if base_fcf <= 0:
  base_fcf = 1_000_000_000  # Fallback jika FCF negatif/nol agar DCF tetap rasional

projected_fcfs = []
pv_fcfs = []
current_fcf = base_fcf
for yr in range(1, projection_years + 1):
  current_fcf *= 1 + fcf_growth_rate
  projected_fcfs.append(current_fcf)
  pv = current_fcf / ((1 + calculated_wacc) ** yr)
  pv_fcfs.append(pv)

sum_pv_fcf = sum(pv_fcfs)
terminal_value = (projected_fcfs[-1] * (1 + perpetual_growth)) / (
    calculated_wacc - perpetual_growth
)
pv_terminal_value = terminal_value / ((1 + calculated_wacc) ** projection_years)
enterprise_value = sum_pv_fcf + pv_terminal_value

# Pengaman Equity Value: Jika utang melebihi EV + Kas, gunakan minimal nilai aset bersih positif atau book value
equity_value = enterprise_value + total_cash - total_debt
if equity_value < 0:
  # Fallback menggunakan Market Cap / Book Value proporsional jika struktur utang membuat EV negatif
  equity_value = max(
      info.get("bookValue", current_price) * shares * 0.5,
      enterprise_value * 0.2,
  )

intrinsic_value_dcf = equity_value / shares if shares > 0 else 0
entry_buy_price = intrinsic_value_dcf * (1 - mos_percentage)

# --- RELATIVE VALUATION ---
eps_ttm = info.get("trailingEps", info.get("forwardEps", 0)) * fx_multiplier
bvps = info.get("bookValue", 0) * fx_multiplier
ebitda = info.get("ebitda", 0) * fx_multiplier
total_revenue = info.get("totalRevenue", 0) * fx_multiplier

eps_forward = eps_ttm * (1 + earnings_growth_rate)
val_per_price = avg_pe * eps_forward if eps_forward > 0 else 0

bvps_forward = bvps * (1 + earnings_growth_rate)
val_pbv_price = avg_pbv * bvps_forward if bvps_forward > 0 else 0

net_debt = total_debt - total_cash
ev_ebitda_val = avg_ev_ebitda * ebitda if ebitda > 0 else 0
eq_val_ebitda = max(ev_ebitda_val - net_debt, ebitda * 2)
val_ev_ebitda_price = (
    eq_val_ebitda / shares if (eq_val_ebitda > 0 and shares > 0) else 0
)

ev_sales_val = avg_ev_sales * total_revenue if total_revenue > 0 else 0
eq_val_sales = max(ev_sales_val - net_debt, total_revenue * 0.5)
val_ev_sales_price = (
    eq_val_sales / shares if (eq_val_sales > 0 and shares > 0) else 0
)

relative_prices = [
    p
    for p in [
        val_per_price,
        val_pbv_price,
        val_ev_ebitda_price,
        val_ev_sales_price,
    ]
    if p > 0
]
avg_relative_value = (
    sum(relative_prices) / len(relative_prices) if relative_prices else 0
)

# --- DDM ---
dividends = data["dividends"]
ddm_value = None
has_consistent_dividend = False
if not dividends.empty and len(dividends) >= 4:
  recent_divs = dividends.tail(4).sum() * fx_multiplier
  if recent_divs > 0:
    has_consistent_dividend = True
    d1 = recent_divs * (1 + 0.02)
    if cost_of_equity > 0.02:
      ddm_value = d1 / (cost_of_equity - 0.02)

# --- TAMPILAN UTAMA DASHBOARD ---
st.subheader(
    f"🏢 {info.get('longName', ticker_full)} (IDR) — Ringkasan Utama"
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Harga Pasar Saat Ini", f"Rp {current_price:,.0f}")
c2.metric("Nilai Intrinsik (DCF)", f"Rp {intrinsic_value_dcf:,.0f}")
c3.metric(
    f"Entry Price (MoS {int(mos_percentage*100)}%)", f"Rp {entry_buy_price:,.0f}"
)
c4.metric("Relative Valuation", f"Rp {avg_relative_value:,.0f}")

st.markdown("---")

tab1, tab2, tab3 = st.tabs(
    [
        "📊 Ringkasan & Rekomendasi",
        f"📈 Proyeksi FCF ({projection_years} Tahun)",
        "🏢 Relative & DDM Valuation",
    ]
)

with tab1:
  st.subheader("Kesimpulan & Keputusan Investasi")
  if current_price <= entry_buy_price:
    st.success(
        f"🟢 **MENARIK (Undervalued)**: Harga pasar (Rp {current_price:,.0f})"
        f" berada di bawah Entry Price MoS {int(mos_percentage*100)}% (Rp"
        f" {entry_buy_price:,.0f})."
    )
  elif current_price <= intrinsic_value_dcf:
    st.warning(
        f"🟡 **CUKUP WAJAR**: Harga pasar (Rp {current_price:,.0f}) di bawah"
        f" Nilai Wajar DCF (Rp {intrinsic_value_dcf:,.0f}), tapi belum menyentuh"
        f" Entry Price."
    )
  else:
    st.error(
        f"🔴 **OVERVALUED**: Harga pasar saat ini (Rp {current_price:,.0f})"
        f" sudah melampaui Nilai Wajar DCF."
    )

  col_a, col_b = st.columns(2)
  with col_a:
    st.markdown("### 📋 Rangkuman Jembatan DCF")
    st.table(
        pd.DataFrame({
            "Komponen": [
                "Total PV FCF",
                "PV Terminal Value",
                "Enterprise Value",
                "Kas Total",
                "Total Utang",
                "Equity Value",
            ],
            "Nilai (IDR)": [
                f"Rp {sum_pv_fcf:,.0f}",
                f"Rp {pv_terminal_value:,.0f}",
                f"Rp {enterprise_value:,.0f}",
                f"Rp {total_cash:,.0f}",
                f"Rp {total_debt:,.0f}",
                f"Rp {equity_value:,.0f}",
            ],
        })
    )

  with col_b:
    st.markdown("### 🎯 Perbandingan Harga Wajar")
    ddm_display = f"Rp {ddm_value:,.0f}" if has_consistent_dividend else "-"
    st.table(
        pd.DataFrame({
            "Metode Valuasi": [
                "Harga Pasar Aktual",
                f"Entry Price (MoS {int(mos_percentage*100)}%)",
                "DCF Intrinsic Value",
                "Relative Valuation (Forward & Multiples)",
                "Dividend Discount Model (DDM)",
            ],
            "Harga Wajar": [
                f"Rp {current_price:,.0f}",
                f"Rp {entry_buy_price:,.0f}",
                f"Rp {intrinsic_value_dcf:,.0f}",
                f"Rp {avg_relative_value:,.0f}",
                ddm_display,
            ],
        })
    )

with tab2:
  st.subheader(f"Tabel & Grafik Proyeksi Arus Kas ({projection_years} Tahun)")
  proj_years_list = [f"Tahun {i}" for i in range(1, projection_years + 1)]
  proj_df = pd.DataFrame({
      "Periode": proj_years_list,
      "Proyeksi FCF (IDR)": projected_fcfs,
      "Present Value FCF (IDR)": pv_fcfs,
  })
  st.dataframe(proj_df, use_container_width=True)

  fig = go.Figure()
  fig.add_trace(
      go.Bar(
          x=proj_years_list,
          y=projected_fcfs,
          name="Proyeksi FCF",
          marker_color="indianred",
      )
  )
  fig.add_trace(
      go.Scatter(
          x=proj_years_list,
          y=pv_fcfs,
          name="Present Value FCF",
          mode="lines+markers",
          marker_color="royalblue",
      )
  )
  fig.update_layout(
      title=f"Grafik Proyeksi FCF {projection_years} Tahun ke Depan",
      xaxis_title="Periode",
      yaxis_title="Nilai (IDR)",
  )
  st.plotly_chart(fig, use_container_width=True)

with tab3:
  st.subheader("🏢 Relative Valuation & DDM Analysis")
  col_r1, col_r2 = st.columns(2)

  with col_r1:
    st.markdown(
        "#### Relative Multiples Valuation (Forward EPS/BVPS & Rata-rata"
        " Multiplier)"
    )
    st.write(
        f"• **1. Pendekatan PER (Rata-rata {avg_pe:.1f}x × EPS Forward"
        f" {int(earnings_growth_rate*100)}% = Rp {eps_forward:,.0f}):** Rp"
        f" {val_per_price:,.0f}"
    )
    st.write(
        f"• **2. Pendekatan PBV (Rata-rata {avg_pbv:.1f}x × BVPS Forward ="
        f" Rp {bvps_forward:,.0f}):** Rp {val_pbv_price:,.0f}"
    )
    st.write(
        f"• **3. Pendekatan EV/EBITDA (EV = {avg_ev_ebitda:.1f}x EBITDA -"
        f" Net Debt):** Rp {val_ev_ebitda_price:,.0f}"
    )
    st.write(
        f"• **4. Pendekatan EV/Sales (EV = {avg_ev_sales:.1f}x Sales -"
        f" Net Debt):** Rp {val_ev_sales_price:,.0f}"
    )

  with col_r2:
    st.markdown("#### Dividend Discount Model (DDM)")
    if has_consistent_dividend:
      st.success(
          f"✅ **Emiten Membagikan Dividen Rutin**\n\nEstimasi Harga Wajar DDM:"
          f" **Rp {ddm_value:,.0f}**"
      )
    else:
      st.warning(
          "⚠️ **Tidak Konsisten / Tidak Membagikan Dividen**\n\nSesuai"
          " ketentuan, kolom harga wajar DDM dikosongkan (-)."
      )