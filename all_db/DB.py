import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "general_db.db")

SCHEMA  = """
    CREATE TABLE IF NOT EXISTS users (
        user_id        INTEGER PRIMARY KEY AUTOINCREMENT,   -- 유저 ID
        login_id  TEXT UNIQUE,
        name           TEXT,                            -- 이름
        age            INT,                             -- 나이
        job            TEXT,                            -- 직업
        monthly_income INT,                             -- 1달 수입
        total_assets   INT,                             -- 총 자산
        household_size INT,                             -- 가족구성원 수
        score          INT,                             -- 금융 이해도
        created_at     TEXT                             -- 생성일자
    );

    CREATE TABLE IF NOT EXISTS chats (
        chat_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL REFERENCES users(user_id),
        title      TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS messages (
        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id    INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
        question   TEXT NOT NULL,
        answer     TEXT,
        created_at TEXT
    );
"""

EDU_ORG = {
    "1": "금융감독원", "2": "서민금융진흥원", "3": "손해보험협회", "4": "생명보험협회",
    "5": "시니어금융교육협의회", "6": "신용회복위원회", "7": "신협중앙회", "8": "여신금융협회",
    "9": "은행연합회", "10": "예금보험공사", "11": "저축은행중앙회", "12": "청소년금융교육협의회",
    "13": "투자자교육협의회", "14": "한국금융소비자보호재단", "15": "금융투자협회", "16": "기타",
    "17": "광주은행", "18": "기업은행", "19": "농협은행", "20": "대구은행", "21": "신한은행",
    "22": "하나은행", "23": "미래에셋증권", "24": "삼성증권", "25": "BNP파리바카디프",
    "26": "농협생명", "27": "신한카드", "28": "현대카드", "29": "새마을금고중앙회",
    "30": "흥국금융그룹", "31": "KB금융공익재단", "32": "한국예탁결제원", "33": "한국거래소",
    "34": "부산은행", "35": "전북은행", "36": "금융결제원", "37": "한국주택금융공사",
    "38": "한화생명", "39": "신용보증기금", "40": "현대캐피탈", "41": "경남은행",
    "42": "한국씨티은행", "44": "국민연금공단",
}

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)

#init_db()

def create_user(name, age, job, monthly_income, total_assets, household_size, score, created_at = None) :
    # 하는일 : users에 1행 추가	
    # 사용처 : 프로필 저장
    if created_at is None : 
        created_at = datetime.now().isoformat(timespec="seconds")

    with get_conn() as conn:
        conn.execute(
        "INSERT INTO users (name, age, job, monthly_income, total_assets, household_size, score, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, age, job, monthly_income, total_assets, household_size, score, created_at)
        )

#create_user("개똥이",28,"아르바이트생",1500000,20000000, 1, 15)
#create_user("김철수",26,"신입사원",2200000,2000000, 1, 20)

def get_user(user_id) :
    # 하는일 : 프로필 조회	
    # 사용처 : /chat에서 프로필 읽기
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None

#print(get_user(1))

def create_chat(user_id, title, created_at = None) : 
    # 하는일 : 새 대화방, chat_id 반환	
    # 사용처 : 첫 질문 때
    #user_id  title  created_at 

    if created_at is None : 
        created_at = datetime.now().isoformat(timespec="seconds")
    
    with get_conn() as conn:
        cur = conn.execute(
        "INSERT INTO chats (user_id, title, created_at) "
        "VALUES (?, ?, ?)",
        (user_id, title, created_at)
        )
        
        return cur.lastrowid

#print(create_chat(1,"적금질문"))
    

def list_chats(user_id) : 
    # 하는일 : 대화방 목록	
    # 사용처 : GET /chats
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT chat_id, title, created_at FROM chats "
            "WHERE user_id = ? ORDER BY chat_id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_message(chat_id, question, answer, created_at = None) :
    # 하는일 : 질문과 답변 저장	
    # 사용처 : /chat 끝에서
    if created_at is None : 
        created_at = datetime.now().isoformat(timespec="seconds")
        
    with get_conn() as conn:
        conn.execute(
        "INSERT INTO messages  (chat_id, question, answer, created_at) "
        "VALUES (?, ?, ?, ?)",
        (chat_id, question, answer, created_at)
        )

def get_messages(chat_id) :
    # 하는일 : 대화 내용 조회	
    # 사용처 : GET /chats/{id}, 맥락 기억
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT question, answer, created_at FROM messages "   
            "WHERE chat_id = ? ORDER BY message_id",
            (chat_id,),
        ).fetchall()
    return [dict(r) for r in rows]

#print(get_user(2))
#cid = create_chat(2, "적금 질문")
#add_message(cid, "적금이 뭐야?", "적금은 매달...")
#print(list_chats(2))
#print(get_messages(cid))

def delete_chat(chat_id, user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM chats WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    conn.commit()
    deleted = cur.rowcount      # 지워진 행 수 (0이면 없는 방)
    conn.close()
    return deleted



def list_mp4() : 
    # 하는일 : 교육자료 mp4 목록
    # 사용처 : get/edu/contents
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM edu_contents "
            "WHERE link_kind = 'mp4' ORDER BY contents_slno DESC",
        ).fetchall()
    return [dict(r) for r in rows]

