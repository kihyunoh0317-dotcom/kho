"""
원/달러 환율(usd_krw.csv) 기반 환헤지 vs 환오픈 손익 비교 시나리오 분석기
- 데이터: usd_krw.csv (최신 환율 로드)
- 비교: 환헤지 미실시(환오픈) vs 환헤지 실시(헤지비용 연 1.5% 가정)
- 시나리오: 환율 변동 (+10%, +5%, 현재 0%, BEP -1.5%, -5%, -10%)
- 출력: fx_hedge_scenario.csv 및 상세 손익 비교표
"""

import os
import sys
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

# Windows 터미널 한글/특수문자 인코딩 안전 설정
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
USD_KRW_FILE = BASE_DIR / "usd_krw.csv"
OUTPUT_CSV = BASE_DIR / "fx_hedge_scenario.csv"

# 기본 가정값
DEFAULT_HEDGE_COST_PCT = 1.5      # 연간 환헤지 비용 (1.5%)
DEFAULT_ASSET_YIELD_PCT = 4.5     # 달러 자산(예: 미국 국채) 연 수익률 (4.5%)
DEFAULT_PRINCIPAL_KRW = 100_000_000  # 투자 원금 (1억 원)


def load_latest_exchange_rate():
    """
    usd_krw.csv 파일에서 최신 환율 및 과거 통계를 로드합니다.
    """
    if not USD_KRW_FILE.exists():
        print(f"❌ [오류] {USD_KRW_FILE.name} 파일이 없습니다. 먼저 fetch_usd_krw.py를 실행해주세요.")
        sys.exit(1)

    df = pd.read_csv(USD_KRW_FILE)
    df["TIME"] = df["TIME"].astype(str)
    df["DATA_VALUE"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
    df = df.dropna(subset=["DATA_VALUE"]).sort_values("TIME").reset_index(drop=True)

    latest_row = df.iloc[-1]
    latest_date = latest_row["TIME"]
    latest_rate = float(latest_row["DATA_VALUE"])

    # 최근 1년/5년 통계
    count_total = len(df)
    rate_5y_min = df["DATA_VALUE"].min()
    rate_5y_max = df["DATA_VALUE"].max()
    rate_5y_avg = df["DATA_VALUE"].mean()

    df_1y = df.tail(245) if count_total >= 245 else df
    rate_1y_min = df_1y["DATA_VALUE"].min()
    rate_1y_max = df_1y["DATA_VALUE"].max()
    rate_1y_avg = df_1y["DATA_VALUE"].mean()

    stats = {
        "latest_date": latest_date,
        "latest_rate": latest_rate,
        "total_records": count_total,
        "1y_avg": rate_1y_avg,
        "1y_min": rate_1y_min,
        "1y_max": rate_1y_max,
        "5y_avg": rate_5y_avg,
        "5y_min": rate_5y_min,
        "5y_max": rate_5y_max,
    }
    return stats


def calculate_scenarios(
    current_rate: float,
    hedge_cost_pct: float = DEFAULT_HEDGE_COST_PCT,
    asset_yield_pct: float = DEFAULT_ASSET_YIELD_PCT,
    principal_krw: float = DEFAULT_PRINCIPAL_KRW
) -> pd.DataFrame:
    """
    시나리오별(현재, +5%, -5% 등) 환오픈 vs 환헤지 손익을 계산합니다.
    """
    # 분석 시나리오 목록 (환율 변동률 %)
    # 손익분기점(BEP): 환헤지 비용이 -1.5%이므로 환율이 -1.5% 하락할 때 양 전략의 손익이 일치
    bep_pct = -hedge_cost_pct
    scenarios = [
        {"name": "환율 +10% 급등 (원화 약세)", "change_pct": 10.0},
        {"name": "환율 +5% 상승  (원화 약세)", "change_pct": 5.0},
        {"name": "현재 환율 유지 (변동 0%)", "change_pct": 0.0},
        {"name": f"손익분기점 BEP ({bep_pct:+.1f}%)", "change_pct": bep_pct},
        {"name": "환율 -5% 하락  (원화 강세)", "change_pct": -5.0},
        {"name": "환율 -10% 급락 (원화 강세)", "change_pct": -10.0},
    ]

    r_asset = asset_yield_pct / 100.0
    r_hedge_cost = hedge_cost_pct / 100.0
    initial_usd = principal_krw / current_rate

    rows = []
    for sc in scenarios:
        change_pct = sc["change_pct"]
        r_fx = change_pct / 100.0
        scenario_rate = current_rate * (1.0 + r_fx)

        # 1. 순수 환수익률 (자산수익 제외)
        unhedged_fx_ret = r_fx * 100.0
        hedged_fx_ret = -hedge_cost_pct

        # 2. 총 투자 수익률 (달러자산수익률 + 환효과/헤지비용)
        # 환오픈 총수익률 = (1 + 자산수익률) * (1 + 환변동률) - 1
        unhedged_total_ret = ((1.0 + r_asset) * (1.0 + r_fx) - 1.0) * 100.0
        # 환헤지 총수익률 = 자산수익률 - 헤지비용
        hedged_total_ret = (r_asset - r_hedge_cost) * 100.0

        # 3. 원화 환산 최종 평가액 및 손익금액 (원)
        # 환오픈: 만기 달러(원금*(1+자산수익률)) * 만기 환율
        unhedged_final_krw = (initial_usd * (1.0 + r_asset)) * scenario_rate
        unhedged_pnl_krw = unhedged_final_krw - principal_krw

        # 환헤지: 원화원금 * (1 + 환헤지 총수익률)
        hedged_final_krw = principal_krw * (1.0 + (hedged_total_ret / 100.0))
        hedged_pnl_krw = hedged_final_krw - principal_krw

        # 4. 차이 및 유리한 전략
        ret_diff = unhedged_total_ret - hedged_total_ret
        pnl_diff_krw = unhedged_pnl_krw - hedged_pnl_krw

        if abs(ret_diff) < 1e-4:
            advantage = "동일 (BEP)"
        elif ret_diff > 0:
            advantage = "환오픈 유리 (+환차익)"
        else:
            advantage = "환헤지 유리 (+방어효과)"

        rows.append({
            "시나리오": sc["name"],
            "환율변동률(%)": change_pct,
            "시나리오환율(원)": round(scenario_rate, 2),
            "환오픈_순수환수익률(%)": round(unhedged_fx_ret, 2),
            "환헤지_순수환수익률(%)": round(hedged_fx_ret, 2),
            "환오픈_총수익률(%)": round(unhedged_total_ret, 2),
            "환헤지_총수익률(%)": round(hedged_total_ret, 2),
            "수익률차이(%p)": round(ret_diff, 2),
            "환오픈_최종금액(원)": int(round(unhedged_final_krw)),
            "환오픈_손익(원)": int(round(unhedged_pnl_krw)),
            "환헤지_최종금액(원)": int(round(hedged_final_krw)),
            "환헤지_손익(원)": int(round(hedged_pnl_krw)),
            "손익차이(원)": int(round(pnl_diff_krw)),
            "우위전략": advantage
        })

    df_res = pd.DataFrame(rows)
    return df_res


def main():
    parser = argparse.ArgumentParser(description="환헤지 vs 환오픈 시나리오별 손익 비교 계산기")
    parser.add_argument(
        "--hedge-cost",
        type=float,
        default=DEFAULT_HEDGE_COST_PCT,
        help=f"연간 환헤지 비용 (%%, 기본값: {DEFAULT_HEDGE_COST_PCT}%%)"
    )
    parser.add_argument(
        "--asset-yield",
        type=float,
        default=DEFAULT_ASSET_YIELD_PCT,
        help=f"달러 자산(미국 국채 등) 기본 연 수익률 (%%, 기본값: {DEFAULT_ASSET_YIELD_PCT}%%)"
    )
    parser.add_argument(
        "--principal",
        type=float,
        default=DEFAULT_PRINCIPAL_KRW,
        help=f"투자 원금 (원 단위, 기본값: {DEFAULT_PRINCIPAL_KRW:,.0f}원)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUT_CSV),
        help=f"결과 CSV 저장 파일명 (기본값: {OUTPUT_CSV.name})"
    )
    args = parser.parse_args()

    # 1. 최신 환율 로드
    stats = load_latest_exchange_rate()
    current_rate = stats["latest_rate"]

    # 2. 시나리오 계산
    df_result = calculate_scenarios(
        current_rate=current_rate,
        hedge_cost_pct=args.hedge_cost,
        asset_yield_pct=args.asset_yield,
        principal_krw=args.principal
    )

    # 3. CSV 파일 저장
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path
    df_result.to_csv(output_path, index=False, encoding="utf-8-sig")

    # 4. 콘솔 상세 출력
    print("=" * 85)
    print("💵 [원/달러 환율 기반 환헤지 vs 환오픈 시나리오 손익 분석]")
    print("=" * 85)
    print(f"📌 [기준 환율 정보 (최근 영업일: {stats['latest_date']})]")
    print(f"   • 현재 원/달러 기준환율 : {current_rate:,.2f} 원")
    print(f"   • 최근 1년 환율 범위   : {stats['1y_min']:,.1f} ~ {stats['1y_max']:,.1f} 원 (평균: {stats['1y_avg']:,.1f} 원)")
    print(f"   • 최근 5년 환율 범위   : {stats['5y_min']:,.1f} ~ {stats['5y_max']:,.1f} 원 (평균: {stats['5y_avg']:,.1f} 원)")
    print("-" * 85)
    print(f"⚙️ [시뮬레이션 기본 조건]")
    print(f"   • 투자 원금             : {args.principal:,.0f} 원 (${args.principal / current_rate:,.2f})")
    print(f"   • 달러 자산 연 수익률   : {args.asset_yield:.2f}% (예: 미국 국채 쿠폰수익률 등)")
    print(f"   • 연간 환헤지 비용     : {args.hedge_cost:.2f}% (프리미엄/스왑포인트 역전 등)")
    print(f"   • 손익분기 환율변동률   : {-args.hedge_cost:+.2f}% (환율이 {current_rate * (1 - args.hedge_cost/100):,.2f}원 이하로 하락 시 환헤지 유리)")
    print("-" * 85)
    print("📊 [1. 시나리오별 총 수익률 비교 (%)]")
    print("-" * 85)
    
    summary_cols = ["시나리오", "시나리오환율(원)", "환오픈_총수익률(%)", "환헤지_총수익률(%)", "수익률차이(%p)", "우위전략"]
    print(df_result[summary_cols].to_string(index=False))

    print("\n" + "-" * 85)
    print(f"💰 [2. 투자원금({args.principal/10000:,.0f}만원) 기준 최종 평가금액 및 손익 비교]")
    print("-" * 85)

    pnl_cols = ["시나리오", "환오픈_최종금액(원)", "환오픈_손익(원)", "환헤지_최종금액(원)", "환헤지_손익(원)", "손익차이(원)"]
    df_pnl_display = df_result[pnl_cols].copy()
    for col in pnl_cols[1:]:
        df_pnl_display[col] = df_pnl_display[col].apply(lambda x: f"{x:+,d}원" if "손익" in col else f"{x:,d}원")
    print(df_pnl_display.to_string(index=False))

    print("\n" + "=" * 85)
    print(f"📁 결과 CSV 파일 저장 완료: {output_path.resolve()}")
    print("=" * 85)


if __name__ == "__main__":
    main()
