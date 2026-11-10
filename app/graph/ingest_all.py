"""모든 출처(교육 / 복지 / 금융상품)를 API에서 새로 받아 저장하고, 벡터 DB를 재구축한다.

사용법 (프로젝트 루트에서)
  python -m app.graph.ingest_all                      # 전부 갱신
  python -m app.graph.ingest_all --only welfare       # 복지만 (교육/복지/금융상품 중 선택, 여러 개 가능)
  python -m app.graph.ingest_all --offline            # API 호출 없이 저장본으로 벡터 DB만 재구축
  python -m app.graph.ingest_all --no-vector          # 벡터 DB는 건드리지 않음

API가 실패하면 기존 저장본이 그대로 유지된다.
복지는 서비스 수만큼 상세 호출이 필요해 몇 분 걸릴 수 있다.
"""

import argparse
import logging
import sys
from collections import Counter

from app.graph.api_ingestion import fetch_and_save_fss_data, load_local_data
from app.graph.finlife_ingestion import (
    fetch_and_save_products,
    load_local_products,
    load_products_info,
)
from app.graph.product_search import format_products, search_products
from app.graph.welfare_ingestion import fetch_and_save_welfare, load_local_welfare

LABELS = {"edu": "교육", "welfare": "복지", "products": "금융상품"}
FETCHERS = {
    "edu": (fetch_and_save_fss_data, load_local_data),
    "welfare": (fetch_and_save_welfare, load_local_welfare),
    "products": (fetch_and_save_products, load_local_products),
}


def _count_values(items, field):
  counter = Counter()
  for item in items:
    counter.update(item["metadata"].get(field, []))
  return counter


def _print_summary(target, data):
  if target == "edu":
    linked = sum(1 for d in data if d["metadata"]["links"])
    videos = sum(
        1 for d in data for link in d["metadata"]["links"]
        if any(h in link for h in ("youtu", "vimeo", ".mp4"))
    )
    print(f"    링크 포함 {linked}/{len(data)}건, 영상 주소 {videos}개")
  elif target == "welfare":
    # 대상별 순서 조정(chat_service.AUDIENCE_TO_WELFARE)에 쓰는 실제 분류값 확인용
    for field, label in (("life", "생애주기"), ("household", "가구 유형"), ("themes", "관심 주제")):
      values = _count_values(data, field)
      shown = ", ".join(f"{v}({n})" for v, n in values.most_common(12))
      print(f"    {label} 값 목록: {shown or '-'}")
  else:
    kinds = Counter(p["kind_name"] for p in data)
    info = load_products_info()
    print(f"    종류별: {dict(kinds)} / 공시 기준월: {info.get('dcls_month')}")
    print("    --- 12개월 정기예금 금리 상위 3건 (확인용) ---")
    groups = search_products("12개월 정기예금", data, top_k=3)
    print("    " + format_products(groups, info.get("dcls_month")).replace("\n", "\n    "))


def _rebuild_vectors(results):
  try:
    from app.graph.vector_store import ingest_fss_data, search_vector
  except Exception as e:  # noqa: BLE001
    print(f"\n[벡터 DB] 사용할 수 없어 건너뜁니다 ({e})")
    return

  tests = {"edu": ("청년 투자", "대출 사기 예방"), "welfare": ("청년 월세 지원", "출산 양육 지원")}
  print("\n[벡터 DB 재구축]")
  for source, queries in tests.items():
    data = results.get(source) or (load_local_welfare() if source == "welfare" else load_local_data())
    if not data:
      print(f"  [{LABELS[source]}] 데이터가 없어 건너뜁니다.")
      continue
    chunks = ingest_fss_data(data, rebuild=True, source=source)
    print(f"  [{LABELS[source]}] 항목 {len(data)}건 / 청크 {chunks}개")
    for q in queries:
      hits = search_vector(q, top_k=3, data=data, source=source)
      names = ", ".join(h["metadata"]["title"] for h in hits) or "(결과 없음 - VECTOR_MAX_DISTANCE를 높여 보세요)"
      print(f"    '{q}' → {names}")


def main(argv=None):
  parser = argparse.ArgumentParser(description="교육/복지/금융상품 데이터를 갱신합니다.")
  parser.add_argument("--only", nargs="+", choices=list(LABELS), help="갱신할 출처 선택")
  parser.add_argument("--offline", action="store_true", help="API를 호출하지 않고 저장본 사용")
  parser.add_argument("--no-vector", action="store_true", help="벡터 DB를 재구축하지 않음")
  args = parser.parse_args(argv)

  logging.basicConfig(level=logging.INFO, format="%(message)s")
  targets = args.only or list(LABELS)

  results = {}
  for target in targets:
    fetch, load = FETCHERS[target]
    print(f"\n[{LABELS[target]}]")
    if args.offline:
      data, mode = load(), "저장본 사용"
    else:
      data = fetch()
      mode = "API에서 갱신"
      if not data:
        data, mode = load(), "API 실패 → 기존 저장본 사용"
    results[target] = data
    print(f"  {mode}: {len(data)}건")
    if data:
      _print_summary(target, data)

  if not args.no_vector and any(t in targets for t in ("edu", "welfare")):
    _rebuild_vectors({t: results.get(t) for t in ("edu", "welfare") if t in targets})

  empty = [LABELS[t] for t in targets if not results.get(t)]
  if empty:
    print(f"\n[주의] 데이터가 없는 출처: {', '.join(empty)} (.env의 키와 네트워크를 확인하세요)")
  print("\n완료. 이어서 `python -m app.graph.chat_service`로 검증하세요.")
  return 1 if len(empty) == len(targets) else 0


if __name__ == "__main__":
  sys.exit(main())
