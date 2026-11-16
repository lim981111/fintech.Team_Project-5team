import json
import os
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

KEY = os.getenv("DATA_API_KEY")

# 금융상품한눈에 오픈API
# 실제 호출로 확인된 주소: GET, 응답은 XML(euc-kr 인코딩).
# (공식 예제 소스의 fss.or.kr 주소는 HTML 페이지가 돌아와서 쓸 수 없다)
BASE = "http://finlife.fss.or.kr/finlifeapi"

# 상품 종류 → (한글 이름, 엔드포인트, 조회할 권역 코드들)
# 권역 코드: 020000 은행 / 030200 여신전문 / 030300 저축은행 / 050000 보험 / 060000 금융투자
KINDS = {
    "deposit": ("정기예금", "depositProductsSearch", ["020000", "030300"]),
    "saving": ("적금", "savingProductsSearch", ["020000", "030300"]),
    # 아래는 필요해지면 주석을 풀어서 사용
    # "annuity":  ("연금저축", "annuitySavingProductsSearch", ["020000", "050000", "060000"]),
    # "rent":     ("전세자금대출", "rentHouseLoanProductsSearch", ["020000", "030200", "030300"]),
    # "mortgage": ("주택담보대출", "mortgageLoanProductsSearch", ["020000", "030200", "030300"]),
    # "credit":   ("개인신용대출", "creditLoanProductsSearch", ["020000", "030200", "030300"]),
}

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "finlife.db")
REQUEST_DELAY = 2     # 호출 사이 대기(초)
MAX_PAGES = 50          # 무한 반복 방지용 안전장치


# ---------------------------------------------------------------
# 1. API 호출
# ---------------------------------------------------------------
def to_dict(elem):
    """XML 요소(<baseinfo> 또는 <option>)를 {태그: 값} dict로 변환"""
    return {c.tag: (c.text or "").strip() for c in elem}


def parse_xml(content):
    """응답 바이트를 XML 요소로 변환.

    응답이 euc-kr인데 파이썬 XML 파서는 멀티바이트 인코딩을 못 읽어서,
    직접 디코딩하고 맨 앞의 <?xml ... encoding="euc-kr"?> 선언은 떼어낸다.
    """
    text = content.decode("cp949", errors="replace")     # cp949 = euc-kr의 확장판
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    return ET.fromstring(text)


def call(endpoint, group_no, page):
    """API 한 번 호출. 성공하면 XML 루트 요소, 실패하면 None."""
    url = f"{BASE}/{endpoint}.xml"
    params = {"auth": KEY, "topFinGrpNo": group_no, "pageNo": page}
    try:
        res = requests.get(url, params=params, timeout=15)
        res.raise_for_status()
        root = parse_xml(res.content)
    except requests.exceptions.SSLError:
        print("  SSL 인증서 오류 (사이트 인증서 문제일 수 있음)")
        return None
    except ET.ParseError:
        print("  XML 파싱 실패 (인증키/주소 오류일 수 있음)")
        return None
    except requests.RequestException as e:
        print(f"  호출 실패: {type(e).__name__}")      # URL에 키가 있어 메시지는 출력 안 함
        return None

    # 상품이 없으면 오류 응답으로 보고 내용을 출력 (오류 XML의 정확한 모양은 미확인)
    if root.find(".//product") is None and root.findtext(".//max_page_no") is None:
        print("  상품 없음/오류 응답:", root.findtext(".//err_cd"), root.findtext(".//err_msg"))
        return None
    return root


def fetch_group(endpoint, group_no):
    """한 권역의 모든 페이지를 받아 [(기본정보 dict, [금리옵션 dict들]), ...] 로 반환."""
    products = []
    page = 1
    while page <= MAX_PAGES:
        root = call(endpoint, group_no, page)
        if root is None:
            break

        count = 0
        for prod in root.iter("product"):
            base = to_dict(prod.find("baseinfo"))
            opts = [to_dict(o) for o in prod.findall("./options/option")]
            products.append((base, opts))
            count += 1

        max_page = int(root.findtext(".//max_page_no") or 1)
        print(f"  page {page}/{max_page}: 상품 {count}건")
        if page >= max_page:
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    return products


# ---------------------------------------------------------------
# 2. DB (SQLite)
# ---------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS finlife_products (
            kind         TEXT NOT NULL,      -- deposit / saving ...
            fin_prdt_cd  TEXT NOT NULL,      -- 상품 코드
            group_no     TEXT,               -- 권역 코드
            fin_co_no    TEXT,               -- 금융회사 코드
            kor_co_nm    TEXT,               -- 금융회사명
            fin_prdt_nm  TEXT,               -- 상품명
            dcls_month   TEXT,               -- 공시 월 (YYYYMM)
            base_json    TEXT,               -- 기본정보 전체(JSON 문자열)
            options_json TEXT,               -- 금리/기간 옵션 전체(JSON 문자열)
            collected_at TEXT,               -- 수집 시각
            PRIMARY KEY (kind, fin_prdt_cd)
        )
        """
    )
    conn.commit()
    return conn


def save_products(conn, kind, group_no, products):
    """상품을 저장한다. 이미 있으면 최신 값으로 덮어쓴다."""
    now = datetime.now().isoformat(timespec="seconds")
    for base, opts in products:
        conn.execute(
            """
            INSERT INTO finlife_products
                (kind, fin_prdt_cd, group_no, fin_co_no, kor_co_nm, fin_prdt_nm,
                 dcls_month, base_json, options_json, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind, fin_prdt_cd) DO UPDATE SET
                group_no     = excluded.group_no,
                fin_co_no    = excluded.fin_co_no,
                kor_co_nm    = excluded.kor_co_nm,
                fin_prdt_nm  = excluded.fin_prdt_nm,
                dcls_month   = excluded.dcls_month,
                base_json    = excluded.base_json,
                options_json = excluded.options_json,
                collected_at = excluded.collected_at
            """,
            (
                kind, base["fin_prdt_cd"], group_no,
                base.get("fin_co_no"), base.get("kor_co_nm"), base.get("fin_prdt_nm"),
                base.get("dcls_month"),
                json.dumps(base, ensure_ascii=False),
                json.dumps(opts, ensure_ascii=False),
                now,
            ),
        )
    conn.commit()


def print_summary(conn):
    print("--- 현재 상태 ---")
    for kind, cnt in conn.execute(
        "SELECT kind, COUNT(*) FROM finlife_products GROUP BY kind"
    ):
        print(f"  {kind}: {cnt}건")


# ---------------------------------------------------------------
# 3. 실행
# ---------------------------------------------------------------
def run():
    if not KEY:
        print("DATA_API_KEY를 .env에서 읽지 못했습니다.")
        return

    conn = get_conn()
    for kind, (name, endpoint, groups) in KINDS.items():
        for group_no in groups:
            print(f"[{name}] 권역 {group_no}")
            products = fetch_group(endpoint, group_no)
            save_products(conn, kind, group_no, products)
            print(f"  → {len(products)}건 저장")
            time.sleep(REQUEST_DELAY)
    print_summary(conn)
    conn.close()


if __name__ == "__main__":
    run()