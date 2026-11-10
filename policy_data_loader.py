import os
import requests
import xmltodict
from dotenv import load_dotenv
import urllib3
import urllib.parse  # 400 에러 방지용 임포트

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

PUBLIC_DATA_API_KEY = os.getenv("PUBLIC_DATA_API_KEY")


def fetch_api_data(url, params, data_type="json"):
  """공공 API에서 데이터를 안전하게 가져오는 함수 (400 에러 방지 처리)"""
  try:
    # serviceKey는 이미 인코딩되어 있으므로 params에서 분리하여 이중 인코딩 방지
    service_key = params.pop("serviceKey", None)
    query_string = urllib.parse.urlencode(params)

    if service_key:
      final_url = f"{url}?serviceKey={service_key}&{query_string}"
    else:
      final_url = f"{url}?{query_string}"

    response = requests.get(final_url, verify=False)
    response.raise_for_status()

    if data_type == "json":
      data = response.json()
      return data.get("response", {}).get("body", {}).get("items", [])
    elif data_type == "xml":
      data = xmltodict.parse(response.content)
      items = (
          data.get("response", {})
          .get("body", {})
          .get("items", {})
          .get("item", [])
      )
      if isinstance(items, dict):
        items = [items]
      return items
  except Exception as e:
    print(f"[서민금융 API 호출 에러]: {e}")
    return []


def transform_to_rag_schema(raw_item):
  """수급받은 원본 데이터를 메타데이터와 본문(Content)으로 정제하는 로직"""
  title = raw_item.get("progNm", "제목 없음")
  institution = raw_item.get("instNm", "금융기관")
  target_audience = raw_item.get("target", "청년/전국민")
  period = raw_item.get("eduPrd", "상시접수")
  source = raw_item.get("source", "공공API")

  content_parts = [
      f"지원 정책명: {title}",
      f"주관 기관: {institution}",
      f"지원 대상: {target_audience}",
      f"신청 기간: {period}",
      f"상세 설명: {raw_item.get('contents', '설명 내용이 없습니다.')}",
  ]
  full_content = "\n".join(content_parts)

  return {
      "metadata": {
          "title": title,
          "institution": institution,
          "target_audience": target_audience,
          "period": period,
      },
      "source": source,
      "content": full_content,
  }


def get_inclusive_finance_rag_data():
  """서민금융 API를 호출하고 RAG 스키마로 변환된 전체 리스트를 반환하는 함수"""
  url = "https://apis.data.go.kr/1400300/inclusiveFinanceService/getItems"
  params = {
      "serviceKey": PUBLIC_DATA_API_KEY,
      "pageNo": "1",
      "numOfRows": "10",  # 테스트용으로 우선 10개만 설정해도 좋습니다
      "type": "json",
  }

  print("서민금융지원 데이터 수집 중...")
  raw_items = fetch_api_data(url, params, data_type="json")

  rag_ready_data = []
  for item in raw_items:
    refined_item = transform_to_rag_schema(item)
    rag_ready_data.append(refined_item)

  print(f"[성공] 총 {len(rag_ready_data)}개의 서민금융 상품 데이터 정제 완료")
  return rag_ready_data