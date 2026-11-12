from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

EMBED_MODEL = "bge-m3"        # 자리표시자: 문서를 적재할 때 쓴 임베딩 모델과 같은 이름으로 바꾸세요
CHROMA_DIR = "./chroma_data"  # Chroma 데이터가 저장된 폴더

embeddings = OllamaEmbeddings(model=EMBED_MODEL)


def get_store(collection_name: str) -> Chroma:
    # 컬렉션(문서 묶음) 하나를 여는 함수
    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR,
        collection_metadata={"hnsw:space": "cosine"},
    )


def search_docs(collection_name: str, query: str, k: int = 4, threshold: float = 0.5):
    # query와 비슷한 문서를 최대 k개 찾고, 유사도가 threshold 이상인 것만 돌려준다
    store = get_store(collection_name)
    results = store.similarity_search_with_relevance_scores(query, k=k)

    for doc, score in results:
        print(f"[RAG] score={score:.3f} | {doc.page_content[:30]}")  # 임계값 정할 때 확인용

    return [doc for doc, score in results if score >= threshold]