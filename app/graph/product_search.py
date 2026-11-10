"""금융상품(예금/적금) 질문 처리: 질문에서 종류와 기간을 읽고, 금리 순으로 정렬해 보여준다.

금리는 숫자라서 벡터 검색이 아니라 필터와 정렬로 찾는다.
정렬 기준은 '최고 우대금리'(없으면 기본금리)이며, 우대조건을 충족해야 받는 금리라서
기본금리도 함께 보여준다.
"""

import re

from app.graph.common import shorten

# '예적금'은 '예금'이라는 글자가 붙어 있지 않아서 따로 넣어야 예금과 적금 둘 다 찾는다
KIND_WORDS = {
    "deposit": ("예금", "예적금"),
    "saving": ("적금", "예적금"),
}
KIND_NAMES = {"deposit": "정기예금", "saving": "적금"}

NOTICE = (
    "※ 금융상품한눈에 공시 기준이며 금리와 우대조건은 변동될 수 있습니다. "
    "가입 전 금융회사에서 확인하세요. 특정 상품의 가입을 권유하는 것이 아닙니다."
)


def extract_term(question):
  """질문에서 가입 기간(개월)을 읽는다. 없으면 None."""
  q = question or ""
  match = re.search(r"(\d+)\s*개월", q)
  if match:
    return int(match.group(1))
  match = re.search(r"(\d+)\s*년", q)
  if match:
    return int(match.group(1)) * 12
  if "반년" in q:
    return 6
  return None


def parse_query(question):
  """(찾을 종류 리스트, 기간)을 반환. 종류를 말하지 않았으면 예금과 적금 둘 다."""
  q = question or ""
  kinds = [kind for kind, words in KIND_WORDS.items() if any(w in q for w in words)]
  return (kinds or ["deposit", "saving"]), extract_term(q)


def _rank_value(option):
  return option["rate_max"] if option.get("rate_max") is not None else option.get("rate")


def _best_option(options, term):
  candidates = [
      o for o in options
      if (term is None or o.get("term") == term) and _rank_value(o) is not None
  ]
  return max(candidates, key=_rank_value) if candidates else None


def search_products(question, items, top_k=None):
  """종류별로 금리 상위 상품을 찾아 [{'kind', 'kind_name', 'term', 'rows'}] 로 반환한다."""
  kinds, term = parse_query(question)
  top_k = top_k or (5 if len(kinds) == 1 else 3)

  groups = []
  for kind in kinds:
    rows = []
    for item in items:
      if item.get("kind") != kind:
        continue
      option = _best_option(item.get("options", []), term)
      if option is None:
        continue
      meta = item["metadata"]
      rows.append({
          "kind": kind,
          "kind_name": KIND_NAMES[kind],
          "company": meta.get("company", ""),
          "name": meta.get("name", ""),
          "group": meta.get("group", ""),
          "term": option.get("term"),
          "rate_type": option.get("rate_type", ""),
          "rate": option.get("rate"),
          "rate_max": option.get("rate_max"),
          "join_way": meta.get("join_way", ""),
          "special_condition": meta.get("special_condition", ""),
          "dcls_month": meta.get("dcls_month"),
      })
    rows.sort(key=lambda r: (-(_rank_value(r) or 0), r["company"]))
    groups.append({
        "kind": kind,
        "kind_name": KIND_NAMES[kind],
        "term": term,
        "rows": rows[:top_k],
    })
  return groups


def _pct(value):
  return "-" if value is None else f"{value:.2f}%"


def _month_text(dcls_month):
  text = str(dcls_month or "")
  return f"{text[:4]}-{text[4:6]}" if len(text) == 6 else text


def format_products(groups, dcls_month=None):
  """검색 결과를 답변용 문자열로 만든다. 공시 기준월과 유의 문구를 함께 붙인다."""
  month = _month_text(dcls_month)
  blocks = []
  for group in groups:
    head = f"[{group['kind_name']} 금리 상위"
    if group["term"]:
      head += f" · {group['term']}개월"
    if month:
      head += f" · 공시 기준 {month}"
    head += "]"

    if not group["rows"]:
      blocks.append(head + "\n조건에 맞는 상품을 찾지 못했습니다.")
      continue

    lines = [head]
    for index, row in enumerate(group["rows"], 1):
      detail = ", ".join(
          x for x in (row["rate_type"], f"{row['term']}개월" if row["term"] else "") if x
      )
      lines.append(
          f"{index}. {row['company']} {row['name']} — 기본 {_pct(row['rate'])}"
          f" / 최고 {_pct(row['rate_max'])}" + (f" ({detail})" if detail else "")
      )
      extra = []
      if row["join_way"]:
        extra.append("가입방법: " + shorten(row["join_way"], 40))
      if row["special_condition"]:
        extra.append("우대조건: " + shorten(row["special_condition"], 60))
      if extra:
        lines.append("   " + " · ".join(extra))
    blocks.append("\n".join(lines))

  return "\n\n".join(blocks) + "\n\n" + NOTICE


def flatten_rows(groups):
  return [row for group in groups for row in group["rows"]]
