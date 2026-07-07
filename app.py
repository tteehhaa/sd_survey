"""
app.py — Global Desk / Tops 가설 검증 시스템 (Streamlit 단일 앱)

라우팅
  기본            → [Public] 고객용 설문
  ?admin=1        → [Private] 창업자 전용 대시보드 (비밀번호: admin1234)
  ?ref=<code>     → 바이럴 유입 추적 (누가 공유했는지 referred_by에 저장)

실행:  streamlit run app.py
"""

from __future__ import annotations
import datetime as dt
import urllib.parse

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import content as C
from db import init_db, insert_response, load_responses
from hypotheses import (
    REGIONS, INDUSTRIES, STAGES, PAINS, SALES_STRUCT, LEGAL_STRUCT,
    SIZE_BUCKETS, HYPOTHESIS_MATRIX, match_response, evaluate_hypotheses,
    PAIN_TO_PRODUCT, label, OTHER_CODE, OTHER_LABEL,
)

ADMIN_PASSWORD = "admin1234"
# 배포 후 실제 도메인으로 교체 (공유 링크 생성에 사용)
BASE_URL = "https://tropsinterview202607.streamlit.app"

st.set_page_config(page_title="수출 리스크 자가진단", page_icon="🧭", layout="centered")
init_db()


# ─────────────────────────────────────────────────────────────────────────────
# 공유 UI 헬퍼 (링크복사 + 카톡 붙여넣기용 메시지)
# ─────────────────────────────────────────────────────────────────────────────
def share_widget(share_url: str, message: str, key: str):
    """링크 복사 버튼 + 공유 메시지 텍스트(카톡/문자 붙여넣기용)."""
    st.text_input("공유 링크", value=share_url, key=f"{key}_url")
    components.html(
        f"""
        <button onclick="navigator.clipboard.writeText('{share_url}');
                this.innerText='✅ 링크 복사됨!';"
            style="width:100%;padding:12px;border:0;border-radius:10px;
                   background:#FEE500;color:#191600;font-weight:700;
                   font-size:15px;cursor:pointer;">
            🔗 링크 복사하기 (카톡·문자에 붙여넣기)
        </button>
        """,
        height=56,
    )
    st.caption("아래 메시지를 그대로 복사해 단톡방·지인 대표님께 보내보세요 👇")
    st.code(message, language=None)


# ─────────────────────────────────────────────────────────────────────────────
# 선택 위젯 + '기타(직접 입력)' 헬퍼
#   해당 사항이 없을 때 '기타'를 고르면 자유 입력창이 나타난다.
#   저장 값: 직접 입력 텍스트가 있으면 그 텍스트, 없으면 OTHER_CODE.
# ─────────────────────────────────────────────────────────────────────────────
def select_with_other(widget, label_text, options_dict, key, **kwargs):
    """단일 선택(selectbox/radio) + '기타' 선택 시 직접 입력. 최종 저장 값을 반환."""
    choice = widget(label_text, list(options_dict.keys()),
                    format_func=lambda k: options_dict[k], key=key, **kwargs)
    if choice == OTHER_CODE:
        custom = st.text_input(
            "↳ '기타'를 선택하셨습니다. 직접 입력해 주세요",
            key=f"{key}_etc", placeholder="여기에 직접 입력",
        ).strip()
        return custom or OTHER_CODE
    return choice


def multiselect_with_other(label_text, options_dict, key):
    """복수 선택 + '기타' 선택 시 직접 입력. 최종 저장 값 리스트를 반환."""
    picks = st.multiselect(label_text, list(options_dict.keys()),
                           format_func=lambda k: options_dict[k], key=key)
    if OTHER_CODE in picks:
        custom = st.text_input(
            "↳ '기타'를 선택하셨습니다. 직접 입력해 주세요",
            key=f"{key}_etc", placeholder="여기에 직접 입력",
        ).strip()
        picks = [p for p in picks if p != OTHER_CODE]
        picks.append(custom or OTHER_CODE)
    return picks


