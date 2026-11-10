"""질문 → 답변 생성 로직 (교육 / 복지 / 금융상품).

FastAPI와 분리해 두었기 때문에 POST 요청 없이 이 파일만 실행해서 검증할 수 있다.
    python -m app.graph.chat_service

중요: 질문을 처리하는 동안에는 저장된 로컬 데이터만 사용하며, 어떤 외부 API도 호출하지 않는다.
      (API 갱신은 `python -m app.graph.ingest_all` 에서만)
"""

import logging
import re
from urllib.parse import urlparse

from app.graph.api_ingestion import (
    get_fss_edu_rag_data,
    load_local_data,
    search_fss_edu,
)
from app.graph.finlife_ingestion import load_local_products, load_products_info
from app.graph.product_search import flatten_rows, format_products, search_products
from app.graph.router import route_question
from app.graph.welfare_ingestion import load_local_welfare

logger = logging.getLogger(__name__)

# 벡터 DB 패키지(chromadb 등)가 없거나 문제가 있어도 키워드 검색으로 계속 동작
try:
  from app.graph.vector_store import ensure_vector_db, search_vector
except Exception as e:  # noqa: BLE001
  ensure_vector_db = None
  search_vector = None
  logger.warning("벡터 검색을 사용할 수 없습니다 (%s). 키워드 검색으로 대체합니다.", e)

TOP_K = 4
WELFARE_CANDIDATES = 12  # 대상(청년 등)으로 순서를 조정하기 위해 넉넉히 가져올 후보 수
NOT_READY_MESSAGE = "요청하신 데이터가 아직 준비되지 않았습니다. 잠시 후 다시 시도해 주세요."
SECTION_DIVIDER = "\n\n──────────\n\n"
WELFARE_NOTICE = "※ 지원 대상과 신청 방법은 바뀔 수 있으니 복지로 등 공식 안내에서 확인하세요."


def prepare_data():
  """서버 시작 시 1회 호출: 저장된 데이터 확인 + 벡터 DB 준비.

  교육은 저장본이 하나도 없을 때만 API를 1회 호출한다.
  복지와 금융상품은 호출이 많아 시작 시 받지 않으므로, 없으면 안내만 남긴다.
  """
  edu = get_fss_edu_rag_data()
  if not edu:
    logger.error(
        "저장된 교육 데이터가 없습니다. FSS_API_KEY/네트워크 확인 후"
        " `python -m app.graph.ingest_all`을 실행하세요."
    )
  welfare = load_local_welfare()
  if not welfare:
    logger.warning("저장된 복지 데이터가 없습니다. `python -m app.graph.ingest_all --only welfare`를 실행하세요.")
  if not load_local_products():
    logger.warning("저장된 금융상품 데이터가 없습니다. `python -m app.graph.ingest_all --only products`를 실행하세요.")

  if ensure_vector_db is not None:
    for source, has_data in (("edu", bool(edu)), ("welfare", bool(welfare))):
      if not has_data:
        continue
      try:
        ensure_vector_db(source)
      except Exception:
        logger.exception("[%s] 벡터 DB 준비 실패 - 키워드 검색으로 대체합니다.", source)


def search_documents(query, data, top_k=TOP_K, source="edu", allow_general=True):
  """(결과 리스트, 사용된 검색 방식)을 반환. 방식: 'vector' | 'keyword' | 'general' | 'none'"""
  if search_vector is not None:
    try:
      results = search_vector(query, top_k=top_k, data=data, source=source)
      if results:
        return results, "vector"
    except Exception:
      logger.exception("벡터 검색 실패 - 키워드 검색으로 대체합니다.")

  results = search_fss_edu(query, data, top_k=top_k)
  if results:
    return results, "keyword"

  if allow_general:
    return data[:top_k], "general"
  return [], "none"


# ---------- 링크 ----------
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


def _link_label(res, url, link_type):
  """화면에 보여줄 링크 설명"""
  if link_type == "video":
    return "영상"
  if str(res.get("source", "")).startswith("복지"):
    return "복지로 상세" if url == res["metadata"].get("url") else "신청·관련 사이트"
  return "교육 페이지"


