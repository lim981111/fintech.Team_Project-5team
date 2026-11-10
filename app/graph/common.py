"""금감원 교육 외 출처(복지, 금융상품) 수집 모듈이 함께 쓰는 공통 도구."""

import html
import json
import logging
import os
import re
import tempfile
from urllib.parse import unquote

import urllib3
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# 프로젝트 최상단(루트): app/graph/common.py 기준 세 단계 위
BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# 금감원(fss.or.kr) 서버용 SSL 검증 설정 (.env의 FSS_VERIFY_SSL)
#   true(기본) / false(개발용: 인증서 문제 시) / CA 번들 파일 경로
_verify_env = os.getenv("FSS_VERIFY_SSL", "true").strip()
if _verify_env.lower() == "false":
  FSS_VERIFY = False
  urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
elif _verify_env.lower() == "true":
  FSS_VERIFY = True
else:
  FSS_VERIFY = _verify_env


def decode_key(key):
  """공공데이터포털의 'Encoding 키'(% 포함)를 넣었더라도 한 번 풀어서 쓴다.

  requests가 파라미터를 다시 인코딩하므로, 이미 인코딩된 키를 그대로 넘기면
  이중 인코딩되어 인증 오류가 난다.
  """
  return unquote(key) if key and "%" in key else key


def as_list(value):
  """xmltodict는 항목이 1개면 dict, 여러 개면 list로 주므로 항상 list로 맞춘다."""
  if value is None:
    return []
  return value if isinstance(value, list) else [value]


def as_text(value, default=""):
  """xmltodict 값(str 또는 {'#text': ...})을 문자열로 변환"""
  if isinstance(value, dict):
    value = value.get("#text", default)
  return value if value else default


def clean_text(value):
  """XML에서 읽은 텍스트를 사람이 읽기 좋게 정리한다.

  - '&amp;#9312;'처럼 이중 이스케이프된 문자(①)를 한 번 더 풀어 준다.
  - 혹시 섞인 HTML 태그를 제거하고, 줄 단위로 공백을 정리한다.
  """
  text = as_text(value)
  if not text:
    return ""
  text = html.unescape(str(text))
  if "<" in text and ">" in text:
    text = BeautifulSoup(text, "html.parser").get_text(separator="\n")
  text = text.replace("\r", "\n")
  lines = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in text.split("\n")]
  return "\n".join(line for line in lines if line)


def split_csv(value):
  """'영유아,아동' / '아동, 영유아' 같은 쉼표 구분 문자열을 중복 없는 리스트로 만든다."""
  text = clean_text(value).replace("\n", ",")
  parts = [part.strip() for part in re.split(r"[,，]", text) if part.strip()]
  return list(dict.fromkeys(parts))


def shorten(text, limit):
  """줄바꿈을 공백으로 합치고 limit자를 넘으면 말줄임표로 줄인다."""
  flat = re.sub(r"\s+", " ", text or "").strip()
  return flat if len(flat) <= limit else flat[:limit].rstrip() + "…"


def write_json_atomic(path, data):
  """임시 파일에 쓴 뒤 교체해서, 쓰는 도중 파일이 깨지는 것을 방지"""
  directory = os.path.dirname(path) or "."
  fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
  try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
  except Exception:
    if os.path.exists(tmp_path):
      os.remove(tmp_path)
    raise


_memo = {}


def load_json_cached(path, default):
  """JSON 파일을 읽되, 파일이 바뀌지 않았으면 메모리에 둔 값을 재사용한다 (API 호출 없음)."""
  try:
    stat = os.stat(path)
  except OSError:
    return default

  stamp = (stat.st_mtime_ns, stat.st_size)
  cached = _memo.get(path)
  if cached and cached[0] == stamp:
    return cached[1]

  try:
    with open(path, "r", encoding="utf-8") as f:
      data = json.load(f)
  except Exception as e:
    logger.warning("캐시 파일 읽기 실패 (%s): %s", os.path.basename(path), e)
    return default

  _memo[path] = (stamp, data)
  return data
