from datetime import datetime
import os

from dotenv import load_dotenv
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_tavily import TavilySearch
from datetime import datetime

from state import State
from rag.rag_search import search_docs
#from llm_config import init_llm_settings
#from db_history import get_recent_history
#from data.region import get_region_code, get_sido_code
#from data.search import search_policies


load_dotenv()

# 모델1. router에서 분기에 사용할 LLM
route_llm = ChatOllama(model="gemma4:e4b", format='json')
# 모델2. 최종 응답을 해줄 LLM
llm = ChatOllama(model="gemma4:e4b",num_ctx=8192)

# 노드 설정

# 라우터
def router(state: State):
    print('router로 분류')
    sys_prompt = """
        당신은 사용자의 [질문]을 분석하여 올바른 답변 경로(Route)를 판단하는 라우팅전문가 입니다.
        
        [분류 기준]
        - normal : 아래에 해당하는 경우에만 선택
            · 인사, 잡담, 감정 표현(위로가 필요한 말, 짜증, 푸념)
            · 금융과 무관한 일상 질문
        - rag : 금융과 조금이라도 관련된 모든 질문

        [출력 규칙]
        - 반드시 JSON 형식으로 출력해야 합니다.
        - 다른 설명, 인사말, 마크다운(```)등은 일체 입력하지 마세요

        [출력 예시]
        {{"route": "normal"}}
        """
    
    human_prompt = "[질문]\n{question}"

    msg_list = [("system",sys_prompt),("human",human_prompt)]
    prompt = ChatPromptTemplate.from_messages(msg_list)
    chain = prompt|route_llm|JsonOutputParser()
    #{{"route":"rag"}}
    try:
        result = chain.invoke({'question': state['question']})
        route = result.get('route')
    except Exception:
        route = 'rag'

    if route not in ('normal', 'rag'):   # 이상한 값이 나온 경우도 방어
        route = 'rag'
    return route

# 일반응답
def normal_answer_node(state: State):
    print('일반 응답')
    sys_prompt = """
        당신은 어르신을 포함한 다양한 사용자와 편하게 대화하는 친절한 AI 도우미입니다.
        사용자의 [질문]을 분석하여 알고 있는 지식을 바탕으로 친절하게 답변해주세요
        사용자의 [나이]를 고려하여 이해하기 쉬운 단어와 문장으로 답변해주세요.
        일상 대화, 잡담, 감정표현(위로가 필요한 말, 짜증, 푸념)등에도 친절하게 답변해주세요.
        
        [출력 규칙]
        - 반드시 한국어로 답변하세요
        - 반드시 존댓말을 사용하세요
        - 확실하지 않은 내용은 추측하지 말고 모른다고 말하세요.
        - 최대한 쉬운 단어와 문장으로 답변하세요.
        - 사용자가 힘들거나 짜증을 내면 해결책보다 공감과 위로를 먼저 해주세요.
        """

    human_prompt = "[질문]\n{question}\n\n[나이]\n{age}"

    msg_list = [("system",sys_prompt),("human",human_prompt)]
    prompt = ChatPromptTemplate.from_messages(msg_list)
    chain = prompt|llm| StrOutputParser()

    result = chain.invoke({
        "question":state['question'],
        "age":state['age']
    })

    return {"answer": result}


# 중위소득
MEDIAN_INCOME = {
    1: 2564238,
    2: 4199292,
    3: 5359036,
    4: 6494738,
    5: 7556719,
    6: 8555952,
}


def get_income_ratio(income: int, household_size: int):
    median = MEDIAN_INCOME.get(household_size)

    if median is None:   # 7인 이상 등 표에 없는 경우
        return None

    return income / median * 100

# rag 응답
def rag_answer_node(state: State):
    print('rag 검색 후 응답')
    policy_docs = search_docs("policy", state['question'])    
    data_docs = search_docs("data", state['question'])
    policy = "\n\n".join(d.page_content for d in policy_docs) or "(관련 자료 없음)"
    data = "\n\n".join(d.page_content for d in data_docs) or "(관련 자료 없음)"

    ratio = get_income_ratio(state['monthly_income'], state['household_size']) 

    # [추가] 7인 이상 등 비율을 못 구한 경우 "None%"가 나가지 않게 처리
    ratio_text = f"기준 중위소득의 약 {round(ratio)}%" if ratio is not None else "알 수 없음"

    sys_prompt = """
        당신은 주어진 [정책]과 [금융정보]를 바탕으로 질문에 답하는 금융 전문 상담전문가 입니다.
        사용자의 [나이],[직업],[월 소득],[총 자산],[가족 구성원 수]를 고려하고,
        특히 사용자의 [중위소득비율]을 고려하여 답변해주세요.
        [중위소득비율]은 이미 계산된 값이니 직접 다시 계산하지 마세요.
        
        [정책]과 [금융정보]를 바탕으로 사용자가 이해하기 쉬운 단어와 문장으로 친절하게 답변해주세요.
        [정책]과 [금융정보]가 모두 "(관련 자료 없음)"이거나, 질문에 답하기에 자료가 부족하다면
        다른 말은 하지 말고 반드시 빈칸("")만 답하세요
        
        [출력 규칙]
        - 반드시 한국어로 답변하세요
        - 반드시 존댓말을 사용하세요
        - 확실하지 않은 내용은 추측하지 마세요
        - 최대한 쉬운 단어와 문장으로 답변하세요

        
        [사용자 정보]
        - 나이 : {age}세
        - 직업 : {job}
        - 월 소득 : {monthly_income}원
        - 총 자산 : {total_assets}원
        - 가족 구성원 수 : {household_size}명
        - 금융 이해도 점수 : {score}점
        - 중위소득비율 : {ratio_text}

        [정책]
        {policy}

        [금융정보]
        {data}
    """
    human_prompt = "[질문]\n{question}"

    msg_list = [("system", sys_prompt), ("human", human_prompt)]
    prompt = ChatPromptTemplate.from_messages(msg_list)
    chain = prompt | llm | StrOutputParser()

    result = chain.invoke({
        "question": state['question'],
        "age": state['age'],
        "job": state['job'],
        "monthly_income": f"{state['monthly_income']:,}",
        "total_assets": f"{state['total_assets']:,}",
        "household_size": state['household_size'],
        "score": state['score'],
        "ratio_text": ratio_text,
        "policy": policy,
        "data": data,
    })
    return {"answer": result}