def build_contents(results):
  """검색된 항목들의 링크를 프론트에서 바로 쓸 수 있는 목록으로 만든다.

  형태: [{"title": 이름, "url": 링크, "type": "video" | "link", "label": 설명}, ...]
  영상 링크가 앞에 오고, 같은 URL은 한 번만 포함한다.
  """
  contents, seen = [], set()
  for res in results:
    title = res["metadata"].get("title", "")
    for url in res["metadata"].get("links", []):
      if url in seen:
        continue
      seen.add(url)
      link_type = _link_type(url)
      contents.append({
          "title": title,
          "url": url,
          "type": link_type,
          "label": _link_label(res, url, link_type),
      })
  contents.sort(key=lambda c: c["type"] != "video")  # 정렬은 안정적이라 기존 순서 유지
  return contents


# ---------- 질문 속 대상 ----------
# 질문에 이런 단어가 있으면 해당 대상을 위한 질문으로 보고 안내 문구에 반영한다.
# (정규식: '(?<!대)학생'은 '대학생'을 제외한 '학생')
AUDIENCE_PATTERNS = {
    "청년": ("청년", "대학생", "사회초년생", "취준", "취업준비"),
    "학생": ("(?<!대)학생", "청소년"),
    "어르신": ("어르신", "노인", "노후", "고령", "시니어", "은퇴"),
    "소상공인": ("소상공인", "자영업", "사업자", "창업"),
    "직장인": ("직장인", "회사원", "월급"),
    "주부": ("주부", "육아", "신혼", "맞벌이"),
    "장애인": ("장애인",),
    "외국인": ("외국인", "이주민", "다문화"),
}

# 질문 속 대상 → 복지 데이터의 분류값. 복지 결과의 순서를 조정하는 데만 쓴다.
# (실제 분류값은 `python -m app.graph.ingest_all` 출력의 '값 목록'에서 확인하고 필요하면 고치세요)
AUDIENCE_TO_WELFARE = {
    "청년": {"life": ("청년",)},
    "학생": {"life": ("청소년", "아동")},
    "어르신": {"life": ("노년",)},
    "장애인": {"household": ("장애인",)},
    "외국인": {"household": ("다문화·탈북민",)},
}


def detect_audience(question):
  """질문 속 키워드로 대상(청년, 소상공인 등)을 찾아 라벨 목록으로 반환"""
  question = question or ""
  return [
      label
      for label, patterns in AUDIENCE_PATTERNS.items()
      if any(re.search(pat, question) for pat in patterns)
  ]


def _audience_bonus(item, audience):
  meta = item["metadata"]
  bonus = 0
  for label in audience:
    rule = AUDIENCE_TO_WELFARE.get(label)
    if not rule:
      continue
    if any(v in meta.get("life", []) for v in rule.get("life", ())) or any(
        v in meta.get("household", []) for v in rule.get("household", ())
    ):
      bonus += 1
  return bonus


# ---------- 출처별 답변 조각 ----------
def _edu_section(question, job, audience):
  data = load_local_data()  # 로컬 저장본만 읽음 (API 호출 없음)
  if not data:
    return None

  # 직업이 입력되지 않았으면 검색어에 넣지 않는다 (기본값이 검색을 치우치게 하는 것 방지)
  results, route = search_documents(f"{question} {job}".strip(), data, source="edu")

  if route == "general":
    intro = (
        "질문과 직접 일치하는 교육은 찾지 못해, 금감원의 일반 금융 교육"
        " 프로그램을 안내합니다."
    )
  elif job:
    intro = (
        f"'{job}' 조건과 질문을 반영하여 관련 금융 교육"
        f" {len(results)}건을 찾았습니다."
    )
  elif audience:
    intro = (
        f"질문에서 '{', '.join(audience)}' 관련 내용을 반영하여 관련 금융 교육"
        f" {len(results)}건을 찾았습니다."
    )
  else:
    intro = f"질문과 관련된 금융 교육 {len(results)}건을 찾았습니다."

  # 답변에는 간단한 본문(display_text)을 쓰고, 없으면 전체 본문을 쓴다
  texts = [res.get("display_text") or res["content"] for res in results]
  return intro + "\n\n" + "\n\n---\n\n".join(texts), results


