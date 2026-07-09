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
from db import init_db, insert_response, load_responses, set_excluded
from hypotheses import (
    REGIONS, INDUSTRIES, STAGES, PAINS, SALES_STRUCT, LEGAL_STRUCT,
    SIZE_BUCKETS, HYPOTHESIS_MATRIX, match_response, evaluate_hypotheses,
    PAIN_TO_PRODUCT, label, OTHER_CODE, OTHER_LABEL,
    DELEGATE_STAGES, UNEXPECTED_PROBLEMS, PMO_ROLES,
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


def multiselect_with_other(label_text, options_dict, key, **kwargs):
    """복수 선택 + '기타' 선택 시 직접 입력. 최종 저장 값 리스트를 반환.
    max_selections 등 st.multiselect의 추가 인자는 kwargs로 전달된다."""
    picks = st.multiselect(label_text, list(options_dict.keys()),
                           format_func=lambda k: options_dict[k], key=key, **kwargs)
    if OTHER_CODE in picks:
        custom = st.text_input(
            "↳ '기타'를 선택하셨습니다. 직접 입력해 주세요",
            key=f"{key}_etc", placeholder="여기에 직접 입력",
        ).strip()
        picks = [p for p in picks if p != OTHER_CODE]
        picks.append(custom or OTHER_CODE)
    return picks


# ─────────────────────────────────────────────────────────────────────────────
# 설문 시각 스타일 + 문항 번호 헬퍼 (대표님 가독성용)
#   질문 하나 = 카드 하나 = 번호 하나. 문항이 섞이지 않도록 개별 넘버링한다.
# ─────────────────────────────────────────────────────────────────────────────
FORM_CSS = """
<style>
/* 한글 가독성이 좋은 시스템 폰트 스택 */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
                 "Malgun Gothic", "Noto Sans KR", "Segoe UI", sans-serif;
}
.part-h   { font-size:1.2rem; font-weight:800; letter-spacing:-.3px;
            margin:1.4rem 0 .3rem; }
.q-title  { font-size:1.04rem; font-weight:700; line-height:1.55; margin:.05rem 0; }
.q-num    { display:inline-block; background:#2563eb; color:#fff; font-size:.78rem;
            font-weight:700; border-radius:6px; padding:2px 9px; margin-right:9px;
            vertical-align:middle; letter-spacing:.4px; }
.q-hint   { color:#6b7280; font-size:.86rem; margin:.1rem 0 .45rem; }
.req      { color:#dc2626; font-weight:800; }
/* 질문 카드 간 여백 살짝 */
div[data-testid="stVerticalBlockBorderWrapper"] { margin-bottom:.35rem; }
</style>
"""


def q_label(num, question, hint=None, required=False):
    """번호 배지 + 질문 문구(+선택 힌트)를 카드 상단에 렌더."""
    star = " <span class='req'>*</span>" if required else ""
    st.markdown(
        f"<div class='q-title'><span class='q-num'>Q{num}</span>{question}{star}</div>",
        unsafe_allow_html=True,
    )
    if hint:
        st.markdown(f"<div class='q-hint'>{hint}</div>", unsafe_allow_html=True)


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

    st.markdown(FORM_CSS, unsafe_allow_html=True)

    # ── 회사 기본 정보 (연락처 폼) ──────────────────────────────────────────
    st.markdown("<div class='part-h'>📋 회사 기본 정보</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='q-hint'>진단 결과를 안내드리기 위한 정보입니다. "
        "<span class='req'>*</span> 는 필수 항목입니다.</div>",
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        c1, c2 = st.columns(2)
        company = c1.text_input("회사명 *", key="company")
        homepage = c2.text_input("홈페이지 주소 (URL)", key="homepage")
        c3, c4 = st.columns(2)
        contact = c3.text_input("담당자 성함 *", key="contact")
        phone = c4.text_input("연락처 *", key="phone")
        email = st.text_input("이메일 *", key="email")
        size = select_with_other(st.selectbox, "대략적인 회사 규모", SIZE_BUCKETS, key="size")

    # ── 우리 회사는 지금 ────────────────────────────────────────────────────
    st.markdown("<div class='part-h'>🌏 우리 회사는 지금</div>", unsafe_allow_html=True)
    with st.container(border=True):
        q_label(1, "회사 소재지(권역)")
        region = select_with_other(st.selectbox, "소재지(권역)", REGIONS,
                                   key="region", label_visibility="collapsed")
    with st.container(border=True):
        q_label(2, "주력 업종")
        industry = select_with_other(st.selectbox, "주력 업종", INDUSTRIES,
                                     key="industry", label_visibility="collapsed")
    with st.container(border=True):
        q_label(3, "현재 수출 단계")
        stage = select_with_other(st.radio, "수출 단계", STAGES,
                                  key="stage", label_visibility="collapsed")

    # ── 해외 거래 운영 방식 (인력/팀 구조) ──────────────────────────────────
    st.markdown("<div class='part-h'>🧩 해외 거래 운영 방식</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='q-hint'>{C.STRUCT_INTRO}</div>", unsafe_allow_html=True)
    with st.container(border=True):
        q_label(4, "해외영업·무역은 현재 어떻게 운영하고 계신가요?")
        sales = select_with_other(st.radio, "해외영업·무역 운영 방식", SALES_STRUCT,
                                  key="sales", label_visibility="collapsed")
    with st.container(border=True):
        q_label(5, "계약·법무 검토는 어떻게 하고 계신가요?")
        legal = select_with_other(st.radio, "계약·법무 검토 방식", LEGAL_STRUCT,
                                  key="legal", label_visibility="collapsed")

    # ── 애로사항 진단 ───────────────────────────────────────────────────────
    st.markdown("<div class='part-h'>⚠️ 애로사항 진단</div>", unsafe_allow_html=True)
    with st.container(border=True):
        q_label(6, "가장 신경 쓰이는 최우선 애로사항은 무엇입니까?", hint="하나만 선택해 주세요.")
        top_pain = select_with_other(st.radio, "최우선 애로사항", PAINS,
                                     key="top_pain", label_visibility="collapsed")
    with st.container(border=True):
        q_label(7, "그 외에도 걸리는 지점이 있다면 골라주세요.", hint="복수 선택 가능")
        sec_pains = multiselect_with_other("그 외 걸리는 지점", PAINS,
                                           key="sec_pains", label_visibility="collapsed")
    with st.container(border=True):
        q_label(8, "해외 진출 과정에서 다음과 같은 '예상치 못한 실무적 문제'를 "
                   "겪었거나 우려하신 적이 있습니까?", hint="복수 선택 가능")
        unexpected = multiselect_with_other("예상치 못한 실무적 문제", UNEXPECTED_PROBLEMS,
                                            key="unexpected_problems",
                                            label_visibility="collapsed")

    # ── 외부 위임·솔루션 니즈 ───────────────────────────────────────────────
    st.markdown("<div class='part-h'>🚀 외부 위임·솔루션 니즈</div>", unsafe_allow_html=True)
    with st.container(border=True):
        q_label(9, "해외 진출(수출) 시, 외부 전문가(운영팀)에게 통째로 맡기고 싶은 단계는?",
                hint="최대 2개까지 선택 가능")
        delegate = multiselect_with_other("통째로 맡기고 싶은 단계", DELEGATE_STAGES,
                                          key="delegate_stages", max_selections=2,
                                          label_visibility="collapsed")
    with st.container(border=True):
        q_label(10, "'필요할 때만 쓰는 외부 글로벌 운영팀(Fractional PMO)'이 있다면, "
                    "어떤 역할을 가장 기대하십니까?", hint="가장 기대하는 역할 하나를 선택해 주세요.")
        pmo_role = select_with_other(st.radio, "Fractional PMO 기대 역할", PMO_ROLES,
                                     key="pmo_role", label_visibility="collapsed")

    # ── 솔직한 공감도 ───────────────────────────────────────────────────────
    st.markdown("<div class='part-h'>💬 솔직한 공감도</div>", unsafe_allow_html=True)
    with st.container(border=True):
        q_label(11, C.RV_RISK, hint="0 = 전혀 아니다  ·  5 = 매우 그렇다")
        rv_risk = st.slider("리스크 공감도", 0, 5, 3, key="rv_risk",
                            label_visibility="collapsed")
    with st.container(border=True):
        q_label(12, C.RV_GAP, hint="0 = 전혀 아니다  ·  5 = 매우 그렇다")
        rv_gap = st.slider("실행 공백 공감도", 0, 5, 3, key="rv_gap",
                           label_visibility="collapsed")

    # ── 후속 안내 ───────────────────────────────────────────────────────────
    st.markdown("<div class='part-h'>🤝 후속 안내</div>", unsafe_allow_html=True)
    with st.container(border=True):
        q_label(13, "진단 이후, 어떤 후속 안내를 원하시나요?",
                hint="원하시는 항목을 체크해 주세요. (선택)")
        allow_call = st.checkbox("진단 결과·지역 리스크 리포트를 전화로 안내받겠습니다",
                                 key="allow_call")
        allow_meeting = st.checkbox("필요 시 대면/화상 미팅으로 더 깊게 진단받고 싶습니다",
                                    key="allow_meeting")

    st.markdown("")
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
            "delegate_stages": ",".join(delegate),
            "unexpected_problems": ",".join(unexpected),
            "pmo_role": pmo_role,
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

    # ── THÉONÉ 홍보 마무리 섹션 ──────────────────────────────────────────────
    st.divider()
    st.success(C.THEONE_THANKS)
    with st.container(border=True):
        st.markdown(C.THEONE_PROMO)

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

    df_all = load_responses()
    if df_all.empty:
        st.caption(f"누적 응답 0건 · 갱신 {dt.datetime.now():%Y-%m-%d %H:%M}")
        st.warning("아직 응답이 없습니다.")
        return

    # 분석에서 제외(테스트/노이즈) 처리된 응답을 걸러낸 '분석 대상'
    n_excluded = int((df_all["excluded"] == 1).sum())
    df = df_all[df_all["excluded"] == 0].copy()
    st.caption(
        f"누적 응답 {len(df_all)}건 · 분석 대상 {len(df)}건 · 제외 {n_excluded}건 · "
        f"갱신 {dt.datetime.now():%Y-%m-%d %H:%M}"
    )
    if df.empty:
        st.warning("모든 응답이 분석 제외 상태입니다. '🧹 데이터 정리' 탭에서 복원하세요.")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📊 가설 동적 판정", "📈 가설 vs 실제", "🎯 세일즈 파이프라인",
         "📥 원본 데이터", "🧹 데이터 정리"]
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
        st.caption("전체 원본(제외 처리분 포함). 분석 제외 여부는 excluded 컬럼(1=제외).")
        st.dataframe(df_all, hide_index=True, use_container_width=True)
        st.download_button("전체 CSV 내려받기",
                           df_all.to_csv(index=False).encode("utf-8-sig"),
                           "responses_all.csv", "text/csv")
        st.download_button("분석 대상만 CSV 내려받기",
                           df.to_csv(index=False).encode("utf-8-sig"),
                           "responses_active.csv", "text/csv")
        st.divider()
        st.subheader("📨 지인 배포용 메시지")
        outreach_url = f"{BASE_URL}/?ref=founder"
        st.markdown("**카카오톡/문자**")
        st.code(C.founder_outreach_message(outreach_url), language=None)
        st.markdown("**이메일**")
        st.code(C.email_template(outreach_url), language=None)

    # ── Tab5: 데이터 정리 (테스트/노이즈 분석 제외 · 복원) ────────────────────
    with tab5:
        st.subheader("🧹 테스트·노이즈 데이터 분석 제외")
        st.caption(
            "체크한 응답은 분석(가설 판정·분포·파이프라인)에서 제외됩니다. "
            "**데이터는 삭제되지 않으며** 체크 해제로 언제든 복원할 수 있습니다."
        )
        cols_show = ["id", "created_at", "company_name", "contact_name",
                     "contact_phone", "matched_tid", "matched_product", "excluded"]
        editor_src = df_all[cols_show].copy()
        editor_src["제외"] = editor_src["excluded"] == 1
        editor_src = editor_src.drop(columns=["excluded"])
        edited = st.data_editor(
            editor_src,
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "created_at": st.column_config.TextColumn("응답시각", disabled=True),
                "company_name": st.column_config.TextColumn("회사명", disabled=True),
                "contact_name": st.column_config.TextColumn("담당자", disabled=True),
                "contact_phone": st.column_config.TextColumn("연락처", disabled=True),
                "matched_tid": st.column_config.TextColumn("가설", disabled=True),
                "matched_product": st.column_config.TextColumn("제안상품", disabled=True),
                "제외": st.column_config.CheckboxColumn(
                    "분석 제외", help="체크 시 분석에서 제외(데이터는 보존)"),
            },
            hide_index=True, use_container_width=True, key="exclude_editor",
        )
        if st.button("변경 저장", type="primary"):
            new_flag = dict(zip(edited["id"].astype(int), edited["제외"]))
            cur_flag = dict(zip(df_all["id"].astype(int), df_all["excluded"] == 1))
            to_exclude = [i for i, v in new_flag.items() if v and not cur_flag.get(i, False)]
            to_include = [i for i, v in new_flag.items() if not v and cur_flag.get(i, False)]
            set_excluded(to_exclude, 1)
            set_excluded(to_include, 0)
            if to_exclude or to_include:
                st.success(f"제외 {len(to_exclude)}건 · 복원 {len(to_include)}건 반영했습니다.")
                st.rerun()
            else:
                st.info("변경된 항목이 없습니다.")


# ─────────────────────────────────────────────────────────────────────────────
# 라우팅
# ─────────────────────────────────────────────────────────────────────────────
if st.query_params.get("admin") == "1":
    admin_dashboard()
else:
    public_survey()
