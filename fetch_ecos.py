"""
한국은행 ECOS Open API 데이터 수집 스크립트
- 통계표: 817Y002 (시장금리(일별))
- 통계항목: 010200000 (국고채(3년))
- 환경변수: .env 파일의 ECOS_API_KEY
- 출력: 날짜(TIME), 값(DATA_VALUE) 컬럼을 가진 CSV 파일
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
DEFAULT_STAT_CODE = "817Y002"       # 1.3.2.1. 시장금리(일별)
DEFAULT_ITEM_CODE = "010200000"     # 국고채(3년)
DEFAULT_CYCLE = "D"                 # 일별 (D)
DEFAULT_YEARS = 5                   # 최근 5개년
DEFAULT_OUTPUT_CSV = "ecos_ktb_3y.csv"


def get_api_key(cli_key: str = None) -> str:
    """
    CLI 인자, .env 파일(스크립트 위치 기준 절대경로), 또는 환경변수에서 ECOS_API_KEY를 로드합니다.
    """
    # 1. CLI 직접 전달 인자 확인
    if cli_key and cli_key.strip():
        return cli_key.strip()

    # 2. 스크립트 위치 기준 .env 파일 경로 지정 로드 (어느 폴더에서 실행해도 동작)
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        load_dotenv(override=True)

    api_key = os.getenv("ECOS_API_KEY", "").strip()

    # 3. 직접 .env 파일 파싱 백업 로직 (인코딩/라이브러리 예외 방지)
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

    # 4. 키 누락 시 사용자 안내 출력
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


def fetch_ecos_data(
    api_key: str,
    stat_code: str = DEFAULT_STAT_CODE,
    item_code: str = DEFAULT_ITEM_CODE,
    cycle: str = DEFAULT_CYCLE,
    start_date: str = "",
    end_date: str = "",
    batch_size: int = 1000
) -> pd.DataFrame:
    """
    한국은행 ECOS API를 호출하여 데이터를 조회하고 DataFrame으로 반환합니다.
    데이터 건수가 많은 경우 자동 페이징(Pagination) 처리를 수행합니다.
    """
    # sample 키는 1회 최대 10건 제한
    if api_key.lower() == "sample" and batch_size > 10:
        batch_size = 10

    base_url = "https://ecos.bok.or.kr/api/StatisticSearch"
    all_rows = []
    start_req = 1

    print("[정보] ECOS API 데이터 수집 시작...")
    print(f" - 통계표 코드: {stat_code}")
    print(f" - 통계항목 코드: {item_code} (국고채 3년)")
    print(f" - 조회 주기: {cycle}")
    print(f" - 조회 기간: {start_date} ~ {end_date}")

    while True:
        end_req = start_req + batch_size - 1
        # ECOS API URL 구조: .../StatisticSearch/{KEY}/json/kr/{START}/{END}/{STAT_CODE}/{CYCLE}/{START_DATE}/{END_DATE}/{ITEM_CODE}
        url = f"{base_url}/{api_key}/json/kr/{start_req}/{end_req}/{stat_code}/{cycle}/{start_date}/{end_date}/{item_code}"

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"[네트워크 오류] API 요청 실패: {e}")
            break
        except Exception as e:
            print(f"[JSON 파싱 오류] 응답 데이터 처리 실패: {e}")
            break

        # API 응답 결과 확인
        if "StatisticSearch" in data:
            search_data = data["StatisticSearch"]
            total_count = int(search_data.get("list_total_count", 0))
            rows = search_data.get("row", [])

            if not rows:
                print("[알림] 조회된 데이터가 없습니다.")
                break

            all_rows.extend(rows)
            print(f"   진행: {len(all_rows)} / {total_count} 건 수집 완료")

            # 모든 데이터를 수집했거나 다음 데이터가 없으면 종료
            if len(all_rows) >= total_count or len(rows) < batch_size:
                break

            start_req += batch_size

        elif "RESULT" in data:
            error_code = data["RESULT"].get("CODE")
            error_msg = data["RESULT"].get("MESSAGE")
            print(f"[API 응답] 코드: {error_code}, 메시지: {error_msg}")
            
            # 검색 결과 없음 (INFO-200)
            if error_code == "INFO-200":
                print("[알림] 해당 조건에 일치하는 데이터가 없습니다.")
            break
        else:
            print(f"[알림] 알 수 없는 응답 형식: {data}")
            break

    if not all_rows:
        return pd.DataFrame()

    # DataFrame 생성 및 정제
    df_raw = pd.DataFrame(all_rows)

    # 필요한 컬럼 추출 및 정렬 (날짜, 값)
    # TIME: 날짜, DATA_VALUE: 금리 값
    df = pd.DataFrame()
    df["TIME"] = df_raw["TIME"]
    df["DATA_VALUE"] = pd.to_numeric(df_raw["DATA_VALUE"], errors="coerce")
    
    # 추가 메타 정보 포함
    if "ITEM_NAME1" in df_raw.columns:
        df["ITEM_NAME"] = df_raw["ITEM_NAME1"]
    if "UNIT_NAME" in df_raw.columns:
        df["UNIT"] = df_raw["UNIT_NAME"]

    # 날짜 기준 오름차순 정렬
    df = df.sort_values(by="TIME").reset_index(drop=True)

    return df


def main():
    parser = argparse.ArgumentParser(description="한국은행 ECOS API 국고채(3년) 데이터 수집기")
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
    parser.add_argument(
        "--item-code",
        type=str,
        default=DEFAULT_ITEM_CODE,
        help=f"통계항목 코드 (기본값: {DEFAULT_ITEM_CODE} - 국고채 3년)"
    )
    args = parser.parse_args()

    # 1. API 키 확인
    api_key = get_api_key(args.api_key)

    # 2. 날짜 범위 계산 (기본 최근 5개년)
    today = datetime.now()
    if not args.end:
        end_date = today.strftime("%Y%m%d")
    else:
        end_date = args.end.replace("-", "")

    if not args.start:
        start_date = (today - timedelta(days=args.years * 365)).strftime("%Y%m%d")
    else:
        start_date = args.start.replace("-", "")

    # 3. 데이터 조회
    df = fetch_ecos_data(
        api_key=api_key,
        stat_code=DEFAULT_STAT_CODE,
        item_code=args.item_code,
        cycle=DEFAULT_CYCLE,
        start_date=start_date,
        end_date=end_date
    )

    if df.empty:
        print("[경고] 저장할 데이터가 없습니다.")
        return

    # 4. CSV 파일 저장 (프로젝트 디렉토리 기준 상대/절대경로 처리, utf-8-sig)
    output_filename = args.output
    if not os.path.isabs(output_filename):
        output_path = BASE_DIR / output_filename
    else:
        output_path = Path(output_filename)

    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 60)
    print(f"[성공] 데이터 저장 완료: {output_path.resolve()}")
    print(f"[요약] 총 데이터 건수: {len(df):,}건")
    print(f"[기간] {df['TIME'].min()} ~ {df['TIME'].max()}")
    print("-" * 60)
    print("최근 5개 데이터 미리보기:")
    print(df.tail(5).to_string(index=False))
    print("=" * 60)


if __name__ == "__main__":
    main()