def _welfare_section(question, audience):
  data = load_local_welfare()
  if not data:
    return None

  candidates, route = search_documents(
      question, data, top_k=WELFARE_CANDIDATES, source="welfare", allow_general=False
  )
  if route == "none" and audience:
    # 단어가 맞는 항목이 없어도, 질문 속 대상(청년 등)에 해당하는 서비스는 보여준다
    candidates = [d for d in data if _audience_bonus(d, audience) > 0][:WELFARE_CANDIDATES]

  # 대상에 맞는 서비스를 앞으로 (정렬은 안정적이라 나머지 순서는 유지)
  results = sorted(candidates, key=lambda d: -_audience_bonus(d, audience))[:TOP_K]
  if not results:
    return "질문과 맞는 복지 서비스를 찾지 못했습니다.", []

  if audience:
    intro = (
        f"질문에서 '{', '.join(audience)}' 관련 내용을 반영하여 관련 복지 서비스"
        f" {len(results)}건을 찾았습니다."
    )
  else:
    intro = f"질문과 관련된 복지 서비스 {len(results)}건을 찾았습니다."

  texts = [res.get("display_text") or res["content"] for res in results]
  return intro + "\n\n" + "\n\n---\n\n".join(texts) + "\n\n" + WELFARE_NOTICE, results


def _products_section(question):
  items = load_local_products()
  if not items:
    return None
  groups = search_products(question, items)
  return format_products(groups, load_products_info().get("dcls_month")), flatten_rows(groups)


def answer_question(question, job=""):
  """질문에 대한 응답(dict)을 만든다. /api/chat 응답과 같은 형태.

  answer   : 화면에 보여줄 답변 문장
  policy   : 관련 교육/복지 서비스 이름 목록 (문자열)
  programs : 교육 프로그램 전체 정보
  welfare  : 복지 서비스 전체 정보
  products : 금융상품 금리 비교 행
  contents : 링크 목록 [{title, url, type, label}]
  """
  job = (job or "").strip()
  audience = detect_audience(question)
  sources = route_question(question)

  sections, unavailable = [], []
  programs, welfare, products = [], [], []

  for source in sources:
    if source == "products":
      built = _products_section(question)
      if built:
        sections.append(built[0])
        products = built[1]
    elif source == "welfare":
      built = _welfare_section(question, audience)
      if built:
        sections.append(built[0])
        welfare = built[1]
    else:
      built = _edu_section(question, job, audience)
      if built:
        sections.append(built[0])
        programs = built[1]
    if not built:
      unavailable.append(source)

  if not sections:
    return {
        "answer": NOT_READY_MESSAGE,
        "policy": [],
        "programs": [],
        "welfare": [],
        "products": [],
        "contents": [],
    }

  if unavailable:
    names = {"edu": "교육", "welfare": "복지", "products": "금융상품"}
    sections.append(
        "(" + ", ".join(names[s] for s in unavailable) + " 데이터는 아직 준비되지 않았습니다.)"
    )

  return {
      "answer": SECTION_DIVIDER.join(sections),
      # 화면의 '관련 교육/정책'에 그대로 출력되는 값이라 문자열(이름) 목록으로 보낸다
      "policy": [r["metadata"].get("title", "") for r in programs + welfare],
      "programs": programs,
      "welfare": welfare,
      "products": products,
      "contents": build_contents(programs + welfare),
  }


