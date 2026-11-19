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

URL = "https://www.fss.or.kr/edu/openApi/api/eduContents.jsp"


# POLICY_API_KEY2
KEY = os.getenv("FSS_API_KEY")
if KEY and "%" in KEY:          # Encoding 키를 넣었어도 한 번 풀어서 사용
    KEY = unquote(KEY)





import json
res = requests.get(URL, params={"apiType": "json", "authKey": KEY, "makeTypeCode": 1}, timeout=15)
items = json.loads(res.text)["reponse"]["result"]
print(len(items))
for it in items[:5]:
    print(it.get("title"), "|", it.get("xtrnlContentsUrl"), "|",
          it.get("playCntnHh"), it.get("playCntnMi"), it.get("playSecond"), "|",
          it.get("eduTrgtCntnt"), it.get("eduCntnt"))

import re

# 1) 한 건의 모든 필드를 보기 (cntnt는 너무 크니 제외, 값은 100자까지만)
it = items[0]
for k, v in it.items():
    if k != "cntnt":
        print(k, ":", str(v)[:100])

# 2) 554건 중 xtrnlContentsUrl이 채워진 건수
print("2번 : ",sum(1 for x in items if x.get("xtrnlContentsUrl")))

# 3) cntnt 안에 http 주소가 있는지
print("3번 : ",re.findall(r'https?://[^\s"<>\']+', it.get("cntnt", ""))[:5])