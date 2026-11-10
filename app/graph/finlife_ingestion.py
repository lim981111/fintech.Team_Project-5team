"""금융감독원 '금융상품한눈에'(금융상품 통합비교공시) 수집 모듈. 정기예금과 적금을 다룬다.

  - 은행(020000)과 저축은행(030300) 권역을 모두 받아, 상품(baseList)과 기간별 금리(optionList)를 합쳐 저장한다.
  - 금리는 숫자 데이터라 벡터 검색이 아니라 정렬/필터로 찾는다. (product_search.py)
  - 결과는 finlife_cache.json 에 저장하고, 질문 처리 중에는 저장본만 읽는다. (API 호출 없음)
  - 갱신:  python -m app.graph.ingest_all --only products
  - 필요한 .env:  FINLIFE_API_KEY (금융상품한눈에에서 발급)
  - 주소는 .env의 FINLIFE_URL(정기예금), FINLIFE_SAVING_URL(적금)로 바꿀 수 있다.
    (적금 주소는 정기예금 주소의 'depositProductsSearch'를 'savingProductsSearch'로 바꾼 것이며,
     정기예금은 실제 호출로 확인했지만 적금은 아직 확인하지 못했다.)
"""

import datetime as dt
import logging
import os

import requests

from app.graph.common import (
    BASE_DIR,
    FSS_VERIFY,
    load_json_cached,
    write_json_atomic,
)

logger = logging.getLogger(__name__)

FINLIFE_KEY = os.getenv("FINLIFE_API_KEY")

DEPOSIT_URL = os.getenv(
    "FINLIFE_URL", "https://finlife.fss.or.kr/finlifeapi/depositProductsSearch.json"
)
SAVING_URL = os.getenv(
    "FINLIFE_SAVING_URL",
    DEPOSIT_URL.replace("depositProductsSearch", "savingProductsSearch"),
)

KINDS = {
    "deposit": {"name": "정기예금", "url": DEPOSIT_URL},
    "saving": {"name": "적금", "url": SAVING_URL},
}
GROUPS = {"020000": "은행", "030300": "저축은행"}

CACHE_FILE = os.path.join(BASE_DIR, "finlife_cache.json")
SOURCE_NAME = "금융상품한눈에"
REQUEST_TIMEOUT = 15
MAX_PAGES = 50


