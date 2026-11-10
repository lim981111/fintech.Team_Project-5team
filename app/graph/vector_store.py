"""금감원 교육 데이터를 ChromaDB(벡터 DB)에 저장하고 검색하는 모듈.

사용법
  - 데이터 적재(재구축): 프로젝트 루트에서  python -m app.graph.vector_store
  - 검색:                from app.graph.vector_store import search_vector
"""

import hashlib
import logging
import os
from functools import lru_cache

import chromadb
from chromadb.utils import embedding_functions

# load_dotenv()가 api_ingestion 임포트 시 실행되므로, 아래 os.getenv보다 먼저 임포트
from app.graph.api_ingestion import (
    fetch_and_save_fss_data,
    get_fss_edu_rag_data,
    load_local_data,
)

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
CHROMA_DIR = os.getenv("CHROMA_DIR", os.path.join(BASE_DIR, "chroma_db"))
COLLECTION_NAME = "fss_edu"

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


def _get_collection():
  return _get_client().get_or_create_collection(
      name=COLLECTION_NAME,
      embedding_function=_get_embedding_function(),
      metadata={"hnsw:space": "cosine"},
  )


def _program_id(item):
  """제목+신청기간으로 만든 고정 ID (재실행해도 같은 프로그램은 같은 ID)"""
  meta = item.get("metadata", {})
  raw = f"{meta.get('title', '')}|{meta.get('period', '')}"
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


def ingest_fss_data(data, rebuild=True):
  """교육 프로그램 리스트를 청크로 나눠 벡터 DB에 저장. 저장된 청크 총 개수를 반환.

  rebuild=True 이면 기존 컬렉션을 지우고 새로 만들어, API에서 사라진 프로그램이
  벡터 DB에 남지 않도록 한다.
  """
  if not data:
    logger.warning("저장할 데이터가 없습니다.")
    return 0

  if rebuild:
    try:
      _get_client().delete_collection(COLLECTION_NAME)
    except Exception:
      pass  # 컬렉션이 아직 없으면 무시

  collection = _get_collection()

  ids, documents, metadatas = [], [], []
  seen = set()
  for item in data:
    pid = _program_id(item)
    if pid in seen:  # 제목+기간이 같은 중복 항목 방지 (Chroma는 배치 내 중복 ID 불가)
      logger.warning("중복 프로그램 건너뜀: %s", item["metadata"].get("title"))
      continue
    seen.add(pid)

    title = item["metadata"].get("title", "")
    for i, chunk in enumerate(_chunk_text(item.get("content", ""))):
      ids.append(f"{pid}:{i}")
      # 첫 청크에는 이미 프로그램명이 있으므로, 나머지 청크에만 제목을 붙여 문맥 유지
      documents.append(chunk if i == 0 else f"[{title}] {chunk}")
      metadatas.append({"program_id": pid, "title": title, "chunk": i})

  for start in range(0, len(ids), UPSERT_BATCH):
    end = start + UPSERT_BATCH
    collection.upsert(
        ids=ids[start:end],
        documents=documents[start:end],
        metadatas=metadatas[start:end],
    )

  total = collection.count()
  logger.info("벡터 DB 저장 완료: 프로그램 %d개 / 청크 %d개", len(seen), total)
  return total


def ensure_vector_db():
  """벡터 DB가 비어 있으면 캐시/API 데이터를 읽어 적재 (서버 시작 시 호출)"""
  if _get_collection().count() > 0:
    return
  data = get_fss_edu_rag_data()
  if not data:
    logger.warning("벡터 DB가 비어 있지만 적재할 원본 데이터도 없습니다.")
    return
  ingest_fss_data(data, rebuild=False)


def search_vector(query, top_k=4, data=None):
  """질문과 의미가 가까운 교육 프로그램을 반환 (원본 데이터 딕셔너리 형태 그대로)"""
  collection = _get_collection()
  count = collection.count()
  if count == 0 or not (query or "").strip():
    return []

  if data is None:
    data = load_local_data()  # 로컬 저장본만 사용 (API 호출 없음)
  by_id = {_program_id(d): d for d in data}

  # 한 프로그램이 여러 청크로 걸릴 수 있어 넉넉히 가져온 뒤 프로그램 단위로 합침
  res = collection.query(
      query_texts=[query],
      n_results=min(top_k * 3, count),
      include=["metadatas", "distances"],
  )

  results, seen = [], set()
  for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
    logger.debug("distance=%.3f title=%s", dist, meta.get("title"))
    if dist > MAX_DISTANCE:
      break  # 거리순 정렬이므로 이후는 모두 더 멀다
    pid = meta["program_id"]
    if pid in seen or pid not in by_id:
      continue
    seen.add(pid)
    results.append(by_id[pid])
    if len(results) >= top_k:
      break
  return results


# ==========================================
# 🧪 단독 실행: (선택) API 갱신 → 벡터 DB 재구축 → 검색 테스트
#   python -m app.graph.vector_store            # API로 최신 데이터 갱신 후 적재
#   python -m app.graph.vector_store --offline  # API 호출 없이 저장된 데이터로만 적재
# ==========================================
if __name__ == "__main__":
  import sys

  logging.basicConfig(level=logging.INFO)

  if "--offline" in sys.argv:
    source = load_local_data()
    print(f"[정보] 오프라인 모드: 저장된 데이터 {len(source)}건 사용")
  else:
    source = fetch_and_save_fss_data()  # 명시적 갱신 (실패 시 기존 저장본 유지)
    if not source:
      source = load_local_data()
      print(f"[경고] API 갱신 실패 - 기존 저장본 {len(source)}건으로 진행")
    else:
      print(f"[정보] API에서 {len(source)}건 갱신 후 저장")

  if not source:
    print("[중단] 적재할 데이터가 없습니다. FSS_API_KEY와 네트워크를 확인하세요.")
    sys.exit(1)

  total_chunks = ingest_fss_data(source, rebuild=True)
  print(f"[성공] 벡터 DB 저장 완료: 청크 {total_chunks}개 ({CHROMA_DIR})")

  for q in ("청년 투자", "대출 사기 예방", "노후 준비"):
    print(f"\n--- 검색 테스트: '{q}' ---")
    hits = search_vector(q, top_k=3, data=source)
    if not hits:
      print("  (결과 없음 - VECTOR_MAX_DISTANCE를 높여 보세요)")
    for h in hits:
      print(f"  - {h['metadata']['title']}")
