from typing import Any, List, TypedDict

from langgraph.graph import StateGraph

class State(TypedDict):
    question:str        #질문&유저상태
    answer:str          #AI답변

    age : int           #나이
    job : str           #직업
    mouthly_income : int#월 소득
    total_assets : int  #총 자산
    household_size : int#가족 구성원 수
    score : int         #금융 이해도 점수

    policy : List[Any]  #취약계층 정책rag검색결과
    data : list[Any]    #금융정보 rag검색결과
    contents : List[Any]#금융교육 콘텐츠
    language : str      #다국어 지원용


def get_state():
    return StateGraph(State)

#id, pw는 세션스토리지에서