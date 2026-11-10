"""한국사회보장정보원 '중앙부처복지서비스'(복지로) 수집 모듈.

  - 목록 조회(callTp=L)로 전체 서비스를 받고, 서비스마다 상세 조회(callTp=D)를 한 번씩 호출한다.
  - 결과는 welfare_cache.json 에 저장하고, 질문 처리 중에는 저장본만 읽는다. (API 호출 없음)
  - 갱신:  python -m app.graph.ingest_all --only welfare
  - 필요한 .env:  WELFARE_API_KEY (공공데이터포털에서 받은 키, Encoding/Decoding 키 모두 가능)
"""

import logging
import os
import time

import requests
import xmltodict

from app.graph.common import (
    BASE_DIR,
    as_list,
    as_text,
    clean_text,
    decode_key,
    load_json_cached,
    shorten,
    split_csv,
    write_json_atomic,
)

logger = logging.getLogger(__name__)

WELFARE_KEY = os.getenv("WELFARE_API_KEY")

_BASE = "https://apis.data.go.kr/B554287/NationalWelfareInformationsV001"
LIST_URL = os.getenv("WELFARE_LIST_URL", _BASE + "/NationalWelfarelistV001")
DETAIL_URL = os.getenv("WELFARE_DETAIL_URL", _BASE + "/NationalWelfaredetailedV001")

CACHE_FILE = os.path.join(BASE_DIR, "welfare_cache.json")
SOURCE_NAME = "복지로 중앙부처복지서비스"

PAGE_SIZE = 100  # 한 번에 받을 목록 개수 (이 API는 최대 500)
REQUEST_TIMEOUT = 15
DETAIL_DELAY = 0.1  # 상세 호출 사이 대기(초): 호출 한도와 서버 부담을 고려
RETRY_DELAY = 1.0
MAX_RETRIES = 2
MAX_PAGES = 50  # 무한 반복 방지


def _get_xml(url, params):
  """한 번 호출해서 XML을 dict로 반환. 실패하면 None. (예외 메시지에는 키가 섞일 수 있어 출력하지 않음)"""
  try:
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
  except requests.RequestException as e:
    status = getattr(e.response, "status_code", None)
    logger.error("복지 API 요청 실패 (%s, status=%s)", type(e).__name__, status)
    return None
  try:
    return xmltodict.parse(response.text)
  except Exception:
    logger.error("복지 API 응답을 XML로 읽지 못했습니다.")
    return None


def _auth_error(data):
  """공공데이터포털이 인증/호출 오류를 HTTP 200 + 별도 XML로 돌려주는 경우를 감지"""
  response = (data or {}).get("OpenAPI_ServiceResponse")
  if not response:
    return False
  header = response.get("cmmMsgHeader") or {}
  logger.error(
      "복지 API 호출 오류: %s",
      as_text(header.get("returnAuthMsg") or header.get("errMsg"), "알 수 없음"),
  )
  return True


def _to_int(value, default=0):
  try:
    return int(str(value).strip())
  except (TypeError, ValueError):
    return default


def _fetch_list(key):
  """전체 서비스 목록(요약)을 모두 받아 list로 반환. 실패하면 None."""
  collected = {}
  for page in range(1, MAX_PAGES + 1):
    data = _get_xml(
        LIST_URL,
        {
            "serviceKey": key,
            "callTp": "L",
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
            "srchKeyCode": "001",
        },
    )
    if data is None or _auth_error(data):
      return None

    root = data.get("wantedList") or {}
    if as_text(root.get("resultCode")).strip() not in ("0", "00"):
      logger.error("복지 목록 조회 실패: %s", as_text(root.get("resultMessage")))
      return None

    total = _to_int(root.get("totalCount"))
    batch = [e for e in as_list(root.get("servList")) if isinstance(e, dict)]
    for entry in batch:
      serv_id = as_text(entry.get("servId")).strip()
      if serv_id:
        collected.setdefault(serv_id, entry)

    if not batch or len(collected) >= total:
      break
  return list(collected.values())


def _fetch_detail(key, serv_id):
  """서비스 하나의 상세를 받아 dict로 반환. 실패하면 None."""
  for attempt in range(MAX_RETRIES + 1):
    data = _get_xml(
        DETAIL_URL, {"serviceKey": key, "callTp": "D", "servId": serv_id}
    )
    if data is not None and _auth_error(data):
      return None
    root = (data or {}).get("wantedDtl")
    if isinstance(root, dict) and as_text(root.get("resultCode")).strip() in ("", "0", "00"):
      return root
    if attempt < MAX_RETRIES:
      time.sleep(RETRY_DELAY * (attempt + 1))
  return None


def _entries(value):
  """상세의 반복 항목(servSeDetailNm / servSeDetailLink)을 [{'name','url'}] 로 정리"""
  entries = []
  for entry in as_list(value):
    if isinstance(entry, dict):
      entries.append({
          "name": clean_text(entry.get("servSeDetailNm")),
          "url": as_text(entry.get("servSeDetailLink")).strip(),
      })
  return entries


def _line(label, value):
  return f"{label}: {value}" if value else None


