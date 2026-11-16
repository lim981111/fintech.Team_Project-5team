"""금융상품한눈에 API: 상품 종류 × 권역코드 조합 중 데이터가 있는 것을 확인하는 1회용 스크립트.

실행: python -m app.graph.check_finlife   (호출 30번, 조합마다 1페이지만)
"""
import os
import re
import time
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

load_dotenv()

KEY = os.getenv("DATA_API_KEY")
BASE = "http://finlife.fss.or.kr/finlifeapi"     # 실제 호출로 확인된 주소 (GET, XML, euc-kr)

PRODUCTS = {
    "정기예금": "depositProductsSearch",
    "적금": "savingProductsSearch",
    "연금저축": "annuitySavingProductsSearch",
    "주택담보대출": "mortgageLoanProductsSearch",
    "전세자금대출": "rentHouseLoanProductsSearch",
    "개인신용대출": "creditLoanProductsSearch",
}
GROUPS = {
    "020000": "은행",
    "030200": "여신전문",
    "030300": "저축은행",
    "050000": "보험",
    "060000": "금융투자",
}

# 이 경우엔 다른 조합도 다 실패하므로 바로 멈춘다
# (키 문제 / 한도 초과 / IP 문제 / 응답이 XML이 아님)
STOP_CODES = {"010", "011", "012", "013", "020", "021", "NOT_XML", "FAILED"}

def parse_xml(content):
    """euc-kr 응답을 직접 디코딩해서 XML로 변환 (파이썬 XML 파서는 euc-kr을 못 읽음)."""
    text = content.decode("cp949", errors="replace")
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    return ET.fromstring(text)


def check_one(endpoint, group_no):
    """호출 1번. (결과 문장, 오류코드) 반환."""
    params = {"auth": KEY, "topFinGrpNo": group_no, "pageNo": 1}
    try:
        res = requests.get(f"{BASE}/{endpoint}.xml", params=params, timeout=15)
        root = parse_xml(res.content)
    except requests.RequestException as e:
        return f"호출 실패 ({type(e).__name__})", "FAILED"
    except ET.ParseError:
        if "firewall" in res.text.lower():
            return "방화벽 차단 (요청이 잦아 IP가 일시 차단된 것으로 보임)", "BLOCKED"
        return f"XML 아님 (status={res.status_code})", "NOT_XML"

    err_cd = root.findtext(".//err_cd")
    if err_cd not in (None, "000"):
        return f"오류 {err_cd} {root.findtext('.//err_msg')}", err_cd

    total = root.findtext(".//total_count")
    if total is None:
        return "응답 형식 이상 (total_count 없음)", "NOT_XML"
    return f"{total}건", None


def main():
    if not KEY:
        print("DATA_API_KEY를 .env에서 읽지 못했습니다.")
        return

    for name, endpoint in PRODUCTS.items():
        for group_no, group_name in GROUPS.items():
            result, err_cd = check_one(endpoint, group_no)
            print(f"{name:<8} {group_no} {group_name:<6} → {result}")
            if err_cd in STOP_CODES:
                print("키/한도 문제로 보여 여기서 중단합니다.")
                return
            time.sleep(2)


if __name__ == "__main__":
    main()