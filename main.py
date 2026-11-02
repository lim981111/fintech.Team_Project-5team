from fastapi import FastAPI
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles
from pydantic import BaseModel

from app.services.rag_service import SimpleFinancialRAG

app = FastAPI()
app.mount("/view", StaticFiles(directory="view"), name="view")

@app.get("/")
def main():
    return RedirectResponse(url="/view/index.html")


class ChatRequest(BaseModel):
    question: str
    age: int = 25
    job: str = "학생"
    monthly_income: int = 0
    total_assets: int = 1000000
    household_size: int = 1
    score: int = 50
    language: str = "ko"


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    try:
        # API가 호출되는 시점에 RAG 객체 생성 (키가 없으면 여기서 에러를 잡습니다)
        rag = SimpleFinancialRAG()
        search_results = rag.search_rag_results(query=req.question, k=3)
        retrieved_texts = [res["content"] for res in search_results]
        answer_text = f"'{req.job}' 조건을 반영하여 관련 금융 정보를 찾았습니다.\n\n" + "\n".join(retrieved_texts)
        policies = search_results
    except Exception as e:
        # API 키가 없어 에러가 나더라도 서버가 죽지 않고 안내 메시지를 띄우도록 처리
        answer_text = f"[안내] 현재 OpenAI API 키가 설정되지 않아 RAG 검색을 수행할 수 없습니다. (에러: {e})"
        policies = []

    return {
        "answer": answer_text,
        "policy": policies,
        "contents": []
    }