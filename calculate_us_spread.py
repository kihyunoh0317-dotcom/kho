"""
미국 국채 10년물(DGS10) vs 2년물(DGS2) 장단기 금리차(10Y-2Y Spread) 및 금리역전(Inversion) 분석기
- 입력: us_treasury_10y.csv, us_treasury_2y.csv
- 출력 1: us_treasury_spread_10y2y.csv (일별 스프레드 및 is_inverted 여부)
- 출력 2: inversion_periods.csv (금리역전 구간별 시작일, 종료일, 지속일수 요약)
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

# Windows 터미널 한글/특수문자 인코딩 안전 설정
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
US_10Y_FILE = BASE_DIR / "us_treasury_10y.csv"
US_2Y_FILE = BASE_DIR / "us_treasury_2y.csv"
OUTPUT_SPREAD_FILE = BASE_DIR / "us_treasury_spread_10y2y.csv"
OUTPUT_PERIODS_FILE = BASE_DIR / "inversion_periods.csv"

# -----------------------------------------------------------------------------
# 지표 배경 설명 텍스트 (단순 사실 및 일반적 통념 설명, 투자 조언/전망 제외)
# -----------------------------------------------------------------------------
INDICATOR_BACKGROUND_INFO = """[장단기 금리역전(Yield Curve Inversion) 지표 안내]
1. 정의:
   장단기 금리역전이란 장기(10년물) 국채 금리가 단기(2년물) 국채 금리보다 낮아지는 현상(10년물 금리 - 2년물 금리 < 0)을 뜻합니다.
2. 일반적 통념:
   금융시장에서는 통상적으로 장단기 금리역전 현상이 경기침체(Recession)를 예고하는 대표적인 선행지표 중 하나로 알려져 있습니다.
