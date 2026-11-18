import json
import os
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import unquote
from apscheduler.schedulers.blocking import BlockingScheduler

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "http://apis.data.go.kr/B554287/NationalWelfareInformationsV001"
LIST_URL = f"{BASE}/NationalWelfarelistV001"
DETAIL_URL = f"{BASE}/NationalWelfaredetailedV001"

# POLICY_API_KEY2
KEY = os.getenv("POLICY_API_KEY2")
if KEY and "%" in KEY:          # Encoding 키를 넣었어도 한 번 풀어서 사용
    KEY = unquote(KEY)

# DB 파일: 이 스크립트와 같은 폴더에 생성 (어디서 실행해도 같은 파일을 씀)  
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "welfare.db")

PAGE_SIZE = 500                 # 목록 1회 최대 500건
DETAIL_LIMIT = 95               # 하루 상세 호출 수 (한도 100에서 여유 5)
DETAIL_DELAY = 0.2              # 호출 사이 대기(초)

# 응답에서 1개여도 항상 리스트로 받을 태그
REPEAT_TAGS = {"servList", "applmetList", "inqplCtadrList",
               "inqplHmpgReldList", "basfrmList", "baslawList"}


class QuotaExceeded(Exception):
    """일일 호출 한도 초과"""


# ---------------------------------------------------------------
# 1. API 호출
# ---------------------------------------------------------------
def to_dict(elem):
    """XML 요소를 dict로 변환"""
    children = list(elem)
    if not children:
        return (elem.text or "").strip()
    out = {}
    for c in children:
        v = to_dict(c)
        if c.tag in REPEAT_TAGS:
            out.setdefault(c.tag, []).append(v)
        else:
            out[c.tag] = v
    return out


def call(url, params):
    """API 한 번 호출 (재시도 없음: 실패한 호출도 한도를 쓰기 때문).

    성공하면 dict, 실패하면 None, 한도 초과면 QuotaExceeded 예외.
    """
    params = {"serviceKey": KEY, **params}
    try:
        res = requests.get(url, params=params, timeout=15)
    except requests.RequestException as e:
        print(f"  호출 실패: {type(e).__name__}")       # URL에 키가 있어 메시지는 출력 안 함
        return None

    if res.status_code == 429:
        print("  429 응답:", res.text[:200])
        raise QuotaExceeded

    try:
        root = ET.fromstring(res.text)
    except ET.ParseError:
        print(f"  XML 파싱 실패 (status={res.status_code})")
        print(f"  응답 내용 일부: {res.text[:200]}")
        return None

    """
    # 인증/한도 오류는 이런 형태의 XML로 옴
    if root.tag == "OpenAPI_ServiceResponse":
        if root.findtext(".//returnReasonCode") == "22":
            raise QuotaExceeded
        print("  호출 오류:", root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg"))
        return None
    """

    if root.tag == "OpenAPI_ServiceResponse" or root.findtext(".//resultCode") not in (None, "0", "00"):
        # 에러 메시지를 담고 있는 태그들을 총동원해서 찾습니다.
        err_code = root.findtext(".//returnReasonCode") or root.findtext(".//resultCode")
        err_msg = (
            root.findtext(".//returnAuthMsg") 
            or root.findtext(".//errMsg") 
            or root.findtext(".//resultMessage")
        )
        
        print(f"  [API 에러 발생] 코드: {err_code}, 메시지: {err_msg}")
        
        if err_code == "22" or (err_msg and "LIMITED" in err_msg.upper()):
            raise QuotaExceeded
        return None

    data = to_dict(root)
    if data.get("resultCode") not in ("0", "00"):
        print("  결과 코드 오류:", data.get("resultCode"), data.get("resultMessage"))
        return None
    return data


def fetch_list():
    """목록 전체를 받아 리스트로 반환 (461건이면 호출 1번)"""
    items = {}
    page = 1
    while True:
        data = call(LIST_URL, {"callTp": "L", "pageNo": page,
                               "numOfRows": PAGE_SIZE, "srchKeyCode": "003"})
        if data is None:
            raise RuntimeError("목록 조회 실패")

        total = int(data["totalCount"])
        batch = data.get("servList", [])
        before = len(items)
        for it in batch:
            items[it["servId"]] = it
        print(f"목록 page={page}, 누적 {len(items)}건 / 전체 {total}건")

        if len(items) >= total or not batch or len(items) == before:
            break
        page += 1
    return list(items.values())


