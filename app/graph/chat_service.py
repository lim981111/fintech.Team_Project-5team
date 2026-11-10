"""질문 → 답변 생성 로직.

FastAPI와 분리해 두었기 때문에 POST 요청 없이 이 파일만 실행해서 검증할 수 있다.
    python -m app.graph.chat_service

중요: 질문을 처리하는 동안에는 저장된 로컬 데이터만 사용하며,
      금감원 API를 절대 호출하지 않는다. (API 갱신은 vector_store 스크립트에서만)
"""

import logging
from urllib.parse import urlparse

from app.graph.api_ingestion import (
    get_fss_edu_rag_data,
    load_local_data,
    search_fss_edu,
)

logger = logging.getLogger(__name__)

# 벡터 DB 패키지(chromadb 등)가 없거나 문제가 있어도 키워드 검색으로 계속 동작
try:
  from app.graph.vector_store import ensure_vector_db, search_vector
except Exception as e:  # noqa: BLE001
  ensure_vector_db = None
  search_vector = None
  logger.warning("벡터 검색을 사용할 수 없습니다 (%s). 키워드 검색으로 대체합니다.", e)

TOP_K = 4
NOT_READY_MESSAGE = "교육 데이터가 아직 준비되지 않았습니다. 잠시 후 다시 시도해 주세요."


def prepare_data():
  """서버 시작 시 1회 호출: 저장된 데이터 확보 + 벡터 DB 준비.

  저장된 데이터가 하나도 없을 때만 API를 호출한다.
  """
  data = get_fss_edu_rag_data()
  if not data:
    logger.error(
        "저장된 교육 데이터가 없습니다. FSS_API_KEY/네트워크 확인 후"
        " `python -m app.graph.vector_store`를 실행하세요."
    )
    return
  if ensure_vector_db is not None:
    try:
      ensure_vector_db()
    except Exception:
      logger.exception("벡터 DB 준비 실패 - 키워드 검색으로 대체합니다.")


def search_documents(query, data, top_k=TOP_K):
  """(결과 리스트, 사용된 검색 방식)을 반환. 방식: 'vector' | 'keyword' | 'general'"""
  if search_vector is not None:
    try:
      results = search_vector(query, top_k=top_k, data=data)
      if results:
        return results, "vector"
    except Exception:
      logger.exception("벡터 검색 실패 - 키워드 검색으로 대체합니다.")

  results = search_fss_edu(query, data, top_k=top_k)
  if results:
    return results, "keyword"

  return data[:top_k], "general"


VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com")
VIDEO_EXTENSIONS = (".mp4", ".webm", ".m3u8")


def _link_type(url):
  """영상 링크면 'video', 아니면 'link'"""
  parsed = urlparse(url)
  host = parsed.netloc.lower().removeprefix("www.")
  if any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS):
    return "video"
  if parsed.path.lower().endswith(VIDEO_EXTENSIONS):
    return "video"
  return "link"


def build_contents(results):
  """검색된 프로그램들의 링크를 프론트에서 바로 쓸 수 있는 목록으로 만든다.

  형태: [{"title": 프로그램명, "url": 링크, "type": "video" | "link"}, ...]
  영상 링크가 앞에 오고, 같은 URL은 한 번만 포함한다.
  """
  contents, seen = [], set()
  for res in results:
    title = res["metadata"].get("title", "")
    for url in res["metadata"].get("links", []):
      if url in seen:
        continue
      seen.add(url)
      contents.append({"title": title, "url": url, "type": _link_type(url)})
  contents.sort(key=lambda c: c["type"] != "video")  # 정렬은 안정적이라 기존 순서 유지
  return contents


def answer_question(question, job="학생"):
  """질문에 대한 응답(dict)을 만든다. /api/chat 응답과 같은 형태."""
  data = load_local_data()  # 로컬 저장본만 읽음 (API 호출 없음)
  if not data:
    return {
        "answer": NOT_READY_MESSAGE,
        "policy": [],
        "programs": [],
        "contents": [],
    }

  results, route = search_documents(f"{question} {job}", data)

  if route == "general":
    intro = (
        "질문과 직접 일치하는 교육은 찾지 못해, 금감원의 일반 금융 교육"
        " 프로그램을 안내합니다."
    )
  else:
    intro = (
        f"'{job}' 조건과 질문을 반영하여 관련 금융 교육"
        f" {len(results)}건을 찾았습니다."
    )

  retrieved_texts = [res["content"] for res in results]
  answer_text = intro + "\n\n" + "\n\n---\n\n".join(retrieved_texts)
  return {
      "answer": answer_text,
      # 화면의 '관련 교육/정책'에 그대로 출력되는 값이라 문자열(프로그램명) 목록으로 보낸다
      "policy": [res["metadata"].get("title", "") for res in results],
      # 프로그램 전체 정보(대상, 신청 기간, 링크 등)가 필요할 때 쓰는 값
      "programs": results,
      "contents": build_contents(results),
  }


