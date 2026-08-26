"""
한국은행 ECOS & 미국 연준 FRED 데이터 기반 채권 & 환율 거시경제 통합 대시보드
챕터별(인덱스 탭) 네비게이션 구성:
- 챕터 1: KR 국고채(3년) 금리 추이
- 챕터 2: KR 회사채(3년, AA-) 금리 추이
- 챕터 3: US 국채(10년) vs (2년) 금리 추이 & 장단기 금리차 (역전 구간 음영)
- 챕터 4: 신용 스프레드 (KR 국고채 대비 회사채) 추이 & 평균 비교
- 챕터 5: 원/달러 환율 추이 & 환헤지 시나리오 시뮬레이션
"""

import os
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -----------------------------------------------------------------------------
# 1. 페이지 환경설정 & 디자인 테마
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="한·미 채권 & 환율 거시경제 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Dashboard Styling
st.markdown("""
<style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    
    html, body, [class*="css"] {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: rgba(255, 255, 255, 0.03);
        padding: 8px 12px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        padding: 0 16px;
        background-color: transparent;
        border-radius: 8px;
        color: #94a3b8;
        font-weight: 600;
        font-size: 0.95rem;
        transition: all 0.2s ease;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(59, 130, 246, 0.18) !important;
        color: #60a5fa !important;
        border: 1px solid rgba(59, 130, 246, 0.4) !important;
    }
    
    .metric-card {
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02));
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: rgba(255, 255, 255, 0.25);
    }
    .metric-title {
        font-size: 0.85rem;
        color: #94a3b8;
        font-weight: 500;
        margin-bottom: 6px;
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #f8fafc;
        letter-spacing: -0.5px;
    }
    .metric-sub {
        font-size: 0.8rem;
        margin-top: 4px;
    }
    .badge-inversion {
        background-color: rgba(239, 68, 68, 0.2);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.4);
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .badge-normal {
        background-color: rgba(34, 197, 94, 0.15);
        color: #4ade80;
        border: 1px solid rgba(34, 197, 94, 0.3);
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

BASE_DIR = Path(__file__).resolve().parent
KTB_FILE = BASE_DIR / "ecos_ktb_3y.csv"
KTB_10Y_FILE = BASE_DIR / "ecos_ktb_10y.csv"
CORP_FILE = BASE_DIR / "ecos_corp_aa_3y.csv"
SPREAD_FILE = BASE_DIR / "bond_spread_3y.csv"
USD_KRW_FILE = BASE_DIR / "usd_krw.csv"
BASE_RATE_FILE = BASE_DIR / "base_rate_history.csv"
US_10Y_FILE = BASE_DIR / "us_treasury_10y.csv"
US_2Y_FILE = BASE_DIR / "us_treasury_2y.csv"
US_SPREAD_FILE = BASE_DIR / "us_treasury_spread_10y2y.csv"
US_PERIODS_FILE = BASE_DIR / "inversion_periods.csv"


# -----------------------------------------------------------------------------
# 2. 데이터 로드 및 전처리 캐싱 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
def load_all_data():
    """모든 CSV 파일을 로드하여 정제된 DataFrame으로 반환합니다."""
    data = {}

    # 1. 국고채 & 회사채 스프레드 데이터
    if SPREAD_FILE.exists():
        df_sp = pd.read_csv(SPREAD_FILE)
        df_sp["DATE"] = pd.to_datetime(df_sp["TIME"].astype(str), format="%Y%m%d")
        df_sp["TIME_STR"] = df_sp["DATE"].dt.strftime("%Y-%m-%d")
        data["spread"] = df_sp.sort_values("DATE").reset_index(drop=True)
    elif KTB_FILE.exists() and CORP_FILE.exists():
        df_k = pd.read_csv(KTB_FILE)[["TIME", "DATA_VALUE"]].rename(columns={"DATA_VALUE": "KTB_3Y"})
        df_c = pd.read_csv(CORP_FILE)[["TIME", "DATA_VALUE"]].rename(columns={"DATA_VALUE": "CORP_AA_3Y"})
        df_sp = pd.merge(df_k, df_c, on="TIME", how="inner")
        df_sp["DATE"] = pd.to_datetime(df_sp["TIME"].astype(str), format="%Y%m%d")
        df_sp["TIME_STR"] = df_sp["DATE"].dt.strftime("%Y-%m-%d")
        df_sp["SPREAD"] = (df_sp["CORP_AA_3Y"] - df_sp["KTB_3Y"]).round(4)
        df_sp["SPREAD_BP"] = (df_sp["SPREAD"] * 100).round(2)
        data["spread"] = df_sp.sort_values("DATE").reset_index(drop=True)
    else:
        data["spread"] = pd.DataFrame()

    # 2. 국고채 3년물 단독 데이터
    if KTB_FILE.exists():
        df_k3 = pd.read_csv(KTB_FILE)
        df_k3["DATE"] = pd.to_datetime(df_k3["TIME"].astype(str), format="%Y%m%d")
        df_k3["TIME_STR"] = df_k3["DATE"].dt.strftime("%Y-%m-%d")
        df_k3["KTB_3Y"] = pd.to_numeric(df_k3["DATA_VALUE"], errors="coerce")
        data["ktb_3y"] = df_k3.dropna(subset=["KTB_3Y"]).sort_values("DATE").reset_index(drop=True)
    else:
        data["ktb_3y"] = pd.DataFrame()

    # 3. 국고채 10년물 데이터
    if KTB_10Y_FILE.exists():
        df_k10 = pd.read_csv(KTB_10Y_FILE)
        df_k10["DATE"] = pd.to_datetime(df_k10["TIME"].astype(str), format="%Y%m%d")
        df_k10["KTB_10Y"] = pd.to_numeric(df_k10["DATA_VALUE"], errors="coerce")
        data["ktb_10y"] = df_k10.dropna(subset=["KTB_10Y"]).sort_values("DATE").reset_index(drop=True)
    else:
        data["ktb_10y"] = pd.DataFrame()

    # 4. 회사채 3년물 AA- 단독 데이터
    if CORP_FILE.exists():
        df_corp = pd.read_csv(CORP_FILE)
        df_corp["DATE"] = pd.to_datetime(df_corp["TIME"].astype(str), format="%Y%m%d")
        df_corp["TIME_STR"] = df_corp["DATE"].dt.strftime("%Y-%m-%d")
        df_corp["CORP_AA_3Y"] = pd.to_numeric(df_corp["DATA_VALUE"], errors="coerce")
        data["corp_3y"] = df_corp.dropna(subset=["CORP_AA_3Y"]).sort_values("DATE").reset_index(drop=True)
    else:
        data["corp_3y"] = pd.DataFrame()

    # 5. 원/달러 환율 데이터
    if USD_KRW_FILE.exists():
        df_fx = pd.read_csv(USD_KRW_FILE)
        df_fx["DATE"] = pd.to_datetime(df_fx["TIME"].astype(str), format="%Y%m%d")
        df_fx["TIME_STR"] = df_fx["DATE"].dt.strftime("%Y-%m-%d")
        df_fx["USD_KRW"] = pd.to_numeric(df_fx["DATA_VALUE"], errors="coerce")
        data["fx"] = df_fx.dropna(subset=["USD_KRW"]).sort_values("DATE").reset_index(drop=True)
    else:
        data["fx"] = pd.DataFrame()

    # 6. 미국 국채 10년물 & 2년물 데이터
    if US_10Y_FILE.exists() and US_2Y_FILE.exists():
        df_u10 = pd.read_csv(US_10Y_FILE)[["DATE", "DATA_VALUE"]].rename(columns={"DATA_VALUE": "US_10Y"})
        df_u2 = pd.read_csv(US_2Y_FILE)[["DATE", "DATA_VALUE"]].rename(columns={"DATA_VALUE": "US_2Y"})
        df_us = pd.merge(df_u10, df_u2, on="DATE", how="inner")
        df_us["DATE"] = pd.to_datetime(df_us["DATE"])
        df_us["TIME_STR"] = df_us["DATE"].dt.strftime("%Y-%m-%d")
        df_us["US_10Y"] = pd.to_numeric(df_us["US_10Y"], errors="coerce")
        df_us["US_2Y"] = pd.to_numeric(df_us["US_2Y"], errors="coerce")
        df_us["SPREAD"] = (df_us["US_10Y"] - df_us["US_2Y"]).round(4)
        df_us["SPREAD_BP"] = (df_us["SPREAD"] * 100).round(2)
        df_us["is_inverted"] = df_us["SPREAD"] < 0.0
        data["us_treasury"] = df_us.dropna(subset=["US_10Y", "US_2Y"]).sort_values("DATE").reset_index(drop=True)
    elif US_SPREAD_FILE.exists():
        df_us = pd.read_csv(US_SPREAD_FILE)
        df_us["DATE"] = pd.to_datetime(df_us["DATE"])
        df_us["TIME_STR"] = df_us["DATE"].dt.strftime("%Y-%m-%d")
        data["us_treasury"] = df_us.sort_values("DATE").reset_index(drop=True)
    else:
        data["us_treasury"] = pd.DataFrame()

    # 7. 미국 역전 구간 요약
    if US_PERIODS_FILE.exists():
        data["us_periods"] = pd.read_csv(US_PERIODS_FILE)
    else:
        data["us_periods"] = pd.DataFrame()

    return data


data_dict = load_all_data()
df_spread = data_dict["spread"]
df_ktb3 = data_dict["ktb_3y"]
df_ktb10 = data_dict["ktb_10y"]
df_corp3 = data_dict["corp_3y"]
df_fx = data_dict["fx"]
df_us_treasury = data_dict["us_treasury"]
df_us_periods = data_dict["us_periods"]


# -----------------------------------------------------------------------------
# 3. 사이드바 컨트롤 & 데이터 요약
# -----------------------------------------------------------------------------
with st.sidebar:
    st.image("https://ecos.bok.or.kr/resources/images/common/logo.png", width=180)
    st.title("⚙️ 대시보드 설정")
    st.caption("한국은행 ECOS & 미국 연준 FRED 실시간 연동")
    st.divider()

    # 기간 선택 필터
    st.subheader("📅 조회 기간 필터")
    period_option = st.radio(
        "분석 기간 선택",
        ["최근 1년", "최근 3년", "최근 5년 (전체)", "사용자 지정"],
        index=2
    )

    if not df_spread.empty:
        max_date = df_spread["DATE"].max().date()
        min_date_5y = df_spread["DATE"].min().date()

        if period_option == "최근 1년":
            start_filter_date = max_date - timedelta(days=365)
            end_filter_date = max_date
        elif period_option == "최근 3년":
            start_filter_date = max_date - timedelta(days=3*365)
            end_filter_date = max_date
        elif period_option == "최근 5년 (전체)":
            start_filter_date = min_date_5y
            end_filter_date = max_date
        else:
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                start_filter_date = st.date_input("시작일", min_date_5y, min_value=min_date_5y, max_value=max_date)
            with col_d2:
                end_filter_date = st.date_input("종료일", max_date, min_value=min_date_5y, max_value=max_date)
    else:
        start_filter_date = datetime.now().date() - timedelta(days=365*5)
        end_filter_date = datetime.now().date()

    st.divider()
    st.subheader("📊 데이터 파일 상태")
    st.markdown(f"""
    - **국고채(3년)**: `{'✅ 정상' if not df_ktb3.empty else '❌ 미발견'}` ({len(df_ktb3):,}건)
    - **회사채(3년, AA-)**: `{'✅ 정상' if not df_corp3.empty else '❌ 미발견'}` ({len(df_corp3):,}건)
    - **미국 국채(10Y/2Y)**: `{'✅ 정상' if not df_us_treasury.empty else '❌ 미발견'}` ({len(df_us_treasury):,}건)
    - **신용 스프레드**: `{'✅ 정상' if not df_spread.empty else '❌ 미발견'}` ({len(df_spread):,}건)
    - **원/달러 환율**: `{'✅ 정상' if not df_fx.empty else '❌ 미발견'}` ({len(df_fx):,}건)
    """)

    if st.button("🔄 캐시 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# 필터링 적용 DataFrame
if not df_ktb3.empty:
    mask_k3 = (df_ktb3["DATE"].dt.date >= start_filter_date) & (df_ktb3["DATE"].dt.date <= end_filter_date)
    filtered_ktb3 = df_ktb3[mask_k3].copy()
else:
    filtered_ktb3 = pd.DataFrame()

if not df_corp3.empty:
    mask_c3 = (df_corp3["DATE"].dt.date >= start_filter_date) & (df_corp3["DATE"].dt.date <= end_filter_date)
    filtered_corp3 = df_corp3[mask_c3].copy()
else:
    filtered_corp3 = pd.DataFrame()

if not df_spread.empty:
    mask_spread = (df_spread["DATE"].dt.date >= start_filter_date) & (df_spread["DATE"].dt.date <= end_filter_date)
    filtered_spread = df_spread[mask_spread].copy()
else:
    filtered_spread = pd.DataFrame()

if not df_fx.empty:
    mask_fx = (df_fx["DATE"].dt.date >= start_filter_date) & (df_fx["DATE"].dt.date <= end_filter_date)
    filtered_fx = df_fx[mask_fx].copy()
else:
    filtered_fx = pd.DataFrame()

if not df_us_treasury.empty:
    mask_us = (df_us_treasury["DATE"].dt.date >= start_filter_date) & (df_us_treasury["DATE"].dt.date <= end_filter_date)
    filtered_us = df_us_treasury[mask_us].copy()
else:
    filtered_us = pd.DataFrame()


# -----------------------------------------------------------------------------
# 4. 헤더 및 주요 경제 지표 KPI 카드 (상단 요약)
# -----------------------------------------------------------------------------
st.title("📈 한·미 채권 & 환율 거시경제 모니터링 대시보드")
st.markdown("한국은행(ECOS) 및 미국 연방준비은행(FRED) 데이터를 기반으로 챕터별 채권 시장 및 환율 지표를 심층 모니터링합니다.")

if not df_spread.empty and not df_fx.empty:
    latest_sp = df_spread.iloc[-1]
    prev_sp = df_spread.iloc[-2] if len(df_spread) >= 2 else latest_sp
    latest_fx = df_fx.iloc[-1]
    prev_fx = df_fx.iloc[-2] if len(df_fx) >= 2 else latest_fx
    latest_us = df_us_treasury.iloc[-1] if not df_us_treasury.empty else None

    # 전일대비 변동 계산
    delta_ktb = latest_sp["KTB_3Y"] - prev_sp["KTB_3Y"]
    delta_corp = latest_sp["CORP_AA_3Y"] - prev_sp["CORP_AA_3Y"]
    delta_spread = latest_sp["SPREAD_BP"] - prev_sp["SPREAD_BP"]
    delta_fx = latest_fx["USD_KRW"] - prev_fx["USD_KRW"]

    # 1년 평균 스프레드
    date_max = df_spread["DATE"].max()
    df_1y = df_spread[df_spread["DATE"] >= (date_max - timedelta(days=365))]
    avg_1y_bp = df_1y["SPREAD_BP"].mean()
    ratio_1y = (latest_sp["SPREAD_BP"] / avg_1y_bp) * 100

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric(
            label="🇰🇷 국고채 (3년)",
            value=f"{latest_sp['KTB_3Y']:.3f} %",
            delta=f"{delta_ktb:+.3f} %p",
            delta_color="inverse"
        )
    with col2:
        st.metric(
            label="🇰🇷 회사채 (3년, AA-)",
            value=f"{latest_sp['CORP_AA_3Y']:.3f} %",
            delta=f"{delta_corp:+.3f} %p",
            delta_color="inverse"
        )
    with col3:
        if latest_us is not None:
            st.metric(
                label="🇺🇸 미국 국채 10Y / 2Y",
                value=f"{latest_us['US_10Y']:.2f}% / {latest_us['US_2Y']:.2f}%",
                delta=f"10Y-2Y: {latest_us['SPREAD_BP']:+.1f} bp"
            )
        else:
            st.metric(label="🇺🇸 미국 국채", value="-")
    with col4:
        st.metric(
            label="📊 신용 스프레드",
            value=f"{latest_sp['SPREAD_BP']:.1f} bp",
            delta=f"{delta_spread:+.1f} bp (평균 {ratio_1y:.1f}%)",
            delta_color="inverse"
        )
    with col5:
        st.metric(
            label="💵 원/달러 환율",
            value=f"{latest_fx['USD_KRW']:,.2f} 원",
            delta=f"{delta_fx:+.2f} 원",
            delta_color="inverse"
        )

st.divider()

# -----------------------------------------------------------------------------
# 5. 챕터별 인덱스 탭 (Tab 1 ~ Tab 5)
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1️⃣ KR 국고채(3년) 금리 추이",
    "2️⃣ KR 회사채(3년, AA-) 금리 추이",
    "3️⃣ US 국채(10년 vs 2년) & 장단기 금리차",
    "4️⃣ 신용 스프레드 분석",
    "5️⃣ 원/달러 환율 & 환헤지 시나리오"
])


# =============================================================================
# 챕터 1: KR 국고채(3년) 금리 추이
# =============================================================================
with tab1:
    st.subheader("1. 🇰🇷 KR 국고채(3년) 금리 추이")
    st.caption("한국 채권시장의 대표적인 무위험 벤치마크 지표인 국고채 3년물 일별 금리 추이입니다.")

    if not filtered_ktb3.empty:
        fig_ktb = go.Figure()

        fig_ktb.add_trace(go.Scatter(
            x=filtered_ktb3["DATE"],
            y=filtered_ktb3["KTB_3Y"],
            name="국고채(3년)",
            mode="lines",
            line=dict(color="#3b82f6", width=2.5),
            hovertemplate="<b>국고채(3년)</b><br>일자: %{x|%Y-%m-%d}<br>금리: %{y:.3f}%<extra></extra>"
        ))

        # 기간 내 평균선
        avg_ktb = filtered_ktb3["KTB_3Y"].mean()
        fig_ktb.add_hline(
            y=avg_ktb,
            line_dash="dot",
            line_color="#93c5fd",
            line_width=1.5,
            annotation_text=f"기간 평균 ({avg_ktb:.3f}%)",
            annotation_position="bottom right",
            annotation_font=dict(color="#93c5fd", size=11)
        )

        fig_ktb.update_layout(
            height=430,
            hovermode="x unified",
            xaxis=dict(title="일자", showgrid=True, gridcolor="rgba(255, 255, 255, 0.08)"),
            yaxis=dict(title="금리 (연 %)", showgrid=True, gridcolor="rgba(255, 255, 255, 0.08)", ticksuffix="%"),
            margin=dict(l=30, r=30, t=30, b=30)
        )
        st.plotly_chart(fig_ktb, use_container_width=True)

        # 요약 메트릭
        latest_k3_row = filtered_ktb3.iloc[-1]
        kc1, kc2, kc3, kc4 = st.columns(4)
        with kc1:
            st.caption(f"최근 기준일: **`{latest_k3_row['TIME_STR']}`**")
        with kc2:
            st.caption(f"현재 금리: **`{latest_k3_row['KTB_3Y']:.3f} %`**")
        with kc3:
            st.caption(f"기간 내 최저: **`{filtered_ktb3['KTB_3Y'].min():.3f} %`**")
        with kc4:
            st.caption(f"기간 내 최고: **`{filtered_ktb3['KTB_3Y'].max():.3f} %`**")

        st.divider()

        with st.expander("📋 국고채(3년) 상세 데이터 테이블"):
            st.dataframe(
                filtered_ktb3[["TIME_STR", "KTB_3Y"]].rename(columns={"TIME_STR": "일자", "KTB_3Y": "국고채 3년 금리(%)"}).tail(100).sort_values("일자", ascending=False),
                use_container_width=True,
                hide_index=True
            )
    else:
        st.warning("국고채(3년) 데이터가 없습니다.")


# =============================================================================
# 챕터 2: KR 회사채(3년, AA-) 금리 추이
# =============================================================================
with tab2:
    st.subheader("2. 🇰🇷 KR 회사채(3년, AA-) 금리 추이")
    st.caption("국내 우량 기업들의 자금 조달 금리 기준이 되는 무보증 회사채(3년물, AA- 등급) 일별 금리 추이입니다.")

    if not filtered_corp3.empty:
        fig_corp = go.Figure()

        fig_corp.add_trace(go.Scatter(
            x=filtered_corp3["DATE"],
            y=filtered_corp3["CORP_AA_3Y"],
            name="회사채(3년, AA-)",
            mode="lines",
            line=dict(color="#f59e0b", width=2.5),
            hovertemplate="<b>회사채(3년, AA-)</b><br>일자: %{x|%Y-%m-%d}<br>금리: %{y:.3f}%<extra></extra>"
        ))

        avg_corp = filtered_corp3["CORP_AA_3Y"].mean()
        fig_corp.add_hline(
            y=avg_corp,
            line_dash="dot",
            line_color="#fcd34d",
            line_width=1.5,
            annotation_text=f"기간 평균 ({avg_corp:.3f}%)",
            annotation_position="bottom right",
            annotation_font=dict(color="#fcd34d", size=11)
        )

        fig_corp.update_layout(
            height=430,
            hovermode="x unified",
            xaxis=dict(title="일자", showgrid=True, gridcolor="rgba(255, 255, 255, 0.08)"),
            yaxis=dict(title="금리 (연 %)", showgrid=True, gridcolor="rgba(255, 255, 255, 0.08)", ticksuffix="%"),
            margin=dict(l=30, r=30, t=30, b=30)
        )
        st.plotly_chart(fig_corp, use_container_width=True)

        latest_c3_row = filtered_corp3.iloc[-1]
        cc1, cc2, cc3, cc4 = st.columns(4)
        with cc1:
            st.caption(f"최근 기준일: **`{latest_c3_row['TIME_STR']}`**")
        with cc2:
            st.caption(f"현재 금리: **`{latest_c3_row['CORP_AA_3Y']:.3f} %`**")
        with cc3:
            st.caption(f"기간 내 최저: **`{filtered_corp3['CORP_AA_3Y'].min():.3f} %`**")
        with cc4:
            st.caption(f"기간 내 최고: **`{filtered_corp3['CORP_AA_3Y'].max():.3f} %`**")

        st.divider()

        with st.expander("📋 회사채(3년, AA-) 상세 데이터 테이블"):
            st.dataframe(
                filtered_corp3[["TIME_STR", "CORP_AA_3Y"]].rename(columns={"TIME_STR": "일자", "CORP_AA_3Y": "회사채 3년 AA- 금리(%)"}).tail(100).sort_values("일자", ascending=False),
                use_container_width=True,
                hide_index=True
            )
    else:
        st.warning("회사채(3년, AA-) 데이터가 없습니다.")


# =============================================================================
# 챕터 3: US 국채(10년) vs (2년) 금리 추이 + US 10Y-2Y 장단기 금리차 (역전 음영)
# =============================================================================
with tab3:
    st.subheader("3. 🇺🇸 US 국채(10년) vs (2년) 금리 추이 & 장단기 금리차 (Inversion)")
    st.caption("미국 연방준비은행(FRED) 데이터 기반 미국 국채 10년물(DGS10) 및 2년물(DGS2) 금리와 장단기 금리차 추이를 분석합니다. 스프레드가 마이너스인 역전 구간은 배경색으로 음영 표시됩니다.")

    if not filtered_us.empty:
        latest_us_data = filtered_us.iloc[-1]
        is_inv_now = latest_us_data["is_inverted"]

        # 상단 요약 카드
        uc1, uc2, uc3, uc4 = st.columns(4)
        with uc1:
            st.metric(label="미국 국채 (10년물)", value=f"{latest_us_data['US_10Y']:.2f} %")
        with uc2:
            st.metric(label="미국 국채 (2년물)", value=f"{latest_us_data['US_2Y']:.2f} %")
        with uc3:
            st.metric(label="10Y-2Y 스프레드", value=f"{latest_us_data['SPREAD']:+.2f} %p", delta=f"{latest_us_data['SPREAD_BP']:+.1f} bp")
        with uc4:
            inv_badge = '<span class="badge-inversion">🚨 금리 역전 상태</span>' if is_inv_now else '<span class="badge-normal">✅ 정상 상태 (10Y > 2Y)</span>'
            st.markdown(f"""
            <div style="padding: 10px; border-radius: 8px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); text-align:center;">
                <div style="font-size:0.78rem; color:#94a3b8; margin-bottom:2px;">현재 역전 여부 ({latest_us_data['TIME_STR']})</div>
                <div>{inv_badge}</div>
            </div>
            """, unsafe_allow_html=True)

        st.write("")

        # [1] 미국 10년물 vs 2년물 금리 그래프
        fig_us_compare = go.Figure()

        fig_us_compare.add_trace(go.Scatter(
            x=filtered_us["DATE"],
            y=filtered_us["US_10Y"],
            name="미국 10년물 (DGS10)",
            mode="lines",
            line=dict(color="#06b6d4", width=2.5),
            hovertemplate="<b>미국 10년물</b><br>일자: %{x|%Y-%m-%d}<br>금리: %{y:.2f}%<extra></extra>"
        ))

        fig_us_compare.add_trace(go.Scatter(
            x=filtered_us["DATE"],
            y=filtered_us["US_2Y"],
            name="미국 2년물 (DGS2)",
            mode="lines",
            line=dict(color="#f43f5e", width=2.5),
            hovertemplate="<b>미국 2년물</b><br>일자: %{x|%Y-%m-%d}<br>금리: %{y:.2f}%<extra></extra>"
        ))

        # 역전 구간 음영 표시 (상단 차트)
        if not df_us_periods.empty:
            for _, period_row in df_us_periods.iterrows():
                p_start = str(period_row["시작일"])
                p_end = str(period_row["종료일"]).split()[0]
                fig_us_compare.add_vrect(
                    x0=p_start,
                    x1=p_end,
                    fillcolor="rgba(239, 68, 68, 0.12)",
                    layer="below",
                    line_width=0
                )

        fig_us_compare.update_layout(
            title="<b>[차트 A] 미국 국채 10년물 vs 2년물 금리 추이</b>",
            height=380,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(title="일자", showgrid=True, gridcolor="rgba(255, 255, 255, 0.08)"),
            yaxis=dict(title="금리 (연 %)", showgrid=True, gridcolor="rgba(255, 255, 255, 0.08)", ticksuffix="%"),
            margin=dict(l=30, r=30, t=50, b=30)
        )
        st.plotly_chart(fig_us_compare, use_container_width=True)

        # [2] 바로 아래: US 10년물 - 2년물 장단기 금리차 그래프 (마이너스 구간 배경색 음영 표시)
        fig_us_spread = go.Figure()

        fig_us_spread.add_trace(go.Scatter(
            x=filtered_us["DATE"],
            y=filtered_us["SPREAD_BP"],
            name="10Y-2Y 스프레드 (bp)",
            mode="lines",
            line=dict(color="#38bdf8", width=2.5),
            hovertemplate="<b>10Y-2Y 스프레드</b><br>일자: %{x|%Y-%m-%d}<br>스프레드: %{y:+.1f} bp (%{customdata:+.2f}%%p)<extra></extra>",
            customdata=filtered_us["SPREAD"]
        ))

        # 0 bp 기준선 (빨간색 점선)
        fig_us_spread.add_hline(
            y=0,
            line_dash="dash",
            line_color="#ef4444",
            line_width=2,
            annotation_text="금리 역전 기준선 (0 bp)",
            annotation_position="bottom right",
            annotation_font=dict(color="#ef4444", size=11)
        )

        # 역전 구간 음영 표시 (하단 스프레드 차트)
        if not df_us_periods.empty:
            for _, period_row in df_us_periods.iterrows():
                p_start = str(period_row["시작일"])
                p_end = str(period_row["종료일"]).split()[0]
                fig_us_spread.add_vrect(
                    x0=p_start,
                    x1=p_end,
                    fillcolor="rgba(239, 68, 68, 0.16)",
                    layer="below",
                    line_width=1,
                    line_color="rgba(239, 68, 68, 0.3)",
                    annotation_text="금리 역전 구간",
                    annotation_position="top left",
                    annotation_font=dict(color="#f87171", size=10)
                )

        fig_us_spread.update_layout(
            title="<b>[차트 B] 미국 국채 10Y-2Y 장단기 금리차 (10년물 - 2년물) & 역전 구간</b>",
            height=380,
            hovermode="x unified",
            xaxis=dict(title="일자", showgrid=True, gridcolor="rgba(255, 255, 255, 0.08)"),
            yaxis=dict(title="장단기 금리차 (bp)", showgrid=True, gridcolor="rgba(255, 255, 255, 0.08)", ticksuffix=" bp"),
            margin=dict(l=30, r=30, t=50, b=30)
        )
        st.plotly_chart(fig_us_spread, use_container_width=True)

        # 역전 구간 요약 표
        if not df_us_periods.empty:
            with st.expander("📋 최근 5개년 미국 국채 금리역전(Inversion) 구간 상세 요약"):
                st.dataframe(df_us_periods, use_container_width=True, hide_index=True)

        # 지표 배경 설명
        st.info("""
        📚 **장단기 금리역전(Yield Curve Inversion) 지표 안내**:
        1. **정의**: 장단기 금리역전이란 장기(10년물) 국채 금리가 단기(2년물) 국채 금리보다 낮아지는 현상(10년물 금리 - 2년물 금리 < 0)을 뜻합니다.
        2. **일반적 통념**: 금융시장에서는 통상적으로 장단기 금리역전 현상이 경기침체(Recession)를 예고하는 대표적인 선행지표 중 하나로 알려져 있습니다.
        3. **안내 사항**: 본 설명 및 데이터는 금융시장에서 일반적으로 알려진 학술적·통념적 배경지식이며, 특정 시점의 투자 권유, 매매 판단 또는 미래 시장에 대한 전망을 의미하지 않습니다.
        """)
    else:
        st.warning("미국 국채 데이터가 없습니다. `python fetch_fred.py`를 실행해주세요.")


# =============================================================================
# 챕터 4: 신용 스프레드 (KR 국고채 대비 회사채) 추이 & 평균 비교
# =============================================================================
with tab4:
    st.subheader("4. 📊 신용 스프레드 (KR 국고채 대비 회사채) 추이 및 평균 분석")
    st.caption("신용 스프레드(회사채 3년 AA- 금리 - 국고채 3년 금리) 추이와 현재값, 1년 평균, 5년 평균을 비교하여 기업 자금 조달 여건 및 시장 신용 프리미엄을 진단합니다.")

    if not df_spread.empty:
        date_max = df_spread["DATE"].max()
        df_1y_full = df_spread[df_spread["DATE"] >= (date_max - timedelta(days=365))]
        
        current_spread_pct = latest_sp["SPREAD"]
        current_spread_bp = latest_sp["SPREAD_BP"]
        
        avg_1y_pct = df_1y_full["SPREAD"].mean()
        avg_1y_bp = df_1y_full["SPREAD_BP"].mean()
        
        avg_5y_pct = df_spread["SPREAD"].mean()
        avg_5y_bp = df_spread["SPREAD_BP"].mean()

        ratio_to_1y = (current_spread_bp / avg_1y_bp) * 100
        ratio_to_5y = (current_spread_bp / avg_5y_bp) * 100

        c_kpi1, c_kpi2, c_kpi3 = st.columns(3)
        with c_kpi1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">📌 현재 신용 스프레드 ({latest_sp['TIME_STR']})</div>
                <div class="metric-value">{current_spread_pct:.4f}%p <span style="font-size:1.1rem; color:#38bdf8;">({current_spread_bp:.1f} bp)</span></div>
                <div class="metric-sub" style="color: #94a3b8;">국고채 {latest_sp['KTB_3Y']:.3f}% vs 회사채 {latest_sp['CORP_AA_3Y']:.3f}%</div>
            </div>
            """, unsafe_allow_html=True)

        with c_kpi2:
            diff_1y = current_spread_bp - avg_1y_bp
            diff_color = "#ef4444" if diff_1y > 0 else "#22c55e"
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">📅 최근 1년 평균 스프레드 ({len(df_1y_full):,}영업일)</div>
                <div class="metric-value">{avg_1y_pct:.4f}%p <span style="font-size:1.1rem; color:#94a3b8;">({avg_1y_bp:.1f} bp)</span></div>
                <div class="metric-sub" style="color: {diff_color}; font-weight:600;">
                    현재값은 1년 평균의 {ratio_to_1y:.1f}% ({diff_1y:+.1f} bp)
                </div>
            </div>
            """, unsafe_allow_html=True)

        with c_kpi3:
            diff_5y = current_spread_bp - avg_5y_bp
            diff_5y_color = "#ef4444" if diff_5y > 0 else "#22c55e"
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">🏛️ 최근 5년 평균 스프레드 ({len(df_spread):,}영업일)</div>
                <div class="metric-value">{avg_5y_pct:.4f}%p <span style="font-size:1.1rem; color:#94a3b8;">({avg_5y_bp:.1f} bp)</span></div>
                <div class="metric-sub" style="color: {diff_5y_color}; font-weight:600;">
                    현재값은 5년 평균의 {ratio_to_5y:.1f}% ({diff_5y:+.1f} bp)
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.write("")

        # 스프레드 인터랙티브 차트 (1년/5년 평균선 + 영역 채우기)
        fig_sp = go.Figure()

        fig_sp.add_trace(go.Scatter(
            x=filtered_spread["DATE"],
            y=filtered_spread["SPREAD_BP"],
            name="신용 스프레드 (bp)",
            mode="lines",
            line=dict(color="#8b5cf6", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(139, 92, 246, 0.12)",
            hovertemplate="<b>신용 스프레드</b><br>일자: %{x|%Y-%m-%d}<br>스프레드: %{y:.1f} bp (%{customdata:.3f}%%p)<extra></extra>",
            customdata=filtered_spread["SPREAD"]
        ))

        fig_sp.add_hline(
            y=avg_1y_bp,
            line_dash="dash",
            line_color="#38bdf8",
            line_width=2,
            annotation_text=f"1년 평균 ({avg_1y_bp:.1f} bp)",
            annotation_position="top right",
            annotation_font=dict(color="#38bdf8", size=12)
        )

        fig_sp.add_hline(
            y=avg_5y_bp,
            line_dash="dot",
            line_color="#f59e0b",
            line_width=2,
            annotation_text=f"5년 평균 ({avg_5y_bp:.1f} bp)",
            annotation_position="bottom right",
            annotation_font=dict(color="#f59e0b", size=12)
        )

        max_row = df_spread.loc[df_spread["SPREAD_BP"].idxmax()]
        if filtered_spread["DATE"].min() <= max_row["DATE"] <= filtered_spread["DATE"].max():
            fig_sp.add_annotation(
                x=max_row["DATE"],
                y=max_row["SPREAD_BP"],
                text=f"5년 최고치 ({max_row['SPREAD_BP']:.1f} bp)<br>2022 레고랜드 신용경색",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=2,
                arrowcolor="#ef4444",
                ax=0,
                ay=-45,
                bgcolor="rgba(239, 68, 68, 0.2)",
                bordercolor="#ef4444",
                font=dict(color="#fca5a5", size=11)
            )

        fig_sp.update_layout(
            height=450,
            hovermode="x unified",
            xaxis=dict(title="일자", showgrid=True, gridcolor="rgba(255, 255, 255, 0.08)"),
            yaxis=dict(title="스프레드 (bp = 0.01%p)", showgrid=True, gridcolor="rgba(255, 255, 255, 0.08)", ticksuffix=" bp"),
            margin=dict(l=30, r=30, t=30, b=30)
        )
        st.plotly_chart(fig_sp, use_container_width=True)

        st.divider()

        with st.expander("📋 신용 스프레드 상세 데이터 테이블"):
            st.dataframe(
                filtered_spread[["TIME_STR", "KTB_3Y", "CORP_AA_3Y", "SPREAD", "SPREAD_BP"]].rename(columns={
                    "TIME_STR": "일자",
                    "KTB_3Y": "국고채 3년(%)",
                    "CORP_AA_3Y": "회사채 AA-(%)",
                    "SPREAD": "스프레드(%p)",
                    "SPREAD_BP": "스프레드(bp)"
                }).tail(100).sort_values("일자", ascending=False),
                use_container_width=True,
                hide_index=True
            )
    else:
        st.warning("스프레드 데이터를 로드할 수 없습니다.")


# =============================================================================
# 챕터 5: 원/달러 환율 추이 + 환헤지 시나리오 시뮬레이션
# =============================================================================
with tab5:
    st.subheader("5. 💵 원/달러 환율 추이 및 환헤지 vs 환오픈 손익 시뮬레이션")
    st.caption("원/달러 환율 추이와 달러 자산 투자 시 환헤지 비용(연 1.5% 가정)에 따른 시나리오별 실질 손익 및 손익분기점(BEP)을 시뮬레이션합니다.")

    if not filtered_fx.empty:
        fig_fx = go.Figure()

        fig_fx.add_trace(go.Scatter(
            x=filtered_fx["DATE"],
            y=filtered_fx["USD_KRW"],
            name="원/달러 환율",
            mode="lines",
            line=dict(color="#06b6d4", width=2.5),
            hovertemplate="<b>원/달러 환율</b><br>일자: %{x|%Y-%m-%d}<br>환율: %{y:,.2f}원<extra></extra>"
        ))

        if len(filtered_fx) >= 60:
            filtered_fx["MA_60"] = filtered_fx["USD_KRW"].rolling(60).mean()
            fig_fx.add_trace(go.Scatter(
                x=filtered_fx["DATE"],
                y=filtered_fx["MA_60"],
                name="60일 이동평균",
                mode="lines",
                line=dict(color="rgba(255, 255, 255, 0.4)", width=1.5, dash="dot"),
                hovertemplate="60일 이평: %{y:,.2f}원<extra></extra>"
            ))

        fig_fx.update_layout(
            height=380,
            hovermode="x unified",
            xaxis=dict(title="일자", showgrid=True, gridcolor="rgba(255, 255, 255, 0.08)"),
            yaxis=dict(title="환율 (원/달러)", showgrid=True, gridcolor="rgba(255, 255, 255, 0.08)", ticksuffix="원"),
            margin=dict(l=30, r=30, t=30, b=30)
        )
        st.plotly_chart(fig_fx, use_container_width=True)

        st.divider()

        # 대화형 환헤지 시나리오 시뮬레이터 위젯 (천 단위 쉼표 포맷팅)
        st.markdown("##### 🧮 환헤지 vs 환오픈 손익 시뮬레이터")

        sim_c1, sim_c2, sim_c3 = st.columns(3)
        with sim_c1:
            input_hedge_cost = st.slider("연간 환헤지 비용 (%)", min_value=0.0, max_value=4.0, value=1.5, step=0.1)
        with sim_c2:
            input_asset_yield = st.slider("달러 자산 기본 연 수익률 (%)", min_value=0.0, max_value=8.0, value=4.5, step=0.1)
        with sim_c3:
            input_principal = st.number_input(
                "투자 원금 (원 단위, 쉼표 포맷)",
                min_value=1_000_000,
                max_value=10_000_000_000,
                value=100_000_000,
                step=10_000_000,
                format="%d",
                help="원화 기준 투자 원금을 입력하세요 (기본: 100,000,000원)"
            )
            st.caption(f"💰 설정된 투자원금: **`{input_principal:,.0f} 원`**")

        current_fx_rate = df_fx.iloc[-1]["USD_KRW"]
        bep_change = -input_hedge_cost

        scenarios = [
            {"name": "환율 +10% 급등 (원화 약세)", "change": 10.0},
            {"name": "환율 +5% 상승  (원화 약세)", "change": 5.0},
            {"name": "현재 환율 유지 (0%)", "change": 0.0},
            {"name": f"손익분기점 BEP ({bep_change:+.1f}%)", "change": bep_change},
            {"name": "환율 -5% 하락  (원화 강세)", "change": -5.0},
            {"name": "환율 -10% 급락 (원화 강세)", "change": -10.0},
        ]

        r_asset = input_asset_yield / 100.0
        r_hedge = input_hedge_cost / 100.0
        initial_usd = input_principal / current_fx_rate

        sim_rows = []
        for sc in scenarios:
            chg = sc["change"]
            r_fx = chg / 100.0
            sc_rate = current_fx_rate * (1.0 + r_fx)

            unhedged_ret = ((1.0 + r_asset) * (1.0 + r_fx) - 1.0) * 100.0
            hedged_ret = (r_asset - r_hedge) * 100.0

            unhedged_final = (initial_usd * (1.0 + r_asset)) * sc_rate
            unhedged_pnl = unhedged_final - input_principal

            hedged_final = input_principal * (1.0 + (hedged_ret / 100.0))
            hedged_pnl = hedged_final - input_principal

            diff_ret = unhedged_ret - hedged_ret
            diff_pnl = unhedged_pnl - hedged_pnl

            sim_rows.append({
                "시나리오": sc["name"],
                "시나리오 환율": f"{sc_rate:,.2f} 원",
                "환오픈 총수익률": f"{unhedged_ret:+.2f} %",
                "환헤지 총수익률": f"{hedged_ret:+.2f} %",
                "수익률 차이": f"{diff_ret:+.2f} %p",
                "환오픈 최종금액": f"{int(round(unhedged_final)):,d} 원",
                "환오픈 최종손익": f"{int(round(unhedged_pnl)):+,d} 원",
                "환헤지 최종금액": f"{int(round(hedged_final)):,d} 원",
                "환헤지 최종손익": f"{int(round(hedged_pnl)):+,d} 원",
                "손익 차이": f"{int(round(diff_pnl)):+,d} 원",
                "우위 전략": "🚀 환오픈 유리" if diff_ret > 0.05 else ("🛡️ 환헤지 유리" if diff_ret < -0.05 else "⚖️ 동일 (BEP)")
            })

        df_sim_table = pd.DataFrame(sim_rows)
        st.dataframe(df_sim_table, use_container_width=True, hide_index=True)

        bep_rate_val = current_fx_rate * (1.0 + bep_change / 100.0)
        st.success(f"""
        🎯 **손익분기점(BEP) 핵심 요약**:
        - 투자 원금: **`{input_principal:,.0f} 원`** (${initial_usd:,.2f})
        - 환율이 **`{bep_rate_val:,.2f} 원` 이상({bep_change:+.1f}% 이상 유지/상승)**일 경우: **환오픈(Unhedged)**이 헤지비용({input_hedge_cost}%)을 절감하여 유리합니다.
        - 환율이 **`{bep_rate_val:,.2f} 원` 미만({bep_change:+.1f}% 초과 하락/원화 급등)**일 경우: **환헤지(Hedged)**가 환손실을 방어하여 유리합니다.
        """)
    else:
        st.warning("환율 데이터가 없습니다.")

# -----------------------------------------------------------------------------
# 6. 푸터
# -----------------------------------------------------------------------------
st.markdown("---")
st.caption("데이터 출처: 한국은행 경제통계시스템(ECOS Open API), 미국 세인트루이스 연방준비은행(FRED API) | 대시보드 자동화 구축 완료")