# ---------------------------------------------------------------
# 2. DB (SQLite)
# ---------------------------------------------------------------
def get_conn():
    """DB에 연결하고, 표(테이블)가 없으면 만든다."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS policies (
            serv_id      TEXT PRIMARY KEY,           -- 정책 ID (중복 불가)
            serv_nm      TEXT,                       -- 정책명
            list_json    TEXT,                       -- 목록에서 받은 값 전체(JSON 문자열)
            detail_json  TEXT,                       -- 상세에서 받은 값 전체(JSON 문자열)
            detail_done  TEXT NOT NULL DEFAULT 'N',  -- 상세 수집 여부 (N/Y)
            collected_at TEXT                        -- 상세를 받은 시각
        )
        """
    )
    conn.commit()
    return conn


def save_list(conn, items):
    """목록을 DB에 넣는다. 새 정책은 추가(detail_done='N'), 이미 있으면 목록 정보만 갱신."""
    for it in items:
        conn.execute(
            """
            INSERT INTO policies (serv_id, serv_nm, list_json)
            VALUES (?, ?, ?)
            ON CONFLICT(serv_id) DO UPDATE SET
                serv_nm   = excluded.serv_nm,
                list_json = excluded.list_json
            """,
            (it["servId"], it.get("servNm", ""), json.dumps(it, ensure_ascii=False)),
        )
    conn.commit()


def get_pending_ids(conn, limit):
    """상세를 아직 못 받은(N) 정책 ID를 limit개까지 가져온다."""
    rows = conn.execute(
        "SELECT serv_id FROM policies WHERE detail_done = 'N' LIMIT ?", (limit,)
    ).fetchall()
    return [r[0] for r in rows]


def save_detail(conn, serv_id, detail):
    """상세를 저장하고 detail_done을 'Y'로 바꾼다."""
    conn.execute(
        """
        UPDATE policies
        SET detail_json = ?, detail_done = 'Y', collected_at = ?
        WHERE serv_id = ?
        """,
        (json.dumps(detail, ensure_ascii=False), datetime.now().isoformat(timespec="seconds"), serv_id),
    )
    conn.commit()      # 한 건마다 확정: 중간에 멈춰도 받은 것까지는 남는다


def print_summary(conn):
    print("--- 현재 상태 ---")
    for flag, cnt in conn.execute(
        "SELECT detail_done, COUNT(*) FROM policies GROUP BY detail_done"
    ):
        print(f"  상세 수집 {flag}: {cnt}건")


# ---------------------------------------------------------------
# 3. 실행
# ---------------------------------------------------------------
def run():
    conn = get_conn()

    # 1) 목록 호출 1번 → DB에 반영
    try:
        items = fetch_list()
        save_list(conn, items)
        print(f"목록 {len(items)}건을 DB에 반영했습니다.")
    except QuotaExceeded:
        print("목록 호출 한도 초과 → 기존 DB로 상세만 진행합니다.")
    except RuntimeError as e:
        print(e, "→ 기존 DB로 상세만 진행합니다.")

    # 2) 상세를 못 받은 것만, 하루 한도 안에서
    pending = get_pending_ids(conn, DETAIL_LIMIT)
    print(f"오늘 상세 수집 대상: {len(pending)}건")

    done = 0
    for serv_id in pending:
        try:
            detail = call(DETAIL_URL, {"callTp": "D", "servId": serv_id})
            if detail is not None:
                save_detail(conn, serv_id, detail)
                done += 1
        except QuotaExceeded:
            print("상세 호출 한도 초과 → 오늘은 여기서 중단합니다.")
            break
        except Exception as e:
            print(f"  {serv_id} 처리 중 에러 ({type(e).__name__}) → 건너뜁니다.")
        time.sleep(DETAIL_DELAY)

    print(f"오늘 상세 {done}건 수집")
    print_summary(conn)
    conn.close()


def import_old_raw(path="policies_raw.json"):
    """(1회용) 예전 policies_raw.json의 상세를 DB로 옮긴다. 목록 저장 여부와 무관."""
    conn = get_conn()
    with open(path, encoding="utf-8") as f:
        old = json.load(f)["policies"]
    moved = 0
    for p in old:
        if not p.get("detail"):
            continue
        list_part = {k: v for k, v in p.items() if k != "detail"}
        conn.execute(
            """
            INSERT INTO policies (serv_id, serv_nm, list_json, detail_json, detail_done, collected_at)
            VALUES (?, ?, ?, ?, 'Y', ?)
            ON CONFLICT(serv_id) DO UPDATE SET
                detail_json  = excluded.detail_json,
                detail_done  = 'Y',
                collected_at = excluded.collected_at
            """,
            (p["servId"], p.get("servNm", ""),
             json.dumps(list_part, ensure_ascii=False),
             json.dumps(p["detail"], ensure_ascii=False),
             datetime.now().isoformat(timespec="seconds")),
        )
        moved += 1
    conn.commit()
    print(f"예전 상세 {moved}건을 옮겼습니다.")
    print_summary(conn)
    conn.close()

if __name__ == "__main__":
    run()