def _parse_service(item, detail):
  """목록 항목 + 상세를 RAG용 딕셔너리로 변환 (교육 데이터와 같은 모양: metadata/source/content/display_text)"""
  detail = detail or {}

  serv_id = as_text(item.get("servId")).strip()
  title = clean_text(item.get("servNm")) or clean_text(detail.get("servNm")) or "복지 서비스"
  summary = clean_text(item.get("servDgst")) or clean_text(detail.get("wlfareInfoOutlCn"))

  # 목록과 상세에서 표기(쉼표 공백, 순서)가 달라서 쉼표로 나눠 정리한 리스트로 보관
  life = split_csv(item.get("lifeArray")) or split_csv(detail.get("lifeArray"))
  household = split_csv(item.get("trgterIndvdlArray")) or split_csv(detail.get("trgterIndvdlArray"))
  themes = split_csv(item.get("intrsThemaArray")) or split_csv(detail.get("intrsThemaArray"))

  ministry = clean_text(item.get("jurMnofNm"))
  organization = clean_text(item.get("jurOrgNm"))
  contact = clean_text(item.get("rprsCtadr")) or clean_text(detail.get("rprsCtadr"))
  support_cycle = clean_text(item.get("sprtCycNm"))
  provide_type = clean_text(item.get("srvPvsnNm"))
  online_flag = as_text(item.get("onapPsbltYn")).strip().upper()
  online_text = {"Y": "가능", "N": "불가"}.get(online_flag, "")
  detail_url = as_text(item.get("servDtlLink")).strip()

  target = clean_text(detail.get("tgtrDtlCn"))
  criteria = clean_text(detail.get("slctCritCn"))
  benefit = clean_text(detail.get("alwServCn"))

  apply_entries = _entries(detail.get("applmetList"))
  homepage_entries = _entries(detail.get("inqplHmpgReldList"))
  apply_names = list(dict.fromkeys(e["name"] for e in apply_entries if e["name"]))

  all_links = [detail_url] + [e["url"] for e in apply_entries + homepage_entries]
  links = [link for link in dict.fromkeys(all_links) if link.startswith("http")]

  content = "\n".join(
      part
      for part in (
          _line("서비스명", title),
          _line("소관", " ".join(x for x in (ministry, organization) if x)),
          _line("개요", summary),
          _line("생애주기", ", ".join(life)),
          _line("가구 유형", ", ".join(household)),
          _line("관심 주제", ", ".join(themes)),
          _line("지원 대상", target),
          _line("선정 기준", criteria),
          _line("지원 내용", benefit),
          _line("신청 방법", ", ".join(apply_names)),
          _line("지원 주기", support_cycle),
          _line("문의처", contact),
      )
      if part
  )

  display_text = "\n".join(
      part
      for part in (
          _line("서비스명", title),
          _line("소관", " ".join(x for x in (ministry, organization) if x)),
          _line("개요", shorten(summary, 160)),
          _line("지원 대상", shorten(target, 160)),
          _line("지원 내용", shorten(benefit, 160)),
          _line("신청 방법", ", ".join(apply_names)),
          _line("온라인 신청", online_text),
          _line("문의처", contact),
          _line("자세히 보기", detail_url),
      )
      if part
  )

  return {
      "metadata": {
          "serv_id": serv_id,
          "title": title,
          "institution": ministry,
          "summary": summary,
          "life": life,
          "household": household,
          "themes": themes,
          "online_apply": online_text,
          "support_cycle": support_cycle,
          "provide_type": provide_type,
          "contact": contact,
          "url": detail_url,
          "links": links,
      },
      "source": SOURCE_NAME,
      "content": content,
      "display_text": display_text,
  }


def load_local_welfare():
  """저장된 복지 데이터만 읽는다 (API 호출 없음)"""
  data = load_json_cached(CACHE_FILE, [])
  return data if isinstance(data, list) else []


def fetch_and_save_welfare():
  """API에서 목록과 상세를 모두 받아 저장하고 결과 리스트를 반환. 실패하면 [] (기존 저장본은 유지)

  상세 조회가 일부 실패하면 이전 저장본의 같은 서비스를 재사용하고,
  그것도 없으면 목록 정보만으로 저장한다.
  호출이 서비스 수(수백 건)만큼 필요하므로, 공공데이터포털의 하루 호출 한도를 확인해 두세요.
  """
  if not WELFARE_KEY:
    logger.error("WELFARE_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return []
  key = decode_key(WELFARE_KEY)

  logger.info("복지 서비스 목록을 불러오는 중...")
  items = _fetch_list(key)
  if not items:
    return []
  logger.info("복지 서비스 %d건 확인. 상세 정보를 불러옵니다.", len(items))

  previous = {
      d["metadata"].get("serv_id"): d for d in load_local_welfare()
  }
  results, reused, list_only = [], 0, 0
  for index, item in enumerate(items, 1):
    serv_id = as_text(item.get("servId")).strip()
    detail = _fetch_detail(key, serv_id)
    if detail is not None:
      results.append(_parse_service(item, detail))
    elif serv_id in previous:
      results.append(previous[serv_id])
      reused += 1
    else:
      results.append(_parse_service(item, None))
      list_only += 1

    if index % 50 == 0:
      logger.info("복지 상세 수집 중... %d/%d", index, len(items))
    time.sleep(DETAIL_DELAY)

  if reused or list_only:
    logger.warning(
        "상세 조회 실패 %d건 (이전 저장본 재사용 %d건, 목록 정보만 저장 %d건)",
        reused + list_only, reused, list_only,
    )

  write_json_atomic(CACHE_FILE, results)
  logger.info("복지 서비스 %d건을 저장했습니다.", len(results))
  return results


if __name__ == "__main__":
  import sys

  logging.basicConfig(level=logging.INFO)
  data = fetch_and_save_welfare() if "--fetch" in sys.argv else load_local_welfare()
  print(f"복지 서비스 {len(data)}건")
  if data:
    print(data[0]["display_text"])
  else:
    print("저장된 데이터가 없습니다. `python -m app.graph.welfare_ingestion --fetch` 또는 ingest_all을 실행하세요.")