def _get_json(url, params):
  try:
    response = requests.get(
        url, params=params, verify=FSS_VERIFY, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
  except requests.RequestException as e:
    status = getattr(e.response, "status_code", None)
    logger.error("금융상품 API 요청 실패 (%s, status=%s)", type(e).__name__, status)
    return None
  try:
    return response.json()
  except ValueError:
    logger.error("금융상품 API 응답을 JSON으로 읽지 못했습니다.")
    return None


def _to_float(value):
  try:
    return float(value)
  except (TypeError, ValueError):
    return None


def _to_int(value):
  try:
    return int(str(value).strip())
  except (TypeError, ValueError):
    return None


def _build_item(kind, base, group_name, options):
  company = (base.get("kor_co_nm") or "").strip()
  name = (base.get("fin_prdt_nm") or "").strip()

  built_options = []
  for opt in options:
    rate_type = (opt.get("intr_rate_type_nm") or "").strip()
    reserve_type = (opt.get("rsrv_type_nm") or "").strip()  # 적금만 있음(정액/자유적립식)
    built_options.append({
        "term": _to_int(opt.get("save_trm")),
        "rate_type": "·".join(x for x in (rate_type, reserve_type) if x),
        "rate": _to_float(opt.get("intr_rate")),        # 기본금리
        "rate_max": _to_float(opt.get("intr_rate2")),   # 최고 우대금리
    })
  built_options.sort(key=lambda o: (o["term"] is None, o["term"] or 0))

  return {
      "kind": kind,
      "kind_name": KINDS[kind]["name"],
      "source": SOURCE_NAME,
      "metadata": {
          "title": f"{company} {name}".strip(),
          "company": company,
          "name": name,
          "group": group_name,
          "company_code": base.get("fin_co_no"),
          "product_code": base.get("fin_prdt_cd"),
          "dcls_month": base.get("dcls_month"),
          "join_way": (base.get("join_way") or "").strip(),
          "join_member": (base.get("join_member") or "").strip(),
          "special_condition": (base.get("spcl_cnd") or "").strip(),
          "interest_note": (base.get("mtrt_int") or "").strip(),
          "max_limit": base.get("max_limit"),
          "note": (base.get("etc_note") or "").strip(),
      },
      "options": built_options,
  }


def _fetch_kind(kind, key):
  """한 종류(정기예금/적금)의 모든 권역·페이지를 받아 상품 리스트로 반환. 실패하면 None."""
  url = KINDS[kind]["url"]
  bases, options = {}, {}

  for group_no, group_name in GROUPS.items():
    for page in range(1, MAX_PAGES + 1):
      data = _get_json(url, {"auth": key, "topFinGrpNo": group_no, "pageNo": page})
      result = (data or {}).get("result")
      if not isinstance(result, dict):
        logger.error("금융상품(%s) 응답 형태가 예상과 다릅니다.", KINDS[kind]["name"])
        return None
      if str(result.get("err_cd")) != "000":
        logger.error(
            "금융상품(%s) 조회 오류: %s %s",
            KINDS[kind]["name"], result.get("err_cd"), result.get("err_msg"),
        )
        return None

      for base in result.get("baseList") or []:
        code = (base.get("fin_co_no"), base.get("fin_prdt_cd"))
        bases[code] = (base, group_name)
      for opt in result.get("optionList") or []:
        options.setdefault((opt.get("fin_co_no"), opt.get("fin_prdt_cd")), []).append(opt)

      if page >= (_to_int(result.get("max_page_no")) or 1):
        break

  return [
      _build_item(kind, base, group_name, options.get(code, []))
      for code, (base, group_name) in bases.items()
  ]


def load_local_products():
  """저장된 금융상품 목록만 읽는다 (API 호출 없음)"""
  data = load_json_cached(CACHE_FILE, {})
  items = data.get("items") if isinstance(data, dict) else None
  return items if isinstance(items, list) else []


def load_products_info():
  """저장 시각과 공시 기준월(가장 최근 dcls_month)을 반환"""
  data = load_json_cached(CACHE_FILE, {})
  if not isinstance(data, dict):
    return {}
  months = [
      p["metadata"].get("dcls_month") for p in data.get("items", [])
      if p.get("metadata", {}).get("dcls_month")
  ]
  return {"fetched_at": data.get("fetched_at"), "dcls_month": max(months) if months else None}


def fetch_and_save_products():
  """API에서 정기예금과 적금을 받아 저장하고 상품 리스트를 반환. 모두 실패하면 [] (기존 저장본 유지)

  한 종류만 실패하면 그 종류는 이전 저장본을 그대로 쓴다.
  """
  if not FINLIFE_KEY:
    logger.error("FINLIFE_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return []

  previous = load_local_products()
  items, fresh_kinds = [], 0
  for kind in KINDS:
    fresh = _fetch_kind(kind, FINLIFE_KEY)
    if fresh:
      items.extend(fresh)
      fresh_kinds += 1
      logger.info("%s %d건을 받았습니다.", KINDS[kind]["name"], len(fresh))
      continue
    old = [p for p in previous if p.get("kind") == kind]
    if old:
      logger.warning("%s 갱신에 실패해 이전 저장본 %d건을 유지합니다.", KINDS[kind]["name"], len(old))
      items.extend(old)

  if fresh_kinds == 0:
    return []

  write_json_atomic(
      CACHE_FILE,
      {"fetched_at": dt.datetime.now().isoformat(timespec="seconds"), "items": items},
  )
  return items


if __name__ == "__main__":
  import sys

  logging.basicConfig(level=logging.INFO)
  data = fetch_and_save_products() if "--fetch" in sys.argv else load_local_products()
  print(f"금융상품 {len(data)}건 (정기예금 {sum(p['kind'] == 'deposit' for p in data)}, "
        f"적금 {sum(p['kind'] == 'saving' for p in data)})")
  print(load_products_info())
