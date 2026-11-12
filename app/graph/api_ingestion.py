from bs4 import BeautifulSoup
import os
import requests
import xmltodict
from dotenv import load_dotenv
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()
FSS_API_KEY = os.getenv("FSS_API_KEY")


def clean_html(raw_html):
  """HTML 태그를 제거하고 순수 텍스트만 추출하는 함수"""
  if not raw_html:
    return ""
  soup = BeautifulSoup(raw_html, "html.parser")
  return soup.get_text(separator=" ", strip=True)


def get_fss_edu_rag_data():
  """금감원 교육 프로그램 API를 호출하고 RAG 스키마로 변환된 리스트를 반환하는 함수"""
  url = "https://www.fss.or.kr/edu/openApi/api/eduProgram.jsp"
  params = {"apiType": "xml", "authKey": FSS_API_KEY}

  try:
    response = requests.get(url, params=params, verify=False)
    response.raise_for_status()
    data = xmltodict.parse(response.text)

    # 💡 브라우저에서 확인된 실제 XML 구조 경로: document -> root -> result
    root = data.get("document", {}).get("root", {})
    items = root.get("result", [])

    # 결과가 단일 항목일 경우 딕셔너리로 올 수 있으므로 리스트로 변환
    if isinstance(items, dict):
      items = [items]

    rag_ready_data = []
    for item in items:
      # programName 추출 (CDATA 형태 대응)
      prog_name_val = item.get("programName", "금융 교육 프로그램")
      if isinstance(prog_name_val, dict):
        title = prog_name_val.get("#text", "금융 교육 프로그램")
      else:
        title = prog_name_val

      institution = "금융감독원"
      target_audience = item.get("target", "청년/전국민")
      period = item.get("eduPrd", "상시접수")
      source = "금감원 교육 API"

      # cntnt(상세 내용) HTML 태그 정제
      cntnt_val = item.get("cntnt", "")
      if isinstance(cntnt_val, dict):
        raw_content = cntnt_val.get("#text", "")
      else:
        raw_content = cntnt_val

      clean_content = clean_html(raw_content)

      content_parts = [
          f"교육 프로그램명: {title}",
          f"주관 기관: {institution}",
          f"교육 대상: {target_audience}",
          f"신청 기간: {period}",
          f"상세 설명: {clean_content if clean_content else '설명 내용이 없습니다.'}",
      ]
      full_content = "\n".join(content_parts)

      rag_ready_data.append({
          "metadata": {
              "title": title,
              "institution": institution,
              "target_audience": target_audience,
              "period": period,
          },
          "source": source,
          "content": full_content,
      })

    print(
        f"[성공] 총 {len(rag_ready_data)}개의 금감원 교육 데이터 정제 완료 (총"
        f" {root.get('resultCnt', 0)}건)"
    )
    return rag_ready_data
  except Exception as e:
    print(f"[FSS API 에러 발생]: {e}")
    return []

get_fss_edu_rag_data()