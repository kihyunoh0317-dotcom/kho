"""
한국은행 ECOS Open API 기준금리 결정 이력 데이터 수집 스크립트
- 통계표: 722Y001 (1.3.1. 한국은행 기준금리 및 여수신금리)
- 통계항목: 0101000 (한국은행 기준금리)
- 환경변수: .env 파일의 ECOS_API_KEY
- 출력: base_rate_history.csv (기준금리 변경 및 결정 이력)
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

# 기본 설정값
DEFAULT_STAT_CODE = "722Y001"       # 1.3.1. 한국은행 기준금리 및 여수신금리
DEFAULT_ITEM_CODE = "0101000"       # 한국은행 기준금리
DEFAULT_CYCLE = "D"                 # 일별 (D)
DEFAULT_YEARS = 5                   # 최근 5개년
DEFAULT_OUTPUT_CSV = "base_rate_history.csv"


def get_api_key(cli_key: str = None) -> str:
    """
    CLI 인자, .env 파일(스크립트 위치 기준 절대경로), 또는 환경변수에서 ECOS_API_KEY를 로드합니다.
    """
    if cli_key and cli_key.strip():
        return cli_key.strip()

    # 스크립트 위치 기준 .env 파일 경로 지정 로드
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        load_dotenv(override=True)

    api_key = os.getenv("ECOS_API_KEY", "").strip()

    # 직접 .env 파일 파싱 백업 로직
    if not api_key and env_path.exists():
        try:
            for enc in ["utf-8", "utf-8-sig", "cp949"]:
                try:
                    with open(env_path, "r", encoding=enc) as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("ECOS_API_KEY="):
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
        print("=" * 60)
        print("[오류] ECOS_API_KEY를 찾을 수 없습니다.")
        print(f"탐색한 .env 파일 위치: {env_path}")
        print("1. 위 위치의 .env 파일을 열어주세요.")
        print("2. ECOS_API_KEY=발급받은_인증키 형태로 입력 후 저장해주세요.")
        print("   (한국은행 ECOS Open API 사이트: https://ecos.bok.or.kr)")
        print("=" * 60)
        sys.exit(1)

    return api_key


def fetch_daily_base_rates(
    api_key: str,
    start_date: str,
    end_date: str,
    batch_size: int = 1000
) -> pd.DataFrame:
    """
    한국은행 ECOS API를 호출하여 일별 기준금리 데이터를 조회합니다.
    """
    if api_key.lower() == "sample" and batch_size > 10:
        batch_size = 10

    base_url = "https://ecos.bok.or.kr/api/StatisticSearch"
    all_rows = []
    start_req = 1

    print("[정보] ECOS API 한국은행 기준금리 데이터 수집 시작...")
    print(f" - 통계표 코드: {DEFAULT_STAT_CODE}")
    print(f" - 통계항목 코드: {DEFAULT_ITEM_CODE} (한국은행 기준금리)")
    print(f" - 조회 기간: {start_date} ~ {end_date}")

    while True:
        end_req = start_req + batch_size - 1
        url = f"{base_url}/{api_key}/json/kr/{start_req}/{end_req}/{DEFAULT_STAT_CODE}/{DEFAULT_CYCLE}/{start_date}/{end_date}/{DEFAULT_ITEM_CODE}"

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[오류] API 요청 실패: {e}")
            break

        if "StatisticSearch" in data:
            search_data = data["StatisticSearch"]
            total_count = int(search_data.get("list_total_count", 0))
            rows = search_data.get("row", [])

            if not rows:
                break

            all_rows.extend(rows)
            if len(all_rows) >= total_count or len(rows) < batch_size:
                break

            start_req += batch_size
        else:
            if "RESULT" in data:
                print(f"[API 응답] {data['RESULT'].get('MESSAGE')}")
            break

    if not all_rows:
        return pd.DataFrame()

    df_raw = pd.DataFrame(all_rows)
    df = pd.DataFrame()
    df["TIME"] = df_raw["TIME"].astype(str)
    df["BASE_RATE"] = pd.to_numeric(df_raw["DATA_VALUE"], errors="coerce")
    df = df.dropna(subset=["BASE_RATE"]).sort_values("TIME").reset_index(drop=True)
    return df


def extract_decision_history(df_daily: pd.DataFrame) -> pd.DataFrame:
    """
    일별 기준금리 시계열에서 금리 변경(인상/인하) 시점 및 결정 이력을 추출합니다.
    """
    if df_daily.empty:
        return pd.DataFrame()

    history_records = []

    # 1. 시작 시점 기준금리 기록
    first_row = df_daily.iloc[0]
    initial_rate = first_row["BASE_RATE"]
    current_rate = initial_rate

    history_records.append({
        "TIME": first_row["TIME"],
        "PREV_RATE": None,
        "BASE_RATE": initial_rate,
        "CHANGE": 0.0,
        "CHANGE_BP": 0.0,
        "ACTION": "조회시작 기준금리",
        "NOTE": f"조회 시작 시점 기준금리 ({initial_rate:.2f}%)"
    })

    # 2. 금리 변동 시점 추출
    for i in range(1, len(df_daily)):
        row = df_daily.iloc[i]
        rate = row["BASE_RATE"]
        date = row["TIME"]

        if rate != current_rate:
            diff = round(rate - current_rate, 4)
            diff_bp = round(diff * 100, 2)
            prev_rate = current_rate

            if diff > 0:
                action = "인상"
                if abs(diff) >= 0.5:
                    note = f"빅스텝 (+{diff_bp:.0f}bp 인상)"
                else:
                    note = f"베이비스텝 (+{diff_bp:.0f}bp 인상)"
            else:
                action = "인하"
                if abs(diff) >= 0.5:
                    note = f"빅컷 ({diff_bp:.0f}bp 인하)"
                else:
                    note = f"베이비스텝 ({diff_bp:.0f}bp 인하)"

            history_records.append({
                "TIME": date,
                "PREV_RATE": prev_rate,
                "BASE_RATE": rate,
                "CHANGE": diff,
                "CHANGE_BP": diff_bp,
                "ACTION": action,
                "NOTE": note
            })
            current_rate = rate

    df_history = pd.DataFrame(history_records)
    return df_history


def main():
    parser = argparse.ArgumentParser(description="한국은행 기준금리 결정 이력 데이터 수집기")
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="ECOS API 인증키 (미입력 시 .env 파일의 ECOS_API_KEY 사용)"
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
        help="조회 시작일 (YYYYMMDD 형식, 미입력 시 최근 N개년 자동 계산)"
    )
    parser.add_argument(
        "--end",
        type=str,
        default="",
        help="조회 종료일 (YYYYMMDD 형식, 미입력 시 오늘 날짜)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_CSV,
        help=f"저장할 CSV 파일명 (기본값: {DEFAULT_OUTPUT_CSV})"
    )
    args = parser.parse_args()

    # 1. API 키 확인
    api_key = get_api_key(args.api_key)

    # 2. 날짜 계산
    today = datetime.now()
    if not args.end:
        end_date = today.strftime("%Y%m%d")
    else:
        end_date = args.end.replace("-", "")

    if not args.start:
        # 변경 직전 금리를 정확히 파악하기 위해 여유있게 시작
        start_date = (today - timedelta(days=args.years * 365 + 30)).strftime("%Y%m%d")
    else:
        start_date = args.start.replace("-", "")

    # 3. 일별 기준금리 데이터 수집
    df_daily = fetch_daily_base_rates(api_key, start_date, end_date)
    if df_daily.empty:
        print("[경고] 수집된 기준금리 데이터가 없습니다.")
        return

    # 4. 결정/변동 이력 추출
    df_history = extract_decision_history(df_daily)

    # 5. CSV 파일 저장
    output_filename = args.output
    if not os.path.isabs(output_filename):
        output_path = BASE_DIR / output_filename
    else:
        output_path = Path(output_filename)

    df_history.to_csv(output_path, index=False, encoding="utf-8-sig")

    # 6. 통계 및 요약 출력
    hike_count = len(df_history[df_history["ACTION"] == "인상"])
    cut_count = len(df_history[df_history["ACTION"] == "인하"])
    latest_row = df_history.iloc[-1]

    print("\n" + "=" * 70)
    print("🏛️ [한국은행 기준금리 결정 이력 분석 결과]")
    print("=" * 70)
    print(f"📁 저장 파일 위치 : {output_path.resolve()}")
    print(f"📅 전체 조회 기간 : {df_history['TIME'].min()} ~ {df_history['TIME'].max()}")
    print(f"🔢 총 결정 변동수 : 총 {len(df_history) - 1}회 (인상 {hike_count}회, 인하 {cut_count}회)")
    print(f"📌 현재 기준금리   : {latest_row['BASE_RATE']:.2f}% (최근 결정일: {latest_row['TIME']})")
    print("-" * 70)
    print("📋 최근 5개년 기준금리 결정 이력 전체 목록:")
    print("-" * 70)

    # 포맷팅 출력
    display_df = df_history.copy()
    display_df["PREV_RATE"] = display_df["PREV_RATE"].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else "-")
    display_df["BASE_RATE"] = display_df["BASE_RATE"].apply(lambda x: f"{x:.2f}%")
    display_df["CHANGE"] = display_df["CHANGE"].apply(lambda x: f"{x:+.2f}%p" if x != 0 else "-")
    display_df["CHANGE_BP"] = display_df["CHANGE_BP"].apply(lambda x: f"{x:+.0f} bp" if x != 0 else "-")
    
    print(display_df[["TIME", "PREV_RATE", "BASE_RATE", "CHANGE", "CHANGE_BP", "ACTION", "NOTE"]].to_string(index=False))
    print("=" * 70)


if __name__ == "__main__":
    main()
