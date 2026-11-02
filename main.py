from fastapi import FastAPI
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()
app.mount("/view", StaticFiles(directory="view"), name="view")

app_graph = create_financial_graph()


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
    initial_state = State(
        question=req.question,
        answer="",
        age=req.age,
        job=req.job,
        monthly_income=req.monthly_income,
        total_assets=req.total_assets,
        household_size=req.household_size,
        score=req.score,
        policy=[],
        data=[],
        contents=[],
        language=req.language
    )

    final_state = app_graph.invoke(initial_state)
    return {
        "answer": final_state["answer"],
        "policy": final_state["policy"],
        "contents": final_state["contents"]
    }