def check_answer(state: State):
    answer = state['answer'].strip().strip('"\'')   # 공백과 따옴표를 벗겨서
    return "web" if answer == "" else "end"
    
# tavily 응답
def web_answer_node(state:State):
    print('tavily로 web검색 후 응답')

    

    # web_answer_node 내부에서 오늘 날짜 생성
    today = datetime.now().strftime("%Y년 %m월 %d일")

    ratio = get_income_ratio(state['monthly_income'], state['household_size'])
    ratio_text = f"기준 중위소득의 약 {round(ratio)}%" if ratio is not None else "알 수 없음"

    question = state['question']
    search = TavilySearch(max_results=3,search_depth='basic', topic='general')
    result = search.invoke({'query':question})
    text = ''
    for r in result['results']:
        text += f"{r['title']}\n{r['url']}\n{r['content'][:800]}\n\n"

    sys_prompt = """
        당신은 주어진 [웹 검색 결과]를 바탕으로 질문에 답하는 금융 전문 상담전문가 입니다.
        사용자의 [나이],[직업],[월 소득],[총 자산],[가족 구성원 수]를 고려하고,
        특히 사용자의 [중위소득비율]을 고려하여 답변해주세요.
        [중위소득비율]은 이미 계산된 값이니 직접 다시 계산하지 마세요.
        
        [웹 검색 결과]를 바탕으로 사용자가 이해하기 쉬운 단어와 문장으로 친절하게 답변해주세요.
        [웹 검색 결과]가 질문에 답하기에 자료가 부족하다면 
        "찾지 못했습니다. 다른 방식으로 질문해 주시겠어요?"와 같은 안내 문구를 답하세요

        최우선적으로 [오늘 날짜]를 고려하여 검색 결과에 나온 정책이 현재 이미 시행 중인지, 향후 출시 예정인 정책인지 시점을 반드시 구분하여 정확히 안내하세요.
        
        [출력 규칙]
        - 반드시 한국어로 답변하세요
        - 반드시 존댓말을 사용하세요
        - 확실하지 않은 내용은 추측하지 마세요
        - 최대한 쉬운 단어와 문장으로 답변하세요
        - 검색결과에 없는 내용은 추측하지 마세요
        - 정확한 내용은 공식기관에서 확인하라고 안내해 주세요
        - 안내 시 [웹 검색 결과]에 실제로 존재하는 URL을 반드시 함께 포함하여 출력하세요 (없는 URL을 임의로 지어내지 말고, 검색 결과에 명시된 URL만 그대로 사용하세요)
        - 답변은 길게 늘리지 말고 요점 위주로 간결하게 작성하세요
        - **사용자의 질문 의도를 최우선으로 파악하세요.** 예를들어 사용자가 아파트 구입을 원하는데, 검색된 정책이 비아파트 전용이거나 엉뚱한 조건이라면 과감하게 제외하거나 부가 설명으로만 짧게 언급하고, 진짜 아파트에 쓸 수 있는 정책(보금자리론, 디딤돌 등) 위주로 답변하세요.
        - 뜬금없는 정책을 메인으로 끌고 와서 "근데 이건 안 됩니다"라고 맥을 끊는 답변을 하지 마세요. 처음부터 사용자의 조건(아파트 구입 여부 등)에 맞는 실질적인 대출 상품을 중심으로 안내하세요.

        
        [사용자 정보]
        - 나이 : {age}세
        - 직업 : {job}
        - 월 소득 : {monthly_income}원
        - 총 자산 : {total_assets}원
        - 가족 구성원 수 : {household_size}명
        - 금융 이해도 점수 : {score}점
        - 중위소득비율 : {ratio_text}


        [오늘 날짜]
        {today}

        [웹 검색 결과]
        {text}
    """
    human_prompt = "[질문]\n{question}"

    msg_list = [("system", sys_prompt), ("human", human_prompt)]
    prompt = ChatPromptTemplate.from_messages(msg_list)
    chain = prompt | llm | StrOutputParser()

    result = chain.invoke({
        "question": state['question'],
        "age": state['age'],
        "job": state['job'],
        "monthly_income": f"{state['monthly_income']:,}",
        "total_assets": f"{state['total_assets']:,}",
        "household_size": state['household_size'],
        "score": state['score'],
        "ratio_text": ratio_text,
        "text": text,
        "today": today
    })

    return {"answer": result}
       
