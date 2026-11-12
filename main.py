from fastapi import FastAPI,Request
from pydantic import BaseModel
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles
from langgraph.graph import START, END
from node_func import *
from state import *

app = FastAPI()

#app.mount("/view", StaticFiles(directory="view"))

wf = get_state()

wf.add_node("normal", normal_answer_node)
wf.add_node("rag", rag_answer_node)
wf.add_node("web", web_answer_node)

wf.add_conditional_edges(
    START,
    router,
    {
        'normal':'normal',
        'rag':'rag'
    }
)

wf.add_edge("normal", END)

wf.add_conditional_edges(
    "rag",
    check_answer,
    {"web": "web", "end": END},
)

wf.add_edge("web", END)

money = wf.compile()

@app.get("/")
def main():
    return RedirectResponse("http://localhost:8000/docs")

# post 실험용 포장
class ChatRequest(BaseModel):
    question: str
    age: int
    job: str
    monthly_income: int
    total_assets: int
    household_size: int
    score: int

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    #body = await request.json() # 프론트나 /docs에서 보낸 JSON을 통째로 받음
    
    initial_state = {
        "question": req.question,
        "age": req.age,
        "job": req.job,
        "monthly_income": req.monthly_income,
        "total_assets": req.total_assets,
        "household_size": req.household_size,
        "score": req.score,
        "answer": ""
    }
    
    result = money.invoke(initial_state)
    return {"answer": result.get("answer", "")}