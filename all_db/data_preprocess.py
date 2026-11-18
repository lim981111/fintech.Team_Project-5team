import sqlite3, json
import os

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from datetime import datetime
import time

from rag.rag_search import *


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "API", "welfare.db")
conn = sqlite3.connect(DB_PATH)


rows = conn.execute(
    "SELECT serv_id, list_json, detail_json FROM policies "
    "WHERE detail_done = 'Y' AND embedded = 'N'",
).fetchall()

serv_id, list_s, detail_s = rows[0]
t = json.loads(list_s)
d = json.loads(detail_s)

#print(d["servNm"])           
#print(t["servDtlLink"])      


def build_text(d) :
    title = d.get("servNm","") #정책명
    content = (
        f"요약: {d.get('wlfareInfoOutlCn','')[:400]}\n"
        f"지원 대상: {d.get('tgtrDtlCn','')[:500]}\n"
        f"선정 기준: {d.get('slctCritCn','')[:600]}\n"
        f"지원 내용: {d.get('alwServCn','')[:800]}"
    ).replace("\r", "\n")
    return f"정책명: {title} \n 상세내용 : \n{content}"

#print(build_text(d))

def build_metadata(t,d):
    created_at = datetime.now().isoformat(timespec="seconds")
        
    return {
        "serv_id": t["servId"],
        "institution": f"{t.get('jurMnofNm', '')} {t.get('jurOrgNm', '')}".strip(), #기관
        "target_audience": f"{t.get('lifeArray') or ''} / {t.get('trgterIndvdlArray') or ''}".strip(" /"), #대상
        "period": f"{d.get('crtrYr', '')} {d.get('sprtCycNm', '')}".strip(), #기간
        "source": t.get("servDtlLink", "").strip(), #출처
        "created_at": created_at, #데이터 등록 일시
    }

#print(build_metadata(t, d))
#text = build_text(d)
#print(text)
#print(len(text))
#print(build_metadata(t, d))


"""
lens = []
total = len(rows)
for i,(serv_id, list_s, detail_s) in enumerate(rows, start=1):
    t = json.loads(list_s)
    d = json.loads(detail_s)
    text = build_text(d)
    meta = build_metadata(t, d)    # 에러 없이 만들어지는지만 확인
    lens.append(len(text))

    if i % 50 == 0 or i == total:
        print(f"{i}/{total} ({i / total * 100:.0f}%)")

print(len(lens), min(lens), max(lens))

#conn.execute("ALTER TABLE policies ADD COLUMN embedded TEXT NOT NULL DEFAULT 'N'")
#conn.commit()
"""



i = 15
for start in  range(0, len(rows), i):
    chunk = rows[start:start + i]
    ids, texts, metas = [], [], []
    for serv_id, list_s, detail_s in chunk:
        t = json.loads(list_s)
        d = json.loads(detail_s)
        ids.append(serv_id)
        texts.append(build_text(d))
        metas.append(build_metadata(t, d))

    vs = get_store("policy")

    if not texts:
        continue
    vs.add_texts(texts = texts, metadatas = metas, ids = ids)

    conn.executemany("UPDATE policies SET embedded='Y' WHERE serv_id=?", [(j,) for j in ids])
    conn.commit()
    print(f"{min(start + i, len(rows))}/{len(rows)}")
    time.sleep(30)