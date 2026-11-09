from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.responses import RedirectResponse

# 금감원 교육 데이터 수집 모듈 임포트
from api_ingestion import get_fss_edu_rag_data

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
  # 금감원 교육 데이터 수집
  fss_data = get_fss_edu_rag_data()

  if fss_data:
    retrieved_texts = [res["content"] for res in fss_data[:4]]
    answer_text = (
        f"'{req.job}' 조건을 반영하여 금감원 금융 교육 정보를"
        f" 불러왔습니다.\n\n" + "\n\n---\n\n".join(retrieved_texts)
    )
  else:
    answer_text = (
        "현재 금감원 교육 API에서 데이터를 불러오지 못했거나 검색 결과가 없습니다."
    )
    fss_data = []

  return {"answer": answer_text, "policy": fss_data, "contents": []}