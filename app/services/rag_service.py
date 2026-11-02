import os
from typing import List, Dict, Any
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings


class SimpleFinancialRAG:
    def __init__(self, persist_directory: str = "./chroma_db"):
        # 임베딩 모델 초기화 (API 키 필요)
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

        # Vector DB (Chroma) 연결
        self.vector_store = Chroma(
            collection_name="financial_platform_docs",
            embedding_function=self.embeddings,
            persist_directory=persist_directory
        )

    def upsert_api_data(self, raw_items: List[Dict[str, Any]]):
        """
        [DB 저장 기능]
        API로 수집한 대량의 데이터를 Vector DB에 적재합니다.
        raw_items 예시: [{"id": "1", "title": "...", "target": "청년", "summary": "...", "url": "..."}, ...]
        """
        texts = []
        metadatas = []
        ids = []

        for item in raw_items:
            item_id = str(item.get("id"))
            title = item.get("title", "")
            target = item.get("target", "일반")
            summary = item.get("summary", "")
            url = item.get("url", "")

            # RAG 검색 정확도를 위한 텍스트 청크 조합
            text_chunk = f"[제목: {title}] 대상: {target} / 내용: {summary}"

            # 메타데이터로 출처 및 카테고리 관리 (RDB 테이블 불필요)
            metadata = {
                "source_id": item_id,
                "title": title,
                "target_category": target,
                "source_url": url
            }

            texts.append(text_chunk)
            metadatas.append(metadata)
            ids.append(item_id)

        if texts:
            self.vector_store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
            print(f"[RAG] 데이터 {len(texts)}건 Vector DB 적재 완료")

    def search_rag_results(self, query: str, target_category: str = None, k: int = 3) -> List[Dict[str, Any]]:
        """
        [RAG 결과물 추출 기능]
        챗봇이나 교육 페이지 백엔드 로직에서 검색이 필요할 때
        이 함수를 호출하여 RAG 결과물(내용 + 출처) 리스트를 받아갑니다.
        """
        # 타겟 카테고리 필터링이 필요할 경우 적용
        search_filter = {"target_category": target_category} if target_category else None

        docs = self.vector_store.similarity_search(
            query=query,
            k=k,
            filter=search_filter
        )

        results = []
        for doc in docs:
            results.append({
                "content": doc.page_content,  # RAG 검색된 텍스트 내용
                "metadata": doc.metadata  # source_url, title 등 출처 정보
            })

        return results