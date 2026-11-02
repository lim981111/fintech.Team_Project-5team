from langgraph.graph import StateGraph, END
from app.graph.state import State

def retrieve_policy_node(state: State) -> State:
    # TODO: Vector DB 검색 연동
    state["policy"] = ["청년 지원 정책 정보"]
    return state

def retrieve_education_node(state: State) -> State:
    # TODO: 금감원 API / Vector DB 검색 연동
    state["contents"] = ["[금감원] 기초 금융 교육 과정"]
    return state

def generate_answer_node(state: State) -> State:
    q = state.get("question", "")
    state["answer"] = f"AI 답변: '{q}'에 대한 맞춤형 금융 안내입니다."
    return state

def create_financial_graph():
    workflow = StateGraph(State)

    workflow.add_node("retrieve_policy", retrieve_policy_node)
    workflow.add_node("retrieve_education", retrieve_education_node)
    workflow.add_node("generate_answer", generate_answer_node)

    workflow.set_entry_point("retrieve_policy")
    workflow.add_edge("retrieve_policy", "retrieve_education")
    workflow.add_edge("retrieve_education", "generate_answer")
    workflow.add_edge("generate_answer", END)

    return workflow.compile()