# ==========================================
# 🧪 자체 검증 (POST 없이 실행): python -m app.graph.chat_service
#   먼저 `python -m app.graph.ingest_all`로 데이터를 저장해 두세요.
#   복지/금융상품 데이터가 없으면 해당 검사는 [SKIP]으로 표시됩니다.
# ==========================================
if __name__ == "__main__":
  import sys

  import requests

  from app.graph import api_ingestion, finlife_ingestion, welfare_ingestion
  from app.graph.product_search import parse_query

  logging.basicConfig(level=logging.INFO)
  failures = []

  def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}".rstrip())
    if not ok:
      failures.append(name)

  def skip(name, why):
    print(f"[SKIP] {name} ({why})")

  # 1) 저장된 데이터 로드
  edu_data = load_local_data()
  welfare_data = load_local_welfare()
  product_data = load_local_products()
  check("교육 데이터 로드", len(edu_data) > 0, f"({len(edu_data)}건)")
  print(f"[정보] 복지 {len(welfare_data)}건, 금융상품 {len(product_data)}건")
  if not edu_data:
    print("\n[중단] 저장된 교육 데이터가 없습니다. `python -m app.graph.ingest_all`을 먼저 실행하세요.")
    sys.exit(1)

  # 2) 질문 속 대상 감지
  for q, expected in [
      ("청년 관련 정책", ["청년"]),
      ("대학생 투자 교육", ["청년"]),           # '대학생'이 '학생'으로 중복 감지되면 안 됨
      ("중학생 금융교육", ["학생"]),
      ("소상공인 지원 정책", ["소상공인"]),
      ("청년 소상공인 대출", ["청년", "소상공인"]),
      ("스미싱 문자가 왔어요", []),
  ]:
    got = detect_audience(q)
    check(f"대상 감지 '{q}'", got == expected, f"-> {got}")

  # 3) 질문 분기
  for q, expected in [
      ("적금 금리 높은 곳 알려줘", ["products"]),
      ("청년 복지 지원금 뭐가 있어?", ["welfare"]),
      ("스미싱 예방 교육 알려줘", ["edu"]),
      ("청년 적금 금리랑 지원금 알려줘", ["products", "welfare"]),
      ("안녕하세요", ["edu"]),
  ]:
    got = route_question(q)
    check(f"질문 분기 '{q}'", got == expected, f"-> {got}")

  # 4) 금융상품 질문 해석
  for q, expected in [
      ("12개월 정기예금 금리", (["deposit"], 12)),
      ("적금 1년 이자 높은 곳", (["saving"], 12)),
      ("예적금 금리 비교", (["deposit", "saving"], None)),
      ("금리 높은 곳", (["deposit", "saving"], None)),
  ]:
    got = parse_query(q)
    check(f"금융상품 질문 해석 '{q}'", got == expected, f"-> {got}")

  # 5) 질문 처리 중 외부 API 호출 감시: requests.get이 불리면 실패 처리
  api_calls = []
  real_get = requests.get

  def _guard(*args, **kwargs):
    api_calls.append(args)
    raise AssertionError("질문 처리 중 외부 API가 호출되었습니다!")

  requests.get = _guard
  try:
    expected_keys = {"answer", "policy", "programs", "welfare", "products", "contents"}

    # 5-1) 교육
    for q, job in [
        ("청년이 투자를 시작하려면 어떤 교육을 들어야 해?", "학생"),
        ("대출 사기 예방 교육 알려줘", "직장인"),
        ("zzzz qqqq", "학생"),  # 일치 항목이 없는 질문 → 일반 안내로 떨어지는지
        ("청년 투자 교육 알려줘", ""),  # 직업 미입력 → 조건 문구 없음
    ]:
      resp = answer_question(q, job)
      shape_ok = (
          set(resp) == expected_keys
          and 0 < len(resp["programs"]) <= TOP_K
          and resp["welfare"] == [] and resp["products"] == []
          and all(isinstance(t, str) for t in resp["policy"])
          and all({"title", "url", "type", "label"} <= set(c) for c in resp["contents"])
          and len({c["url"] for c in resp["contents"]}) == len(resp["contents"])
      )
      check(f"[교육] 응답 형태 '{q}'", shape_ok, f"({len(resp['programs'])}건)")
      if not job:
        first_line = resp["answer"].split("\n\n")[0]
        check("[교육] 직업 미입력 시 '조건' 문구 없음", "조건" not in first_line, f"-> {first_line}")

    # 5-2) 복지
    if welfare_data:
      resp = answer_question("청년 복지 지원금 알려줘")
      check("[복지] 응답 형태", set(resp) == expected_keys and 0 < len(resp["welfare"]) <= TOP_K
            and resp["programs"] == [] and resp["products"] == [], f"({len(resp['welfare'])}건)")
      check("[복지] 이름이 policy에 포함", resp["policy"] == [w["metadata"]["title"] for w in resp["welfare"]])
      check("[복지] 안내 문구/복지로 링크",
            "복지 서비스" in resp["answer"] and any(c["label"] == "복지로 상세" for c in resp["contents"]))
      for w in resp["welfare"]:
        print(f"    - {w['metadata']['title']}  (생애주기: {', '.join(w['metadata']['life']) or '-'})")
    else:
      skip("복지 응답 검사", "저장된 복지 데이터 없음")

    # 5-3) 금융상품
    if product_data:
      resp = answer_question("12개월 정기예금 금리 높은 곳 알려줘")
      rows = resp["products"]
      rates = [r["rate_max"] if r["rate_max"] is not None else r["rate"] for r in rows]
      check("[금융상품] 응답 형태", set(resp) == expected_keys and 0 < len(rows) <= 5
            and resp["programs"] == [] and resp["welfare"] == [], f"({len(rows)}건)")
      check("[금융상품] 정기예금 12개월만, 금리 내림차순",
            all(r["kind_name"] == "정기예금" and r["term"] == 12 for r in rows) and rates == sorted(rates, reverse=True))
      check("[금융상품] 공시 기준월/유의 문구 포함", "공시 기준" in resp["answer"] and "권유" in resp["answer"])
      for r in rows:
        print(f"    - {r['company']} {r['name']}  기본 {r['rate']}% / 최고 {r['rate_max']}%")
    else:
      skip("금융상품 응답 검사", "저장된 금융상품 데이터 없음")

    # 5-4) 여러 출처가 섞인 질문
    if welfare_data and product_data:
      resp = answer_question("청년 적금 금리랑 지원금 알려줘")
      check("[복합] 금융상품과 복지가 함께 나옴", len(resp["products"]) > 0 and len(resp["welfare"]) > 0)
    else:
      skip("복합 질문 검사", "복지 또는 금융상품 데이터 없음")

    # 5-5) 저장 데이터가 없는 상황에서도 API를 호출하지 않고 안내 문구만 반환
    real_paths = (api_ingestion.CACHE_FILE, welfare_ingestion.CACHE_FILE, finlife_ingestion.CACHE_FILE)
    api_ingestion.CACHE_FILE = real_paths[0] + ".not_exist"
    welfare_ingestion.CACHE_FILE = real_paths[1] + ".not_exist"
    finlife_ingestion.CACHE_FILE = real_paths[2] + ".not_exist"
    try:
      for q in ("투자", "청년 복지 지원금", "정기예금 금리"):
        resp = answer_question(q)
        check(f"저장 데이터 없을 때 안내 문구 '{q}'",
              resp["answer"] == NOT_READY_MESSAGE and resp["policy"] == [] and resp["contents"] == [])
    finally:
      api_ingestion.CACHE_FILE, welfare_ingestion.CACHE_FILE, finlife_ingestion.CACHE_FILE = real_paths
  finally:
    requests.get = real_get

  check("질문 처리 중 외부 API 호출 0회", len(api_calls) == 0, f"(호출 {len(api_calls)}회)")

  # 6) 교육 데이터에 링크가 있는지
  linked = [d for d in edu_data if d["metadata"]["links"]]
  check("링크 포함 교육 프로그램 존재", len(linked) > 0, f"({len(linked)}/{len(edu_data)}건)")

  print("\n검색 방식:", "벡터 + 키워드 대체" if search_vector else "키워드만 (벡터 DB 미사용)")
  print("=== 결과:", "모두 통과" if not failures else f"실패 {failures}", "===")
  sys.exit(1 if failures else 0)