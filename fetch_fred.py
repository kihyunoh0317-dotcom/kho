"""
미국 연방준비은행 FRED API 미국 국채(10년물 / 2년물) 데이터 수집 스크립트
- 시리즈: DGS10 (미국 국채 10년물), DGS2 (미국 국채 2년물)
- 환경변수: .env 파일의 FRED_API_KEY
- 출력: us_treasury_10y.csv, us_treasury_2y.csv
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import requests
import pandas as pd
from dotenv import load_dotenv

# Windows 터미널 한글/특수문자 인코딩 안전 설정
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 프로젝트 기본 경로 (스크립트 파일 기준 절대경로)
BASE_DIR = Path(__file__).resolve().parent

# FRED API 기본 설정
FRED_API_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_YEARS = 5

SERIES_CONFIG = {
    "DGS10": {
        "name": "미국 국채(10년물)",
        "output_csv": "us_treasury_10y.csv"
    },
    "DGS2": {
        "name": "미국 국채(2년물)",
        "output_csv": "us_treasury_2y.csv"
    }
}


def get_api_key(cli_key: str = None) -> str:
    """
    CLI 인자, .env 파일(스크립트 위치 기준 절대경로), 또는 환경변수에서 FRED_API_KEY를 로드합니다.
    """
    if cli_key and cli_key.strip():
        return cli_key.strip()

    # 스크립트 위치 기준 .env 파일 경로 지정 로드
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        load_dotenv(override=True)

    api_key = os.getenv("FRED_API_KEY", "").strip()

    # 직접 .env 파일 파싱 백업 로직
    if not api_key and env_path.exists():
        try:
            for enc in ["utf-8", "utf-8-sig", "cp949"]:
                try:
                    with open(env_path, "r", encoding=enc) as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("FRED_API_KEY="):
                                val = line.split("=", 1)[1].strip().strip("'\"")
                                if val:
                                    api_key = val
                                    break
                    if api_key:
                        break
                except UnicodeDecodeError:
                    continue
        except Exception:
            pass

    if not api_key:
        print("=" * 65)
        print("[오류] FRED_API_KEY가 설정되지 않았습니다.")
        print(f"탐색한 .env 파일 위치: {env_path}")
        print("1. https://fred.stlouisfed.org/docs/api/api_key.html 에서 무료 API 키를 발급받으세요.")
        print("2. .env 파일을 열어 FRED_API_KEY=발급받은키 형식으로 입력 후 저장해주세요.")
        print("=" * 65)
        sys.exit(1)

    return api_key


def fetch_fred_series(
    api_key: str,
    series_id: str,
    start_date: str,
    end_date: str
) -> pd.DataFrame:
    """
    FRED API로부터 특정 series_id의 시계열 데이터를 조회하여 정제된 DataFrame으로 반환합니다.
    """
    info = SERIES_CONFIG.get(series_id, {"name": series_id})
    series_name = info["name"]

    print(f"\n[정보] FRED API {series_name} ({series_id}) 수집 시작...")
    print(f" - 조회 기간: {start_date} ~ {end_date}")

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date,
        "sort_order": "asc"
    }

    try:
        response = requests.get(FRED_API_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"[네트워크 오류] API 요청 실패: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"[JSON 파싱 오류] 응답 데이터 처리 실패: {e}")
        return pd.DataFrame()

    if "error_message" in data:
        print(f"[API 오류 응답] {data['error_message']}")
        return pd.DataFrame()

    observations = data.get("observations", [])
    if not observations:
        print("[알림] 조회된 데이터가 없습니다.")
        return pd.DataFrame()

    # DataFrame 생성 및 정제
    df_raw = pd.DataFrame(observations)

    df = pd.DataFrame()
    # 날짜 컬럼: YYYYMMDD 및 YYYY-MM-DD 호환
    df["TIME"] = df_raw["date"].str.replace("-", "")
    df["DATE"] = df_raw["date"]
    
    # 공휴일 등으로 값이 '.' 인 경우 NaN 처리 후 유효한 영업일 데이터만 추출
    df["DATA_VALUE"] = pd.to_numeric(df_raw["value"], errors="coerce")
    df["SERIES_ID"] = series_id
    df["SERIES_NAME"] = series_name
    df["UNIT"] = "%"

    # 유효 데이터만 필터링 및 날짜 오름차순 정렬
    df = df.dropna(subset=["DATA_VALUE"]).sort_values("TIME").reset_index(drop=True)

    print(f"   진행: 총 {len(df):,}개 영업일 데이터 수집 완료")
    return df


def main():
    parser = argparse.ArgumentParser(description="미국 연방준비은행 FRED API 국채 금리 데이터 수집기")
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="FRED API 인증키 (미입력 시 .env 파일의 FRED_API_KEY 사용)"
    )
    parser.add_argument(
        "--years",
        type=int,
        default=DEFAULT_YEARS,
        help=f"수집할 최근 기간(년 단위, 기본값: {DEFAULT_YEARS})"
    )
    parser.add_argument(
        "--start",
        type=str,
        default="",
        help="조회 시작일 (YYYY-MM-DD 또는 YYYYMMDD 형식, 미입력 시 최근 N개년 자동 계산)"
    )
    parser.add_argument(
        "--end",
        type=str,
        default="",
        help="조회 종료일 (YYYY-MM-DD 또는 YYYYMMDD 형식, 미입력 시 오늘 날짜)"
    )
    parser.add_argument(
        "--series",
        type=str,
        default="ALL",
        choices=["ALL", "DGS10", "DGS2"],
        help="수집할 시리즈 ID (기본값: ALL - 10년물 및 2년물 모두 수집)"
    )
    args = parser.parse_args()

    # 1. API 키 확인
    api_key = get_api_key(args.api_key)

    # 2. 날짜 범위 계산 (YYYY-MM-DD 형식)
    today = datetime.now()
    if not args.end:
        end_date = today.strftime("%Y-%m-%d")
    else:
        # 형식 정리 (YYYYMMDD -> YYYY-MM-DD)
        clean_end = args.end.replace("-", "")
        end_date = f"{clean_end[:4]}-{clean_end[4:6]}-{clean_end[6:]}" if len(clean_end) == 8 else args.end

    if not args.start:
        start_date = (today - timedelta(days=args.years * 365)).strftime("%Y-%m-%d")
    else:
        clean_start = args.start.replace("-", "")
        start_date = f"{clean_start[:4]}-{clean_start[4:6]}-{clean_start[6:]}" if len(clean_start) == 8 else args.start

    target_series = ["DGS10", "DGS2"] if args.series == "ALL" else [args.series]
    saved_dfs = {}

    print("=" * 65)
    print("🌐 [미국 연방준비은행 FRED API 국채 데이터 수집기]")
    print("=" * 65)

    # 3. 각 시리즈 데이터 수집 및 개별 CSV 저장
    for s_id in target_series:
        df = fetch_fred_series(
            api_key=api_key,
            series_id=s_id,
            start_date=start_date,
            end_date=end_date
        )

        if df.empty:
            print(f"[경고] {s_id} 데이터가 비어있어 저장을 건너뜁니다.")
            continue

        output_filename = SERIES_CONFIG[s_id]["output_csv"]
        output_path = BASE_DIR / output_filename

        # CSV 파일 저장 (날짜: TIME, 값: DATA_VALUE 중심 구성, utf-8-sig)
        save_cols = ["TIME", "DATE", "DATA_VALUE", "SERIES_ID", "SERIES_NAME", "UNIT"]
        df[save_cols].to_csv(output_path, index=False, encoding="utf-8-sig")
        saved_dfs[s_id] = df

        print(f"✅ [{s_id}] 저장 완료: {output_path.resolve()}")
        print(f"   • 데이터 건수: {len(df):,}건")
        print(f"   • 데이터 기간: {df['DATE'].min()} ~ {df['DATE'].max()}")
        print(f"   • 최신 금리: {df.iloc[-1]['DATA_VALUE']:.2f}% (기준일: {df.iloc[-1]['DATE']})")

    # 4. 장단기 금리차 (10Y - 2Y Spread) 보너스 요약 분석
    if "DGS10" in saved_dfs and "DGS2" in saved_dfs:
        df_10 = saved_dfs["DGS10"][["DATE", "DATA_VALUE"]].rename(columns={"DATA_VALUE": "US_10Y"})
        df_2 = saved_dfs["DGS2"][["DATE", "DATA_VALUE"]].rename(columns={"DATA_VALUE": "US_2Y"})
        df_spread = pd.merge(df_10, df_2, on="DATE", how="inner")
        df_spread["SPREAD"] = (df_spread["US_10Y"] - df_spread["US_2Y"]).round(4)
        df_spread["SPREAD_BP"] = (df_spread["SPREAD"] * 100).round(2)

        latest_sp = df_spread.iloc[-1]
        print("-" * 65)
        print("📊 [미국 국채 10Y-2Y 장단기 금리차(Yield Curve Spread) 현황]")
        print(f"   • 최신 기준일: {latest_sp['DATE']}")
        print(f"   • 미국 10년물 금리 : {latest_sp['US_10Y']:.2f}%")
        print(f"   • 미국 2년물 금리  : {latest_sp['US_2Y']:.2f}%")
        status = "정상 스프레드 (10Y > 2Y)" if latest_sp['SPREAD'] >= 0 else "🚨 금리 역전 현상 (Inversion: 2Y > 10Y)"
        print(f"   • 장단기 금리차    : {latest_sp['SPREAD']:+.2f}%p ({latest_sp['SPREAD_BP']:+.1f} bp) [{status}]")

    print("=" * 65)


if __name__ == "__main__":
    main()
