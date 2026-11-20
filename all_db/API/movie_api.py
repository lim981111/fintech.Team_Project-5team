import json
import os
import sqlite3
from collections import Counter
from urllib.parse import unquote

import requests
from dotenv import load_dotenv

load_dotenv()

URL = "https://www.fss.or.kr/edu/openApi/api/eduContents.jsp"

KEY = os.getenv("FSS_API_KEY")
if KEY and "%" in KEY:
    KEY = unquote(KEY)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "general_db.db")


# 1단계: API 한 번 호출해서 전체 목록 받기
res = requests.get(
    URL,
    params={"apiType": "json", "authKey": KEY, "makeTypeCode": 1},  # 영상만, 모든 기관
    timeout=15,
)
items = json.loads(res.text)["reponse"]["result"]   # 'reponse' 는 금감원 API의 오타 그대로
print("받은 행:", len(items))                          # 554 가 나와야 정상


# 2단계: 같은 영상(contentsSlno 같은 줄)을 하나로 합치기
#   - 첨부파일마다 줄이 따로 와서 같은 영상이 2줄로 오는 경우가 있음
#   - 줄 하나 = 영상 대표, 그중 fileSn=1(사진)의 주소를 썸네일로 기록
merged = {}   # { 영상번호 : 영상 정보 }  (같은 번호는 하나뿐)
for x in items:
    slno = x["contentsSlno"]
    if slno not in merged:                    # 처음 보는 번호면 그 줄을 대표로 저장
        merged[slno] = dict(x)                # 복사해서 저장 (원본을 건드리지 않음)
        merged[slno]["thumb_url"] = ""        # 썸네일은 일단 빈 값
    file_url = x.get("fileDownUrl") or ""     # None 이면 "" 로
    if "fileSn=1" in file_url:                # 사진(fileSn=1) 주소가 나오면 썸네일로
        merged[slno]["thumb_url"] = file_url
print("고유 영상:", len(merged))                 # 407 이 나와야 정상


# 3단계: DB에 넣을 모양으로 정리 (영상 주소가 있는 것만)
def to_int(value):
    #재생시간 표기를 위한 함수 '' 이나 None 이면 0, 아니면 정수로
    try:
        return int(value or 0)
    except ValueError:
        return 0


def link_kind(url):
    # mp4와 youtube링크가 섞여있기 때문에 구분
    u = url.lower()
    if ".mp4" in u:
        return "mp4"
    if "youtu" in u:
        return "youtube"
    return "other"


rows = []
for slno, x in merged.items():
    video_url = x.get("xtrnlContentsUrl") or ""
    if not video_url:                         # 재생 주소가 없는 영상은 건너뜀
        continue

    code = x.get("cpyrhtPermCode") or ""
    etc = x.get("cpyrhtPermCodeEtc") or ""
    ok = code in ("A", "B", "C", "D") or (code == "E" and ("출처를 표시" in etc or "indicating the source" in etc))
    if not ok:
        continue

    # 재생시간(초) = 시*3600 + 분*60 + 초   (빈 문자열은 0 으로)
    seconds = to_int(x.get("playCntnHh")) * 3600 + to_int(x.get("playCntnMi")) * 60 + to_int(x.get("playSecond"))

    rows.append((
        int(slno),                                   # contents_slno : 영상 고유 번호 (기본 키)
        x.get("title") or "",                        # title
        video_url,                                   # video_url
        link_kind(video_url),                        # link_kind : mp4 / youtube / other
        x["thumb_url"],                              # thumb_url : 없으면 ""
        seconds,                                     # play_seconds
        f",{x.get('eduTrgtCntnt') or ''},",          # edu_trgt  : ",Y,A,AM," (앞뒤에 쉼표)
        f",{x.get('eduCntnt') or ''},",              # edu_cntnt : ",3001,3002,"
        str(x.get("fncEngnCode") or ""),             # org_code : 운영기관 코드 (출처 표시용)
        x.get("cpyrhtPermCode") or "",               # copyright_code : 저작물 이용허락 (A~E)
    ))
print("재생 주소가 있는 영상:", len(rows))


# 4단계: DB에 저장
conn = sqlite3.connect(DB_PATH)
conn.execute("""
CREATE TABLE IF NOT EXISTS edu_contents (
    contents_slno  INTEGER PRIMARY KEY,
    title          TEXT,
    video_url      TEXT,
    link_kind      TEXT,
    thumb_url      TEXT,
    play_seconds   INTEGER,
    edu_trgt       TEXT,
    edu_cntnt      TEXT,
    org_code       TEXT,
    copyright_code TEXT
)
""")
conn.executemany("INSERT OR REPLACE INTO edu_contents VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()


# 5단계: 결과 확인
#print("DB 파일:", DB_PATH)
#print("테이블 전체 개수:", conn.execute("SELECT COUNT(*) FROM edu_contents").fetchone()[0])
#print("재생 방식별:", conn.execute("SELECT link_kind, COUNT(*) FROM edu_contents GROUP BY link_kind").fetchall())
#print("썸네일 없는 영상:", conn.execute("SELECT COUNT(*) FROM edu_contents WHERE thumb_url = ''").fetchone()[0])
#print("저작물 이용허락별:", conn.execute("SELECT copyright_code, COUNT(*) FROM edu_contents GROUP BY copyright_code").fetchall())
#conn.close()

