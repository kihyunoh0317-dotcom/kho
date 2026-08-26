"""
국고채(3년) 및 회사채(3년, AA-) 금리 데이터 병합 및 신용 스프레드 분석 스크립트
- 입력: ecos_ktb_3y.csv, ecos_corp_aa_3y.csv
- 출력: bond_spread_3y.csv
- 계산: 일별 스프레드(회사채 - 국고채), 최근 1년/5년 평균 스프레드 및 평균 대비 비율(%)
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

# Windows 터미널 한글/특수문자 인코딩 안전 설정
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
KTB_FILE = BASE_DIR / "ecos_ktb_3y.csv"
CORP_FILE = BASE_DIR / "ecos_corp_aa_3y.csv"
OUTPUT_FILE = BASE_DIR / "bond_spread_3y.csv"


def calculate_and_save_spread():
    # 1. 파일 존재 여부 확인
    if not KTB_FILE.exists():
        print(f"❌ [오류] {KTB_FILE.name} 파일이 없습니다. 먼저 fetch_ecos.py를 실행해주세요.")
        return
    if not CORP_FILE.exists():
        print(f"❌ [오류] {CORP_FILE.name} 파일이 없습니다. 먼저 fetch_corp_aa_3y.py를 실행해주세요.")
        return

    # 2. CSV 파일 읽기
    df_ktb = pd.read_csv(KTB_FILE)
    df_corp = pd.read_csv(CORP_FILE)

    # 컬럼 정리
    df_ktb = df_ktb[["TIME", "DATA_VALUE"]].rename(columns={"DATA_VALUE": "KTB_3Y"})
    df_corp = df_corp[["TIME", "DATA_VALUE"]].rename(columns={"DATA_VALUE": "CORP_AA_3Y"})

    # 3. 날짜(TIME) 기준 내부 조인(Inner Merge)
    df_merged = pd.merge(df_ktb, df_corp, on="TIME", how="inner")

    # 숫자형 변환 및 정렬
    df_merged["TIME"] = df_merged["TIME"].astype(str)
    df_merged["KTB_3Y"] = pd.to_numeric(df_merged["KTB_3Y"], errors="coerce")
    df_merged["CORP_AA_3Y"] = pd.to_numeric(df_merged["CORP_AA_3Y"], errors="coerce")
    df_merged = df_merged.dropna(subset=["KTB_3Y", "CORP_AA_3Y"]).sort_values(by="TIME").reset_index(drop=True)

    # 4. 스프레드 계산 (회사채 - 국고채)
    df_merged["SPREAD"] = (df_merged["CORP_AA_3Y"] - df_merged["KTB_3Y"]).round(4)
    df_merged["SPREAD_BP"] = (df_merged["SPREAD"] * 100).round(2)  # 1%p = 100bp

    # 5. CSV 파일 저장
    df_merged.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    # 6. 날짜 파싱을 통한 기간별 통계 분석
    df_merged["DATE"] = pd.to_datetime(df_merged["TIME"], format="%Y%m%d")
    latest_row = df_merged.iloc[-1]
    curr_spread = latest_row["SPREAD"]
    curr_bp = latest_row["SPREAD_BP"]
    latest_date = latest_row["DATE"]

    # 최근 1년 데이터 필터링
    one_year_ago = latest_date - timedelta(days=365)
    df_1y = df_merged[df_merged["DATE"] >= one_year_ago]
    avg_1y = df_1y["SPREAD"].mean()
    avg_1y_bp = df_1y["SPREAD_BP"].mean()

    # 최근 5년 데이터
    five_years_ago = latest_date - timedelta(days=5 * 365)
    df_5y = df_merged[df_merged["DATE"] >= five_years_ago]
    avg_5y = df_5y["SPREAD"].mean()
    avg_5y_bp = df_5y["SPREAD_BP"].mean()

    # 현재 스프레드의 평균 대비 비율(%) 및 차이
    ratio_1y = (curr_spread / avg_1y) * 100
    diff_1y_pct = curr_spread - avg_1y
    diff_1y_bp = curr_bp - avg_1y_bp

    ratio_5y = (curr_spread / avg_5y) * 100
    diff_5y_pct = curr_spread - avg_5y
    diff_5y_bp = curr_bp - avg_5y_bp

    # 7. 결과 출력
    print("=" * 68)
    print("📊 [국고채 3년 vs 회사채 3년(AA-) 신용 스프레드 분석 결과]")
    print("=" * 68)
    print(f"📁 병합 파일 저장 완료 : {OUTPUT_FILE.resolve()}")
    print(f"📈 총 데이터 건수       : {len(df_merged):,}건")
    print(f"📅 전체 데이터 기간     : {df_merged['TIME'].min()} ~ {df_merged['TIME'].max()}")
    print("-" * 68)
    print(f"📌 [현재 기준일: {latest_row['TIME']}]")
    print(f"   • 국고채(3년) 금리     : {latest_row['KTB_3Y']:.3f}%")
    print(f"   • 회사채(3년, AA-) 금리: {latest_row['CORP_AA_3Y']:.3f}%")
    print(f"   • 현재 스프레드        : {curr_spread:.4f}%p ({curr_bp:.2f} bp)")
    print("-" * 68)
    print("📊 [기간별 평균 스프레드 및 현재값 비교]")
    print(f"   1) 최근 1년 평균 스프레드 : {avg_1y:.4f}%p  ({avg_1y_bp:.2f} bp)  [245영업일]")
    print(f"      👉 현재 스프레드는 1년 평균 대비: {ratio_1y:.2f}%  (차이: {diff_1y_pct:+.4f}%p / {diff_1y_bp:+.2f} bp)")
    print()
    print(f"   2) 최근 5년 평균 스프레드 : {avg_5y:.4f}%p  ({avg_5y_bp:.2f} bp)  [1,226영업일]")
    print(f"      👉 현재 스프레드는 5년 평균 대비: {ratio_5y:.2f}%  (차이: {diff_5y_pct:+.4f}%p / {diff_5y_bp:+.2f} bp)")
    print("-" * 68)
    print("📊 [최근 5년 스프레드 극값]")
    print(f"   • 최저 스프레드 : {df_5y['SPREAD'].min():.3f}%p ({df_5y['SPREAD_BP'].min():.1f} bp) (일자: {df_5y.loc[df_5y['SPREAD'].idxmin(), 'TIME']})")
    print(f"   • 최고 스프레드 : {df_5y['SPREAD'].max():.3f}%p ({df_5y['SPREAD_BP'].max():.1f} bp) (일자: {df_5y.loc[df_5y['SPREAD'].idxmax(), 'TIME']})")
    print("-" * 68)
    print("📋 최근 5개 영업일 데이터 미리보기:")
    preview_df = df_merged[["TIME", "KTB_3Y", "CORP_AA_3Y", "SPREAD", "SPREAD_BP"]].tail(5)
    print(preview_df.to_string(index=False))
    print("=" * 68)


if __name__ == "__main__":
    calculate_and_save_spread()
