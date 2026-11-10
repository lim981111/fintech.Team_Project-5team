import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import RedirectResponse

from app.graph.chat_service import answer_question, prepare_data

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
  # 서버 시작 시 1회: 저장된 데이터 확보 + 벡터 DB 준비
  # (저장된 데이터가 하나도 없을 때만 금감원 API 호출)
  prepare_data()
  yield


app = FastAPI(lifespan=lifespan)
app.mount("/view", StaticFiles(directory=BASE_DIR / "view"), name="view")


@app.get("/")
def main():
  return RedirectResponse(url="/view/index.html")


class ChatRequest(BaseModel):
  question: str = Field(..., min_length=1, max_length=500)
  age: int = 25
  job: str = ""
  monthly_income: int = 0
  total_assets: int = 1000000
  household_size: int = 1
  score: int = 50
  language: str = "ko"


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
  # 질문 처리 중에는 저장된 데이터만 사용 (금감원 API 호출 없음)
  return answer_question(req.question, req.job)