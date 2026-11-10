import json
import logging
import os
import re
import tempfile
from urllib.parse import urljoin

import requests
import urllib3
import xmltodict
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

FSS_API_KEY = os.getenv("FSS_API_KEY")
FSS_API_URL = "https://www.fss.or.kr/edu/openApi/api/eduProgram.jsp"
FSS_BASE_URL = "https://www.fss.or.kr"

REQUEST_TIMEOUT = 10  # 초

# SSL 검증 설정 (.env의 FSS_VERIFY_SSL)
#   true(기본)  : 정상 검증
#   false       : 검증 끔 (인증서 문제가 있을 때 개발용으로만 사용)
#   그 외 문자열 : CA 번들 파일 경로
_verify_env = os.getenv("FSS_VERIFY_SSL", "true").strip()
if _verify_env.lower() == "true":
  SSL_VERIFY = True
elif _verify_env.lower() == "false":
  SSL_VERIFY = False
  urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
  logger.warning("SSL 인증서 검증이 꺼져 있습니다. 운영 환경에서는 사용하지 마세요.")
else:
  SSL_VERIFY = _verify_env

# 프로젝트 최상단(루트) 디렉토리에 캐시 파일 생성
BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
CACHE_FILE = os.path.join(BASE_DIR, "fss_edu_cache.json")


def _as_text(value, default=""):
  """xmltodict가 만든 값(str 또는 {'#text': ...})을 문자열로 변환"""
  if isinstance(value, dict):
    value = value.get("#text", default)
  return value if value else default


def clean_html_and_extract_links(raw_html):
  """HTML 태그를 제거하고 순수 텍스트와 함께 포함된 링크(URL)를 추출하는 함수"""
  if not raw_html:
    return "", []

  soup = BeautifulSoup(raw_html, "html.parser")

  # 상대 경로 링크는 금감원 도메인 기준으로 절대 경로로 보정
  extracted_links = [
      urljoin(FSS_BASE_URL, a["href"].strip())
      for a in soup.find_all("a", href=True)
  ]

  clean_text = soup.get_text(separator=" ", strip=True)
  return clean_text, extracted_links


def _parse_item(item):
  """API 응답의 항목 하나를 RAG용 딕셔너리로 변환"""
  title = _as_text(item.get("programName"), "금융 교육 프로그램")
  institution = "금융감독원"
  target_audience = _as_text(item.get("target"), "청년/전국민")
  period = _as_text(item.get("eduPrd"), "상시접수")

  api_url = _as_text(
      item.get("url") or item.get("link") or item.get("homepage"), ""
  )
  clean_content, html_links = clean_html_and_extract_links(
      _as_text(item.get("cntnt"), "")
  )

  # 링크 통합 + 중복 제거 (순서 유지, http(s)만 허용)
  all_links = ([urljoin(FSS_BASE_URL, api_url)] if api_url else []) + html_links
  valid_links = [
      link for link in dict.fromkeys(all_links) if link.startswith("http")
  ]

  content_parts = [
      f"교육 프로그램명: {title}",
      f"주관 기관: {institution}",
      f"교육 대상: {target_audience}",
      f"신청 기간: {period}",
      f"상세 설명: {clean_content if clean_content else '설명 내용이 없습니다.'}",
  ]
  if valid_links:
    content_parts.append(f"관련 영상 및 교육 링크: {', '.join(valid_links)}")

  return {
      "metadata": {
          "title": title,
          "institution": institution,
          "target_audience": target_audience,
          "period": period,
          "links": valid_links,
      },
      "source": "금감원 교육 API",
      "content": "\n".join(content_parts),
  }


def _write_cache(data):
  """임시 파일에 쓴 뒤 교체해서, 쓰는 도중 파일이 깨지는 것을 방지"""
  fd, tmp_path = tempfile.mkstemp(dir=BASE_DIR, suffix=".tmp")
  try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp_path, CACHE_FILE)
  except Exception:
    if os.path.exists(tmp_path):
      os.remove(tmp_path)
    raise


def _read_cache():
  """캐시 파일을 읽어 리스트로 반환. 없거나 비었거나 깨졌으면 None"""
  if not os.path.exists(CACHE_FILE):
    return None
  try:
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
      data = json.load(f)
    return data if data else None  # 빈 리스트는 캐시로 인정하지 않음
  except Exception as e:
    logger.warning("캐시 파일 읽기 실패: %s", e)
    return None


# 파일 수정 시각이 바뀔 때만 다시 읽도록 메모리에 보관 (요청마다 파일을 읽지 않음)
_local_cache = {"mtime": None, "data": []}


