"""교육/복지 데이터를 ChromaDB(벡터 DB)에 저장하고 검색하는 모듈.

출처(source)마다 컬렉션을 따로 둔다.
    "edu"     → 컬렉션 fss_edu           (금감원 교육 프로그램)
    "welfare" → 컬렉션 welfare_services  (복지로 중앙부처복지서비스)
금융상품은 금리 정렬이 핵심이라 벡터 DB를 쓰지 않는다. (product_search.py)

사용법
  - 전체 갱신(API 호출 + 벡터 DB 재구축): python -m app.graph.ingest_all
  - 저장본으로 벡터 DB만 재구축(API 호출 없음): python -m app.graph.vector_store
"""

import hashlib
import logging
import os
from functools import lru_cache

import chromadb
from chromadb.utils import embedding_functions

# load_dotenv()가 임포트 시 실행되므로, 아래 os.getenv보다 먼저 임포트
from app.graph.api_ingestion import get_fss_edu_rag_data, load_local_data
from app.graph.welfare_ingestion import load_local_welfare

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
CHROMA_DIR = os.getenv("CHROMA_DIR", os.path.join(BASE_DIR, "chroma_db"))

COLLECTIONS = {"edu": "fss_edu", "welfare": "welfare_services"}

# 한국어 지원 임베딩 모델 (최초 실행 시 HuggingFace에서 다운로드됨)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")

# 코사인 거리 기준(작을수록 유사). 이보다 먼 결과는 버림. 실제 결과를 보며 조정하세요.
MAX_DISTANCE = float(os.getenv("VECTOR_MAX_DISTANCE", "0.8"))

CHUNK_SIZE = 500
CHUNK_OVERLAP = 80
UPSERT_BATCH = 100


@lru_cache(maxsize=1)
def _get_client():
  return chromadb.PersistentClient(path=CHROMA_DIR)


@lru_cache(maxsize=1)
def _get_embedding_function():
  # 모델 로딩이 무거우므로 한 번만 생성
  return embedding_functions.SentenceTransformerEmbeddingFunction(
      model_name=EMBEDDING_MODEL
  )


def _get_collection(source="edu"):
  return _get_client().get_or_create_collection(
      name=COLLECTIONS[source],
      embedding_function=_get_embedding_function(),
      metadata={"hnsw:space": "cosine"},
  )


def _item_id(item):
  """항목의 고정 ID (재실행해도 같은 항목은 같은 ID).

  복지는 서비스 ID(serv_id), 교육은 제목+프로그램 페이지 주소로 만든다.
  """
  meta = item.get("metadata", {})
  if meta.get("serv_id"):
    return "w" + str(meta["serv_id"])
  raw = f"{meta.get('title', '')}|{meta.get('url', '')}"
  return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
  """긴 본문을 겹치게 잘라, 임베딩이 뭉개지지 않도록 함"""
  text = (text or "").strip()
  if len(text) <= size:
    return [text] if text else []

  chunks = []
  start = 0
  while start < len(text):
    chunks.append(text[start : start + size])
    if start + size >= len(text):
      break
    start += size - overlap
  return chunks


def _load_items(source):
  """저장된 데이터를 읽는다. (교육은 저장본이 하나도 없을 때만 API를 1회 호출)"""
  if source == "welfare":
    return load_local_welfare()
  return get_fss_edu_rag_data()


