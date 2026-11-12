from fastapi import FastAPI
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles
from langgraph.graph import START, END
from node_func import *
from state import *

app = FastAPI()

app.mount("/view", StaticFiles(directory="view"))

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

gold = wf.compile()

@app.get("/")
def main():
    return RedirectResponse("/view/index.html")