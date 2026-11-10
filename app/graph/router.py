"""질문이 어느 데이터(교육 / 복지 / 금융상품)와 관련 있는지 키워드로 나눈다.

처음에는 단어 포함 여부만 본다. 나중에 LangGraph나 LLM 분류로 바꿀 때는
route_question()만 교체하면 된다.
"""

SOURCE_KEYWORDS = {
    # 예·적금 금리 비교
    "products": ("예금", "적금", "금리", "이자", "예적금", "금융상품"),
    # 복지/지원 제도
    "welfare": (
        "복지", "지원금", "수당", "급여", "바우처", "보조금", "장려금", "혜택",
        "돌봄", "정책", "기초생활", "양육", "보육", "월세 지원", "생계",
    ),
    # 금융 교육 프로그램
    "edu": ("교육", "강의", "강좌", "특강", "연수", "세미나", "체험", "설명회"),
}

SOURCE_ORDER = ("products", "welfare", "edu")
DEFAULT_SOURCE = "edu"


def route_question(question):
  """질문과 관련된 출처 이름 리스트를 반환한다. 해당하는 게 없으면 교육으로 본다."""
  q = question or ""
  matched = [
      source for source in SOURCE_ORDER
      if any(word in q for word in SOURCE_KEYWORDS[source])
  ]
  return matched or [DEFAULT_SOURCE]