# ==========================================
# 🧪 자체 검증 (POST 없이 실행): python -m app.graph.chat_service
# ==========================================
if __name__ == "__main__":
  import sys

  from app.graph import api_ingestion

  logging.basicConfig(level=logging.INFO)
  failures = []

  def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}".rstrip())
    if not ok:
      failures.append(name)

  # 1) 저장된 데이터 로드
  data = load_local_data()
  check("저장된 데이터 로드", len(data) > 0, f"({len(data)}건)")
  if not data:
    print("\n[중단] 저장된 데이터가 없습니다. 먼저 `python -m app.graph.api_ingestion`을"
          " 실행해 데이터를 저장하세요.")
    sys.exit(1)

  # 2) 반복 호출해도 파일을 다시 읽지 않고 메모리 데이터를 재사용
  check("메모리 재사용(파일 재읽기 없음)", load_local_data() is load_local_data())

  # 3) 질문 처리 중 API 호출 감시: requests.get이 불리면 실패 처리
  api_calls = []
  real_get = api_ingestion.requests.get

  def _guard(*args, **kwargs):
    api_calls.append(args)
    raise AssertionError("질문 처리 중 금감원 API가 호출되었습니다!")

  api_ingestion.requests.get = _guard
  try:
    samples = [
        ("청년이 투자를 시작하려면 어떤 교육을 들어야 해?", "학생"),
        ("대출 사기 예방 교육 알려줘", "직장인"),
        ("노후 준비", "자영업자"),
        ("zzzz qqqq", "학생"),  # 일치 항목이 없는 질문 → 일반 안내로 떨어지는지
    ]
    for q, job in samples:
      resp = answer_question(q, job)
      _, route = search_documents(f"{q} {job}", data)
      policy = resp["programs"]
      contents = resp["contents"]

      shape_ok = (
          set(resp) == {"answer", "policy", "programs", "contents"}
          and 0 < len(policy) <= TOP_K
          and all(isinstance(p["metadata"]["links"], list) for p in policy)
          and all(isinstance(t, str) for t in resp["policy"])
          and resp["policy"] == [p["metadata"]["title"] for p in policy]
          and all({"title", "url", "type"} <= set(c) for c in contents)
          and len({c["url"] for c in contents}) == len(contents)
      )
      check(f"응답 형태/개수 [{route}] '{q}'", shape_ok, f"({len(policy)}건)")
      for p in policy:
        links = p["metadata"]["links"]
        print(f"    - {p['metadata']['title']}  (링크 {len(links)}개)")
      # policy에 포함된 링크가 contents에 빠짐없이 들어갔는지
      expected = {u for p in policy for u in p["metadata"]["links"]}
      check("  contents에 링크 반영", {c["url"] for c in contents} == expected,
            f"(영상 {sum(c['type'] == 'video' for c in contents)}개, 일반 {sum(c['type'] == 'link' for c in contents)}개)")

    # 4) 저장 데이터가 없는 상황에서도 API를 호출하지 않고 안내 문구만 반환
    real_cache_file = api_ingestion.CACHE_FILE
    api_ingestion.CACHE_FILE = real_cache_file + ".not_exist"
    try:
      resp = answer_question("투자", "학생")
      check(
          "저장 데이터 없을 때 안내 문구 반환",
          resp["answer"] == NOT_READY_MESSAGE
          and resp["policy"] == []
          and resp["programs"] == [],
      )
    finally:
      api_ingestion.CACHE_FILE = real_cache_file
  finally:
    api_ingestion.requests.get = real_get

  check("질문 처리 중 API 호출 0회", len(api_calls) == 0, f"(호출 {len(api_calls)}회)")

  # 5) 영상/교육 링크가 저장 데이터에 들어 있는지
  linked = [d for d in data if d["metadata"]["links"]]
  check("링크 포함 프로그램 존재", len(linked) > 0, f"({len(linked)}/{len(data)}건)")
  if linked:
    print(f"    예) {linked[0]['metadata']['title']}: {linked[0]['metadata']['links'][:2]}")

  print("\n검색 방식:", "벡터 + 키워드 대체" if search_vector else "키워드만 (벡터 DB 미사용)")
  print("=== 결과:", "모두 통과" if not failures else f"실패 {failures}", "===")
  sys.exit(1 if failures else 0)
