from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

from all_db.API.bankpdf import *
from langchain_google_genai import ChatGoogleGenerativeAI
from state import SideState

load_dotenv()

llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite")

def init_answer(state:SideState):
    print('RAG 정보 검색')
    question = state['question']
    context = rag_search(question)
    state['contents'] = context
    return state

def last_answer(state:SideState):
    print('주어진 데이터를 가지고 최종 응답 완성')
    sys_prompt = """
    당신은 금융/경제 용어 전문 사전이자 분석가입니다.
    사용자가 입력한 [질문]이 가르키는 용어를 파악하고, [참고데이터]를 기반으로 명확하고 간결한 설명을 제공하세요.

    [엄격한 규칙]
    1. 인사말, 추임새, "네, 알겠습니다", "설명해 드리겠습니다" 같은 **불필요한 서두나 잡담을 절대 포함하지 마세요.** 답변은 무조건 해당 용어의 정의나 설명부터 바로 시작해야 합니다.
    2. [참고데이터]에 있는 내용만을 기반으로 작성하며, 데이터에 없는 내용을 임의로 지어내거나 과장하지 마세요.
    3. 만약 [참고데이터]에 해당 용어에 대한 설명이 없다면, 사족을 붙이지 말고 정확히 "해당 용어에 대한 정보를 찾을 수 없습니다."라고만 답변하세요.
    4. 친근한 대화체(해요체, 반말 등)를 쓰지 말고, 백과사전이나 사전처럼 **객관적이고 전문적인 명사형 또는 해요체(~다, ~임)의 서술형 어조**를 유지하세요.
    """
    human_prompt = "[참고데이터]\n{context}\n\n[질문]\n{question}"
    msg_list = [("system",sys_prompt),("human",human_prompt)]
    prompt = ChatPromptTemplate.from_messages(msg_list)
    chain = prompt|llm|StrOutputParser()
    result = chain.invoke({
        "question":state['question'],
        "context":state['contents']
    })
    state['answer'] = result
    return state