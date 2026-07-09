"""
db.py — Supabase(Postgres) 저장소.
'고객사 정보' + '인력/팀 구조' + '외부 위임·솔루션 니즈' + 애트리뷰트 응답 +
매칭 결과 + 바이럴(referral)을 하나의 responses 테이블에 통합 저장한다.

※ 테이블은 supabase_schema.sql을 Supabase SQL Editor에서 1회 실행해 미리 만든다.
※ 연결 정보(SUPABASE_URL / SUPABASE_KEY)는 .streamlit/secrets.toml 또는
  Streamlit Cloud의 Secrets에 저장한다. (커밋 금지)
"""

from __future__ import annotations
import pandas as pd
import streamlit as st
from supabase import create_client, Client

TABLE = "responses"

# insert 시 사용할 컬럼(= 앱이 채워 넣는 값). created_at 포함.
INSERT_COLS = [
    "created_at", "company_name", "homepage_url", "contact_name", "contact_phone",
    "contact_email", "size_bucket", "region", "industry", "export_stage",
    "top_pain", "secondary_pains", "sales_struct", "legal_struct",
    "delegate_stages", "unexpected_problems", "pmo_role",
    "resonance_risk", "resonance_gap", "allow_call", "allow_meeting",
    "matched_tid", "match_score", "matched_product", "referred_by", "share_code",
]


@st.cache_resource
def get_client() -> Client:
    """Supabase 클라이언트(세션 내 1회 생성 후 재사용)."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def init_db() -> None:
    """
    테이블은 Supabase(supabase_schema.sql)에서 사전 생성하므로 여기선 no-op.
    (연결 자체는 첫 insert/select 시점에 검증된다.)
    """
    return None


def insert_response(data: dict) -> int:
    """설문 응답 1건을 저장하고 새 행의 id를 반환."""
    row = {k: data.get(k) for k in INSERT_COLS}
    res = get_client().table(TABLE).insert(row).execute()
    return int(res.data[0]["id"]) if res.data else -1


def set_excluded(ids: list[int], excluded: int) -> None:
    """지정 id들의 분석 제외 플래그 설정(1=제외, 0=복원). 데이터는 삭제하지 않는다."""
    if not ids:
        return
    (get_client().table(TABLE)
        .update({"excluded": int(excluded)})
        .in_("id", [int(i) for i in ids])
        .execute())


def load_responses() -> pd.DataFrame:
    """전체 응답을 최신순 DataFrame으로 반환(기존 SQLite 버전과 동일한 컬럼 계약)."""
    res = get_client().table(TABLE).select("*").order("created_at", desc=True).execute()
    df = pd.DataFrame(res.data or [])
    if not df.empty:
        for col in ("allow_call", "allow_meeting", "excluded"):
            if col in df.columns:
                df[col] = df[col].fillna(0).astype(int)
    return df
