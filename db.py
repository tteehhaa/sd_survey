"""
db.py — SQLite 저장소.
'고객사 정보' + '[NEW] 인력/팀 구조' + 애트리뷰트 응답 + 매칭 결과 + 바이럴(referral)을
하나의 responses 테이블에 통합 저장한다.
"""

from __future__ import annotations
import sqlite3
from contextlib import contextmanager
import pandas as pd

DB_PATH = "survey.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL,
    -- 고객사 정보
    company_name    TEXT,
    homepage_url    TEXT,
    contact_name    TEXT,
    contact_phone   TEXT,
    contact_email   TEXT,
    size_bucket     TEXT,
    -- 애트리뷰트
    region          TEXT,
    industry        TEXT,
    export_stage    TEXT,
    top_pain        TEXT,
    secondary_pains TEXT,     -- 콤마 구분
    -- [NEW] 인력/팀 구조
    sales_struct    TEXT,
    legal_struct    TEXT,
    -- 리얼보이스 공감도 (0~5)
    resonance_risk  INTEGER,  -- "리스크가 남 일 같지 않다"
    resonance_gap   INTEGER,  -- "실행 공백을 느낀다"
    -- 후속 컨택 동의
    allow_call      INTEGER DEFAULT 0,
    allow_meeting   INTEGER DEFAULT 0,
    -- 매칭 결과
    matched_tid     TEXT,
    match_score     REAL,
    matched_product TEXT,
    -- 바이럴
    referred_by     TEXT,     -- 유입 ref 코드(누가 공유했는지)
    share_code      TEXT,     -- 이 응답자에게 발급된 공유 코드
    -- 관리자용 소프트 삭제: 1이면 테스트/노이즈로 분석에서 제외(데이터는 보존)
    excluded        INTEGER DEFAULT 0
);
"""

# 기존 DB에 뒤늦게 추가된 컬럼 — init_db()에서 없으면 ALTER로 채운다.
MIGRATIONS = {
    "excluded": "ALTER TABLE responses ADD COLUMN excluded INTEGER DEFAULT 0",
}


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as c:
        c.executescript(SCHEMA)
        # 기존 DB 마이그레이션: 누락된 컬럼을 안전하게 추가
        existing = {row[1] for row in c.execute("PRAGMA table_info(responses)")}
        for col, ddl in MIGRATIONS.items():
            if col not in existing:
                c.execute(ddl)


def set_excluded(ids: list[int], excluded: int) -> None:
    """지정한 응답 id들의 분석 제외 플래그를 설정(1=제외, 0=복원). 데이터는 삭제하지 않는다."""
    if not ids:
        return
    with get_conn() as c:
        c.executemany(
            "UPDATE responses SET excluded = ? WHERE id = ?",
            [(int(excluded), int(i)) for i in ids],
        )


def insert_response(data: dict) -> int:
    cols = [
        "created_at", "company_name", "homepage_url", "contact_name", "contact_phone",
        "contact_email", "size_bucket", "region", "industry", "export_stage",
        "top_pain", "secondary_pains", "sales_struct", "legal_struct",
        "resonance_risk", "resonance_gap", "allow_call", "allow_meeting",
        "matched_tid", "match_score", "matched_product", "referred_by", "share_code",
    ]
    with get_conn() as c:
        cur = c.execute(
            f"INSERT INTO responses ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
            [data.get(k) for k in cols],
        )
        return cur.lastrowid


def load_responses() -> pd.DataFrame:
    with get_conn() as c:
        df = pd.read_sql_query("SELECT * FROM responses ORDER BY created_at DESC", c)
    if not df.empty:
        for col in ("allow_call", "allow_meeting", "excluded"):
            if col in df.columns:
                df[col] = df[col].fillna(0).astype(int)
    return df
