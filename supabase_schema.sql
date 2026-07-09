-- ─────────────────────────────────────────────────────────────────────────────
-- Supabase 테이블 생성 스크립트
-- 사용법: Supabase 대시보드 → 왼쪽 메뉴 "SQL Editor" → New query →
--         이 파일 전체를 붙여넣고 "Run" 실행 (한 번만).
-- ─────────────────────────────────────────────────────────────────────────────

create table if not exists public.responses (
    id                  bigint generated always as identity primary key,
    created_at          timestamptz not null default now(),
    -- 고객사 정보
    company_name        text,
    homepage_url        text,
    contact_name        text,
    contact_phone       text,
    contact_email       text,
    size_bucket         text,
    -- 애트리뷰트
    region              text,
    industry            text,
    export_stage        text,
    top_pain            text,
    secondary_pains     text,
    -- 인력/팀 구조
    sales_struct        text,
    legal_struct        text,
    -- 외부 위임·솔루션 니즈
    delegate_stages     text,
    unexpected_problems text,
    pmo_role            text,
    -- 리얼보이스 공감도 (0~5)
    resonance_risk      integer,
    resonance_gap       integer,
    -- 후속 컨택 동의
    allow_call          integer default 0,
    allow_meeting       integer default 0,
    -- 매칭 결과
    matched_tid         text,
    match_score         real,
    matched_product     text,
    -- 바이럴
    referred_by         text,
    share_code          text,
    -- 관리자용 소프트 삭제 (1=분석 제외)
    excluded            integer default 0
);

-- 최신순 조회 최적화
create index if not exists responses_created_at_idx
    on public.responses (created_at desc);

-- ─────────────────────────────────────────────────────────────────────────────
-- Row Level Security (RLS)
--   퍼블리셔블(anon) 키로 설문 저장·조회·소프트삭제가 가능하도록 정책을 연다.
--   ※ 이 앱은 서버 사이드(Streamlit)에서만 키를 사용하므로 키가 브라우저에 노출되지 않음.
--   ※ 더 강한 보안을 원하면 secret 키(service_role) 사용으로 전환 권장(아래 정책 불필요).
-- ─────────────────────────────────────────────────────────────────────────────
alter table public.responses enable row level security;

drop policy if exists "anon can insert" on public.responses;
create policy "anon can insert" on public.responses
    for insert to anon with check (true);

drop policy if exists "anon can select" on public.responses;
create policy "anon can select" on public.responses
    for select to anon using (true);

drop policy if exists "anon can update" on public.responses;
create policy "anon can update" on public.responses
    for update to anon using (true) with check (true);