def load_local_data():
  """로컬에 저장된 데이터만 읽어 반환. 절대 API를 호출하지 않는다.

  질문을 처리하는 경로에서는 반드시 이 함수를 사용한다.
  """
  try:
    mtime = os.path.getmtime(CACHE_FILE)
  except OSError:
    return []

  if _local_cache["mtime"] != mtime:
    _local_cache["data"] = _read_cache() or []
    _local_cache["mtime"] = mtime
  return _local_cache["data"]


def fetch_and_save_fss_data():
  """금감원 API에서 데이터를 가져와 정제한 뒤 로컬에 캐싱하는 함수"""
  if not FSS_API_KEY:
    logger.error("FSS_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return []

  try:
    logger.info("금감원 API에서 최신 데이터를 불러오는 중...")
    response = requests.get(
        FSS_API_URL,
        params={"apiType": "xml", "authKey": FSS_API_KEY},
        verify=SSL_VERIFY,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
  except requests.RequestException as e:
    # 예외 메시지에는 authKey가 포함된 URL이 들어 있으므로 출력하지 않음
    status = getattr(e.response, "status_code", None)
    logger.error(
        "FSS API 요청 실패 (%s, status=%s)", type(e).__name__, status
    )
    return []

  try:
    data = xmltodict.parse(response.text)
    root = (data.get("document") or {}).get("root") or {}
    items = root.get("result", [])
    if isinstance(items, dict):
      items = [items]

    edu_data_list = [_parse_item(item) for item in items]
  except Exception:
    logger.exception("FSS API 응답 파싱 실패")
    return []

  if not edu_data_list:
    logger.warning("FSS API가 빈 결과를 반환했습니다. 캐시에 저장하지 않습니다.")
    return []

  try:
    _write_cache(edu_data_list)
  except Exception:
    logger.exception("캐시 저장 실패 (데이터는 그대로 반환합니다)")

  logger.info("총 %d개의 데이터를 캐시에 저장했습니다.", len(edu_data_list))
  return edu_data_list


def get_fss_edu_rag_data():
  """저장된 데이터를 반환하고, 저장된 게 하나도 없을 때만 API를 호출해 저장한다.

  서버 시작이나 적재 스크립트에서 쓰는 함수이며, 질문 처리 경로에서는
  load_local_data()를 사용한다. 데이터를 최신으로 바꾸려면
  fetch_and_save_fss_data()를 명시적으로 실행한다. (자동 갱신 없음)
  """
  data = load_local_data()
  if data:
    return data
  return fetch_and_save_fss_data()


# ------------------------------------------------------------
# 간단한 키워드 기반 검색 (임베딩 검색 도입 전 임시 방식)
# ------------------------------------------------------------
def _bigrams(text):
  """한글 조사 변화에 덜 민감하도록 2글자 단위로 쪼갠 집합을 반환"""
  grams = set()
  for token in re.findall(r"[0-9a-z가-힣]+", text.lower()):
    if len(token) >= 2:
      grams.update(token[i : i + 2] for i in range(len(token) - 1))
  return grams


def search_fss_edu(query, data, top_k=4):
  """질문과 관련도가 높은 교육 프로그램을 점수순으로 반환 (일치 항목이 없으면 [])"""
  query_grams = _bigrams(query)
  if not query_grams:
    return []

  scored = []
  for item in data:
    meta = item.get("metadata", {})
    title_grams = _bigrams(meta.get("title", ""))
    target_grams = _bigrams(meta.get("target_audience", ""))
    content_grams = _bigrams(item.get("content", ""))

    score = (
        3 * len(query_grams & title_grams)
        + 2 * len(query_grams & target_grams)
        + len(query_grams & content_grams)
    )
    if score > 0:
      scored.append((score, item))

  scored.sort(key=lambda pair: pair[0], reverse=True)
  return [item for _, item in scored[:top_k]]


# ==========================================
# 🧪 단독 테스트 실행 (터미널에서 링크 추출 결과 확인)
# ==========================================
if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO)
  print("=== [테스트] 영상 및 링크 추출 테스트 시작 ===")
  data = get_fss_edu_rag_data()
  print(f"\n[결과] 불러온 교육 프로그램 총 개수: {len(data)}건")

  if data:
    linked_items = [d for d in data if d["metadata"]["links"]]
    print(f"[정보] 링크가 포함된 프로그램 수: {len(linked_items)}건")

    print("\n--- 첫 번째 데이터 샘플 ---")
    print(f"제목: {data[0]['metadata']['title']}")
    print(f"추출된 링크 주소: {data[0]['metadata']['links']}")
    print(f"내용 일부:\n{data[0]['content'][:200]}...")

    print("\n--- 검색 테스트 ('청년 투자') ---")
    for r in search_fss_edu("청년 투자", data):
      print(f"- {r['metadata']['title']}")

  print("\n=== 테스트 완료 ===")