def ingest_fss_data(data, rebuild=True, source="edu"):
  """항목 리스트를 청크로 나눠 벡터 DB에 저장. 저장된 청크 총 개수를 반환.

  rebuild=True 이면 기존 컬렉션을 지우고 새로 만들어, API에서 사라진 항목이
  벡터 DB에 남지 않도록 한다.
  """
  if not data:
    logger.warning("[%s] 저장할 데이터가 없습니다.", source)
    return 0

  if rebuild:
    try:
      _get_client().delete_collection(COLLECTIONS[source])
    except Exception:
      pass  # 컬렉션이 아직 없으면 무시

  collection = _get_collection(source)

  ids, documents, metadatas = [], [], []
  seen = set()
  for item in data:
    item_id = _item_id(item)
    if item_id in seen:  # Chroma는 배치 내 중복 ID 불가
      logger.warning("중복 항목 건너뜀: %s", item["metadata"].get("title"))
      continue
    seen.add(item_id)

    title = item["metadata"].get("title", "")
    for i, chunk in enumerate(_chunk_text(item.get("content", ""))):
      ids.append(f"{item_id}:{i}")
      # 첫 청크에는 이미 이름이 있으므로, 나머지 청크에만 제목을 붙여 문맥 유지
      documents.append(chunk if i == 0 else f"[{title}] {chunk}")
      metadatas.append({"program_id": item_id, "title": title, "chunk": i})

  for start in range(0, len(ids), UPSERT_BATCH):
    end = start + UPSERT_BATCH
    collection.upsert(
        ids=ids[start:end],
        documents=documents[start:end],
        metadatas=metadatas[start:end],
    )

  total = collection.count()
  logger.info("[%s] 벡터 DB 저장 완료: 항목 %d개 / 청크 %d개", source, len(seen), total)
  return total


def ensure_vector_db(source="edu"):
  """벡터 DB가 비어 있으면 저장된 데이터를 읽어 적재 (서버 시작 시 호출)"""
  if _get_collection(source).count() > 0:
    return
  data = _load_items(source)
  if not data:
    logger.warning("[%s] 벡터 DB가 비어 있지만 적재할 원본 데이터도 없습니다.", source)
    return
  ingest_fss_data(data, rebuild=False, source=source)


def search_vector(query, top_k=4, data=None, source="edu"):
  """질문과 의미가 가까운 항목을 반환 (원본 데이터 딕셔너리 형태 그대로)"""
  collection = _get_collection(source)
  count = collection.count()
  if count == 0 or not (query or "").strip():
    return []

  if data is None:
    data = load_local_welfare() if source == "welfare" else load_local_data()
  by_id = {_item_id(d): d for d in data}

  # 한 항목이 여러 청크로 걸릴 수 있어 넉넉히 가져온 뒤 항목 단위로 합침
  res = collection.query(
      query_texts=[query],
      n_results=min(top_k * 3, count),
      include=["metadatas", "distances"],
  )

  results, seen = [], set()
  for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
    logger.debug("[%s] distance=%.3f title=%s", source, dist, meta.get("title"))
    if dist > MAX_DISTANCE:
      break  # 거리순 정렬이므로 이후는 모두 더 멀다
    item_id = meta["program_id"]
    if item_id in seen or item_id not in by_id:
      continue
    seen.add(item_id)
    results.append(by_id[item_id])
    if len(results) >= top_k:
      break
  return results


# ==========================================
# 🧪 단독 실행: 저장본으로 벡터 DB 재구축 + 검색 테스트 (API 호출 없음)
#   API까지 새로 받으려면 `python -m app.graph.ingest_all` 을 사용하세요.
# ==========================================
if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO)

  tests = {
      "edu": ("청년 투자", "대출 사기 예방"),
      "welfare": ("청년 월세 지원", "출산 양육 지원"),
  }
  for source_name, queries in tests.items():
    source_data = load_local_welfare() if source_name == "welfare" else load_local_data()
    if not source_data:
      print(f"[{source_name}] 저장된 데이터가 없어 건너뜁니다.")
      continue

    chunks = ingest_fss_data(source_data, rebuild=True, source=source_name)
    print(f"[{source_name}] 저장 완료: 항목 {len(source_data)}건 / 청크 {chunks}개 ({CHROMA_DIR})")
    for q in queries:
      print(f"  --- 검색 테스트: '{q}' ---")
      hits = search_vector(q, top_k=3, data=source_data, source=source_name)
      if not hits:
        print("    (결과 없음 - VECTOR_MAX_DISTANCE를 높여 보세요)")
      for h in hits:
        print(f"    - {h['metadata']['title']}")