# ─────────────────────────────────────────────────────────────────────────────
# [PUBLIC] 고객용 설문
# ─────────────────────────────────────────────────────────────────────────────
def public_survey():
    ref = st.query_params.get("ref", "")

    st.title(C.INTRO_TITLE)
    st.write(C.INTRO_SUB)

    # (a) 시작 화면 바이럴 장치
    # with st.container(border=True):
      #   st.markdown(f"**{C.INTRO_SHARE_LINE}**")
      #   start_share = f"{BASE_URL}/?ref=intro"
      #   share_widget(start_share, C.viral_message_for_respondent(start_share), key="intro")

    #  st.divider()

    if st.session_state.get("submitted"):
        _thank_you_screen()
        return

    st.subheader("1. 회사 기본 정보")
    c1, c2 = st.columns(2)
    company = c1.text_input("회사명 *", key="company")
    homepage = c2.text_input("홈페이지 주소 (URL)", key="homepage")
    c3, c4 = st.columns(2)
    contact = c3.text_input("담당자 성함 *", key="contact")
    phone = c4.text_input("연락처 *", key="phone")
    email = st.text_input("이메일 *", key="email")
    size = select_with_other(st.selectbox, "대략적인 규모", SIZE_BUCKETS, key="size")

    st.subheader("2. 우리 회사는 지금")
    region = select_with_other(st.selectbox, "소재지(권역)", REGIONS, key="region")
    industry = select_with_other(st.selectbox, "주력 업종", INDUSTRIES, key="industry")
    stage = select_with_other(st.radio, "수출 단계", STAGES, key="stage")

    # [NEW] 인력/팀 구조 — 직관적 프레이밍
    st.subheader("3. 해외 거래는 어떻게 운영되나요?")
    st.caption(C.STRUCT_INTRO)
    sales = select_with_other(st.radio, "해외영업·무역 운영 방식", SALES_STRUCT, key="sales")
    legal = select_with_other(st.radio, "계약·법무 검토 방식", LEGAL_STRUCT, key="legal")

    st.subheader("4. 가장 신경 쓰이는 지점")
    top_pain = select_with_other(st.radio, "최우선 애로사항 (하나만)", PAINS, key="top_pain")
    sec_pains = multiselect_with_other("그 외 걸리는 지점 (복수 선택)", PAINS, key="sec_pains")

    st.subheader("5. 솔직하게, 어느 정도 공감하시나요?")
    rv_risk = st.slider(C.RV_RISK, 0, 5, 3, key="rv_risk")
    rv_gap = st.slider(C.RV_GAP, 0, 5, 3, key="rv_gap")

    st.subheader("6. 후속 안내")
    allow_call = st.checkbox("진단 결과·지역 리스크 리포트를 전화로 안내받겠습니다", key="allow_call")
    allow_meeting = st.checkbox("필요 시 대면/화상 미팅으로 더 깊게 진단받고 싶습니다", key="allow_meeting")

    submitted = st.button("진단 결과 보기 →", use_container_width=True, type="primary")

    if submitted:
        if not (company and contact and phone and email):
            st.error("회사명·담당자·연락처·이메일은 필수입니다.")
            return
        response = {
            "region": region, "industry": industry, "export_stage": stage,
            "top_pain": top_pain, "sales_struct": sales, "legal_struct": legal,
        }
        m = match_response(response)
        share_code = f"{company[:6]}-{dt.datetime.now().strftime('%H%M%S')}"
        insert_response({
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
            "company_name": company, "homepage_url": homepage,
            "contact_name": contact, "contact_phone": phone, "contact_email": email,
            "size_bucket": size, "region": region, "industry": industry,
            "export_stage": stage, "top_pain": top_pain,
            "secondary_pains": ",".join(sec_pains),
            "sales_struct": sales, "legal_struct": legal,
            "resonance_risk": rv_risk, "resonance_gap": rv_gap,
            "allow_call": int(allow_call), "allow_meeting": int(allow_meeting),
            "matched_tid": m["tid"], "match_score": m["score"],
            "matched_product": m["product"],
            "referred_by": ref, "share_code": share_code,
        })
        st.session_state["submitted"] = True
        st.session_state["match"] = m
        st.session_state["share_code"] = share_code
        st.rerun()