3. 안내 사항:
   본 설명 및 데이터는 금융시장에서 일반적으로 알려진 학술적·통념적 배경지식이며, 특정 시점의 투자 권유, 매매 판단 또는 미래 시장에 대한 전망을 의미하지 않습니다."""


def analyze_us_treasury_spread():
    # 1. 원본 파일 존재 여부 확인
    if not US_10Y_FILE.exists() or not US_2Y_FILE.exists():
        print(f"❌ [오류] {US_10Y_FILE.name} 또는 {US_2Y_FILE.name} 파일이 없습니다.")
        print("   먼저 python fetch_fred.py를 실행하여 데이터를 수집해주세요.")
        return

    # 2. CSV 파일 로드
    df_10y = pd.read_csv(US_10Y_FILE)
    df_2y = pd.read_csv(US_2Y_FILE)

    # 필요한 컬럼 추출 및 정리
    df_10y = df_10y[["DATE", "DATA_VALUE"]].rename(columns={"DATA_VALUE": "US_10Y"})
    df_2y = df_2y[["DATE", "DATA_VALUE"]].rename(columns={"DATA_VALUE": "US_2Y"})

    # 3. 날짜(DATE) 기준 병합 (Inner Join)
    df_merged = pd.merge(df_10y, df_2y, on="DATE", how="inner")
    df_merged["US_10Y"] = pd.to_numeric(df_merged["US_10Y"], errors="coerce")
    df_2y_val = pd.to_numeric(df_merged["US_2Y"], errors="coerce")
    df_merged["US_2Y"] = df_2y_val

    df_merged = df_merged.dropna(subset=["US_10Y", "US_2Y"]).sort_values("DATE").reset_index(drop=True)

    # 4. 스프레드 계산 및 역전(is_inverted) 여부 플래그
    # SPREAD = 10년물 금리 - 2년물 금리
    df_merged["SPREAD"] = (df_merged["US_10Y"] - df_merged["US_2Y"]).round(4)
    df_merged["SPREAD_BP"] = (df_merged["SPREAD"] * 100).round(2)  # bp 단위
    df_merged["is_inverted"] = df_merged["SPREAD"] < 0.0

    # 5. us_treasury_spread_10y2y.csv 저장
    df_merged.to_csv(OUTPUT_SPREAD_FILE, index=False, encoding="utf-8-sig")

    # 6. 연속된 금리역전(Inversion) 구간 분석
    periods = []
    in_inversion = False
    start_date = None
    period_spreads = []
    trading_days = 0

    for idx, row in df_merged.iterrows():
        is_inv = row["is_inverted"]
        date = row["DATE"]
        spread = row["SPREAD"]

        if is_inv:
            if not in_inversion:
                # 역전 구간 시작
                in_inversion = True
                start_date = date
                period_spreads = [spread]
                trading_days = 1
            else:
                period_spreads.append(spread)
                trading_days += 1
        else:
            if in_inversion:
                # 역전 구간 종료
                end_date = df_merged.iloc[idx - 1]["DATE"]
                min_spread = min(period_spreads)
                avg_spread = sum(period_spreads) / len(period_spreads)

                periods.append({
                    "시작일": start_date,
                    "종료일": end_date,
                    "지속영업일수": trading_days,
                    "최저스프레드(%p)": round(min_spread, 3),
                    "최저스프레드(bp)": round(min_spread * 100, 1),
                    "평균스프레드(%p)": round(avg_spread, 3),
                    "구간상태": "종료 (정상화 복귀)"
                })
                in_inversion = False
                start_date = None
                period_spreads = []
                trading_days = 0

    # 현재도 역전이 진행 중인 경우 처리
    if in_inversion and start_date:
        end_date = df_merged.iloc[-1]["DATE"]
        min_spread = min(period_spreads)
        avg_spread = sum(period_spreads) / len(period_spreads)
        periods.append({
            "시작일": start_date,
            "종료일": f"{end_date} (진행중)",
            "지속영업일수": trading_days,
            "최저스프레드(%p)": round(min_spread, 3),
            "최저스프레드(bp)": round(min_spread * 100, 1),
            "평균스프레드(%p)": round(avg_spread, 3),
            "구간상태": "현재 역전 진행중"
        })

    df_periods = pd.DataFrame(periods)
    df_periods.to_csv(OUTPUT_PERIODS_FILE, index=False, encoding="utf-8-sig")

    # 7. 최신 데이터 및 화면 출력
    latest = df_merged.iloc[-1]
    latest_date = latest["DATE"]
    latest_10y = latest["US_10Y"]
    latest_2y = latest["US_2Y"]
    latest_spread = latest["SPREAD"]
    latest_bp = latest["SPREAD_BP"]
    is_curr_inverted = latest["is_inverted"]

    status_text = "🚨 역전 상태 (Inverted: 10Y < 2Y)" if is_curr_inverted else "✅ 정상 상태 (Normal: 10Y > 2Y)"

    print("=" * 75)
    print("🌐 [미국 국채 10년물 vs 2년물 장단기 금리차 및 역전 구간 분석]")
    print("=" * 75)
    print(f"📁 스프레드 시계열 저장 완료 : {OUTPUT_SPREAD_FILE.resolve()}")
    print(f"📁 역전 구간 요약 저장 완료   : {OUTPUT_PERIODS_FILE.resolve()}")
    print(f"📈 총 데이터 건수             : {len(df_merged):,}건")
    print(f"📅 전체 데이터 기간           : {df_merged['DATE'].min()} ~ {df_merged['DATE'].max()}")
    print("-" * 75)
    print(f"📌 [최근 기준일: {latest_date}]")
    print(f"   • 미국 국채 10년물 금리 : {latest_10y:.2f}%")
    print(f"   • 미국 국채 2년물 금리  : {latest_2y:.2f}%")
    print(f"   • 장단기 금리차(10Y-2Y) : {latest_spread:+.2f}%p ({latest_bp:+.1f} bp)")
    print(f"   • 현재 금리 역전 여부   : {is_curr_inverted} -> {status_text}")
    print("-" * 75)
    print(f"📊 [최근 5개년 금리역전(Inversion) 구간 요약 (총 {len(df_periods)}개 구간)]")
    print("-" * 75)
    if not df_periods.empty:
        print(df_periods.to_string(index=False))
    else:
        print("해당 기간 동안 금리 역전 구간이 발생하지 않았습니다.")
    print("-" * 75)
    print("📋 최근 5개 영업일 데이터 미리보기:")
    preview_df = df_merged[["DATE", "US_10Y", "US_2Y", "SPREAD", "SPREAD_BP", "is_inverted"]].tail(5)
    print(preview_df.to_string(index=False))
    print("-" * 75)
    print(INDICATOR_BACKGROUND_INFO)
    print("=" * 75)


if __name__ == "__main__":
    analyze_us_treasury_spread()
