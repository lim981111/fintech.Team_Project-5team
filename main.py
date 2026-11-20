from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import RedirectResponse
from fastapi import HTTPException 
from langgraph.graph import START, END
from node_func import *
from sidebar_ai import *
from state import *
from all_db.DB import *

app = FastAPI()



app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

side_wf = get_side_state()

side_wf.add_node("init", init_answer)
side_wf.add_node("last", last_answer)

side_wf.set_entry_point("init")

side_wf.add_edge("init", "last")
side_wf.add_edge("last", END)

side = side_wf.compile()

init_db()

@app.get("/")
def main():
    return RedirectResponse("http://localhost:8000/docs")

@app.get("/chats")
def get_chats(user_id : int) : 
    return list_chats(user_id)

@app.get("/chats/{chat_id}")
def get_chat_messages(chat_id: int):
    return get_messages(chat_id)

@app.get("/users/{user_id}")
def read_user(user_id: int):
    user = get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return {"name": user["name"]}

# post 포장
class ChatRequest(BaseModel):
    question: str
    user_id : int
    chat_id : int | None = None

@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    #body = await request.json() # 프론트나 /docs에서 보낸 JSON을 통째로 받음
    user = get_user(req.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    
    if req.chat_id is None:
        chat_id = create_chat(req.user_id, req.question[:20])
        rows = []
    else:
        chat_id = req.chat_id
        rows = get_messages(chat_id)[-3:]                       # 최근 3쌍

    lines = []
    for r in rows:
        lines.append(f"사용자: {r['question']}")
        lines.append(f"AI: {(r['answer'] or '')[:200]}")        # 답변은 앞 200자만
    history = "\n".join(lines) or "(이전 대화 없음)"

    last_q = rows[-1]["question"] if rows else ""
    search_query = f"{last_q} {req.question}".strip() if len(req.question) < 15 else req.question

    initial_state = {
        "question": req.question,
        "name" : user["name"],
        "age": user["age"],
        "job": user["job"],
        "monthly_income": user["monthly_income"],
        "total_assets": user["total_assets"],
        "household_size": user["household_size"],
        "score": user["score"],
        "answer": "",
        "history" : history,
        "search_query": search_query,
    }
    
    result = money.invoke(initial_state)
    answer = result.get("answer", "")

    add_message(chat_id, req.question, answer)   
    return {"answer": answer, "chat_id": chat_id}  

class SideChatRequest(BaseModel):
    question: str

@app.post("/side_chat")
def side_chat_endpoint(req: SideChatRequest):
    
    side_state = {
        "question": req.question,
        "answer": "",
        "language": "ko",
        "contents": ""
    }
    
    result = side.invoke(side_state)
    return {"answer": result.get("answer", "")}

@app.delete("/chats/{chat_id}")
def remove_chat(chat_id: int, user_id: int):
    if delete_chat(chat_id, user_id) == 0:
        raise HTTPException(status_code=404, detail="상담 기록을 찾을 수 없습니다")
    return {"ok": True}


@app.get("/edu/contents")
def edus_list() :
    i = list_mp4()

    transformation = []
    for j in i:
        transformation.append ({
                "id": j["contents_slno"],
                "title" : j["title"],
                "thumbnail": j["thumb_url"],
                "video_url": j["video_url"],
                "minutes": j["play_seconds"] // 60,
                "source": EDU_ORG.get(j["org_code"], "기타")
        })

    return transformation


"""
class UserCreate(BaseModel):
    name: str
    age: int
    job: str
    monthly_income: int
    total_assets: int
    household_size: int

@app.post("/users")
def create_user(req: UserCreate):
    user_state = {
            "name" : req.name,
            "age": req.age,
            "job": req.job,
            "monthly_income": req.monthly_income,
            "total_assets": req.total_assets,
            "household_size": req.household_size
        }

    chat_id = create_chat(req.user_id, req.question[:20])
    create_user
"""