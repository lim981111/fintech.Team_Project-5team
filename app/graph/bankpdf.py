import os

import chromadb
from llama_index.core import Settings, StorageContext, VectorStoreIndex, SimpleDirectoryReader
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore

from llama_index.readers.file import PyMuPDFReader


# 1. 모델등록, chunk size 등록
Settings.llm = Ollama(model="gemma4:e4b", request_timeout=300)
Settings.embed_model = OllamaEmbedding(model_name="bge-m3")
Settings.chunk_size = 300
Settings.chunk_overlap = 50

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
    VectorStoreIndex.from_documents(pages, storage_context=ctx, show_progress=True)
    print(f'완료. 저장된 청크 수 : {coll.count()}')

#insert_data()
#print(coll.get())

# 5. 검색기 버전으로 결과값 불러오기

def rag_search(query:str):
    ret = index.as_retriever(simiarity_top_ke=5)
    nodes = ret.retrieve(query)
    resp = ''
    for node_with_score in nodes:
        resp += f"{node_with_score.node.get_content()}"
    return resp

result = rag_search("가계부실위험지수")
print(result)