import os
import time

import chromadb
from dotenv import load_dotenv
from llama_index.core import Settings, StorageContext, VectorStoreIndex, SimpleDirectoryReader
from llama_index.vector_stores.chroma import ChromaVectorStore

from llama_index.readers.file import PyMuPDFReader

from llama_index.llms.google_genai import GoogleGenAI
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding

load_dotenv()
api_key = os.getenv("google_api_key")

# 1. 모델등록, chunk size 등록
Settings.llm = GoogleGenAI(model="gemini-3.8-flash", api_key=api_key)
Settings.embed_model = GoogleGenAIEmbedding(model_name="models/gemini-embedding-001", api_key=api_key)
Settings.chunk_size = 700
Settings.chunk_overlap = 80

# 2. chromadb 등록
client = chromadb.PersistentClient("store")
coll = client.get_or_create_collection("store")
# llama-index 와 연동
store = ChromaVectorStore(chroma_collection=coll)
# 3-1. llama-index 저장만을 위한 객체
ctx = StorageContext.from_defaults(vector_store=store)
# 3. llam-index 검색을 위한 객체
index = VectorStoreIndex.from_vector_store(store)


# 4. 데이터 삽입
def insert_data():
    print('PDF 읽는 중')

    # 1. PDF 파일 읽기 (PyMuPDFReader 사용)
    loader = PyMuPDFReader()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_path = os.path.normpath(os.path.join(current_dir, "../../한국은행 경제금융용어 700선.pdf"))
    documents = loader.load(file_path=pdf_path)

    # 2. 제대로 읽혔는지 먼저 눈으로 확인! (DB에 넣기 전 필수 테스트)
    print(documents[10].text[:300])


    #reader = SimpleDirectoryReader(input_files=["한국은행 경제금융용어 700선.pdf"])
    #pages = reader.load_data()
    pages = documents
    print('읽어온 데이터 인덱싱 작업(청킹+ 백터화)')
    #VectorStoreIndex.from_documents(pages, storage_context=ctx, show_progress=True)
    pages = documents
    nodes = Settings.node_parser.get_nodes_from_documents(pages)   # 청킹
    print(f'청크 수: {len(nodes)}')

    BATCH = 20                       # 분당 100건 한도보다 여유 있게
    start = coll.count()             # 이미 저장된 개수부터 이어서 (중간에 멈춰도 재개 가능)
    for i in range(start, len(nodes), BATCH):
        index.insert_nodes(nodes[i:i + BATCH])
        print(f'{min(i + BATCH, len(nodes))}/{len(nodes)}')
        time.sleep(30)               # 1분 창이 지나길 기다림
    print(f'완료. 저장된 청크 수 : {coll.count()}')

#insert_data()
#print(coll.get())

# 5. 검색기 버전으로 결과값 불러오기

def rag_search(query:str):
    ret = index.as_retriever(similarity_top_k=5)
    nodes = ret.retrieve(query)
    resp = ''
    for node_with_score in nodes:
        resp += f"{node_with_score.node.get_content()}"
    return resp

#result = rag_search("가계부실위험지수")
#print(result)

#print(coll.count())