def _thank_you_screen():
    m = st.session_state.get("match", {})
    st.success(C.DONE_TITLE)
    if m:
        product_line = (
            "‘계약·대금 리스크 가드레일’" if m["product"] == "Tops"
            else "‘해외 운영·커뮤니케이션 실행 지원’"
        )
        st.info(
            f"진단 결과: 귀사는 **{m['persona']}** 유형에 가장 가깝고, "
            f"현재 가장 도움이 될 방향은 {product_line} 입니다."
        )

    # (b) 완료 화면 강력 CTA + 공유 스크립트
    st.divider()
    st.subheader(f"📣 {C.DONE_CTA}")
    st.write(C.DONE_SUB)
    code = st.session_state.get("share_code", "done")
    share_url = f"{BASE_URL}/?ref={urllib.parse.quote(code)}"
    share_widget(share_url, C.viral_message_for_respondent(share_url), key="done")

    if st.button("새 진단 시작"):
        for k in ("submitted", "match", "share_code"):
            st.session_state.pop(k, None)
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# [PRIVATE] 창업자 대시보드
# ─────────────────────────────────────────────────────────────────────────────
def admin_dashboard():
    st.title("🔒 창업자 전용 · 가설 검증 대시보드")

    if not st.session_state.get("auth"):
        pw = st.text_input("비밀번호", type="password")
        if st.button("입장"):
            if pw == ADMIN_PASSWORD:
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")
        return

    df = load_responses()
    st.caption(f"누적 응답 {len(df)}건 · 갱신 {dt.datetime.now():%Y-%m-%d %H:%M}")
    if df.empty:
        st.warning("아직 응답이 없습니다.")
        return

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📊 가설 동적 판정", "📈 가설 vs 실제", "🎯 세일즈 파이프라인", "📥 원본 데이터"]
    )

    # ── Tab1: 동적 판정 (Validated / Pivot / Fail) ──────────────────────────
    with tab1:
        ev = evaluate_hypotheses(df)
        cols = st.columns(4)
        for col, status, emoji in zip(
            cols, ["VALIDATED", "PIVOT", "FAIL", "INSUFFICIENT"], ["✅", "🟡", "🔴", "⚪"]
        ):
            col.metric(f"{emoji} {status}", int((ev["status"] == status).sum()))

        badge = {"VALIDATED": "✅", "PIVOT": "🟡 Pivot", "FAIL": "🔴 Fail",
                 "INSUFFICIENT": "⚪ 데이터부족"}
        view = ev.copy()
        view["판정"] = view["status"].map(badge)
        st.dataframe(
            view[["tid", "persona", "product", "n",
                  "baseline_share_pct", "actual_share_pct",
                  "baseline_meeting_pct", "actual_meeting_pct", "score", "판정"]],
            column_config={
                "tid": "가설", "persona": "페르소나", "product": "상품", "n": "응답수",
                "baseline_share_pct": "기대비중%", "actual_share_pct": "실제비중%",
                "baseline_meeting_pct": "기대미팅%", "actual_meeting_pct": "실제미팅%",
                "score": st.column_config.ProgressColumn("검증점수", min_value=0, max_value=100),
            },
            hide_index=True, use_container_width=True,
        )
        st.caption("점수 = 비중달성률×0.4 + 미팅달성률×0.6 (0~100). "
                   "표본 누적에 따라 상태가 자동 갱신됩니다.")

    # ── Tab2: 기대 vs 실제 비교 시각화 ──────────────────────────────────────
    with tab2:
        st.subheader("애트리뷰트별 실제 분포")
        for attr, dic, title in [
            ("region", REGIONS, "소재지"), ("industry", INDUSTRIES, "업종"),
            ("export_stage", STAGES, "수출단계"), ("top_pain", PAINS, "최우선 애로사항"),
            ("sales_struct", SALES_STRUCT, "해외영업 인력구조"),
            ("legal_struct", LEGAL_STRUCT, "법무 인력구조"),
        ]:
            vc = df[attr].map(lambda k: label(dic, k)).value_counts()
            st.markdown(f"**{title}**")
            st.bar_chart(vc)

        st.subheader("상품군 반응 (매칭된 주력 상품 기준)")
        prod = df["matched_product"].value_counts()
        st.bar_chart(prod)
        st.caption("무역 리스크 가드레일(Tops) vs 크로스보더 운영지원(Global Desk) 수요 비중")

    # ── Tab3: 세일즈 파이프라인 (미팅 허락 리드 우선) ───────────────────────
    with tab3:
        st.subheader("미팅 허락 리드 우선순위")
        leads = df[df["allow_meeting"] == 1].copy()
        if leads.empty:
            leads = df[df["allow_call"] == 1].copy()
            st.caption("미팅 허락 리드가 없어 콜 허락 리드를 표시합니다.")
        if leads.empty:
            st.info("후속 컨택을 허락한 리드가 아직 없습니다.")
        else:
            leads["규모"] = leads["size_bucket"].map(lambda k: label(SIZE_BUCKETS, k))
            leads["해외영업구조"] = leads["sales_struct"].map(lambda k: label(SALES_STRUCT, k))
            leads["법무구조"] = leads["legal_struct"].map(lambda k: label(LEGAL_STRUCT, k))
            leads = leads.sort_values("match_score", ascending=False)
            st.dataframe(
                leads[["company_name", "homepage_url", "규모", "해외영업구조", "법무구조",
                       "matched_tid", "matched_product", "match_score",
                       "contact_name", "contact_phone", "contact_email"]],
                column_config={
                    "company_name": "회사명",
                    "homepage_url": st.column_config.LinkColumn("홈페이지"),
                    "matched_tid": "가설", "matched_product": "제안상품",
                    "match_score": "일치율", "contact_name": "담당자",
                    "contact_phone": "연락처", "contact_email": "이메일",
                },
                hide_index=True, use_container_width=True,
            )

    # ── Tab4: 원본 + 지인 배포 메시지 ───────────────────────────────────────
    with tab4:
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.download_button("CSV 내려받기", df.to_csv(index=False).encode("utf-8-sig"),
                           "responses.csv", "text/csv")
        st.divider()
        st.subheader("📨 지인 배포용 메시지")
        outreach_url = f"{BASE_URL}/?ref=founder"
        st.markdown("**카카오톡/문자**")
        st.code(C.founder_outreach_message(outreach_url), language=None)
        st.markdown("**이메일**")
        st.code(C.email_template(outreach_url), language=None)


# ─────────────────────────────────────────────────────────────────────────────
# 라우팅
# ─────────────────────────────────────────────────────────────────────────────
if st.query_params.get("admin") == "1":
    admin_dashboard()
else:
    public_survey()
