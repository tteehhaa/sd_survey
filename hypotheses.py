"""
hypotheses.py
─────────────────────────────────────────────────────────────────────────────
가설 매트릭스(T1~T30) 정의 + 룰 기반 실시간 분류 로직.

설계 원칙
- 애트리뷰트 4종(소재지/업종/수출단계/애로사항) + [NEW] 인력구조 2종을
  하나의 스키마로 통합한다.
- 30개 타겟 셀은 "창업자가 사전에 세운 가설(prior)"이다. 각 셀은
  - 기대 응답 비중(baseline_share)      : 이 페르소나가 전체 응답의 몇 %를 차지할 것이라 봤는가
  - 기대 미팅 허락률(baseline_meeting)  : 이 페르소나가 얼마나 강하게 반응(콜/미팅)할 것이라 봤는가
  - 주력 제안 상품(product)             : 이 페르소나에게 무엇을 팔 것인가 (Global Desk / Tops)
  을 미리 값으로 갖는다. 이 prior를 실제 설문 데이터와 대조해 Validated/Pivot/Fail을 판정한다.
"""

from __future__ import annotations
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# 1. 애트리뷰트 사전 (라벨 = 화면 노출 텍스트, 코드 = 저장/매칭 키)
# ─────────────────────────────────────────────────────────────────────────────

# 소재지: 지방 5개 권역 (수도권은 타겟 외이므로 매트릭스에서 제외)
# 각 항목의 "기타(직접 입력)" 옵션 코드 — 선택 시 응답자가 직접 텍스트를 입력한다.
OTHER_CODE = "__ETC__"
OTHER_LABEL = "기타 (직접 입력)"

REGIONS = {
    "R_CHUNG": "충청권 (대전·세종·충남북)",
    "R_HONAM": "호남권 (광주·전남북)",
    "R_DAEGU": "대경권 (대구·경북)",
    "R_DONGN": "동남권 (부산·울산·경남)",
    "R_GANGW": "강원권 (강원·제주)",
    "R_SEOUL": "수도권 (서울·경기·인천)",
    OTHER_CODE: OTHER_LABEL,
}

# 업종: 제조 5개
INDUSTRIES = {
    "I_AUTO": "자동차부품",
    "I_MACH": "기계·장비",
    "I_ELEC": "전기·전자",
    "I_CHEM": "화학·소재",
    "I_METAL": "금속가공",
    "I_SERV": "서비스업·기타",
    "I_BEAUTY": "화장품·바이오·화학소재",
    OTHER_CODE: OTHER_LABEL,
}

# 수출 단계: 3단계
STAGES = {
    "E_EARLY": "수출 준비·초기 (간접수출/첫 오더 단계)",
    "E_GROWTH": "수출 성장기 (직수출·거래처 확대 중)",
    "E_SCALE": "수출 확대·다변화기 (다국가·대형 계약)",
    OTHER_CODE: OTHER_LABEL,
}

# 애로사항: 4개 키워드
PAINS = {
    "P_LEGAL": "계약·법률 리스크 (계약서 검토, 분쟁, 클레임)",
    "P_FRAUD": "무역사기·대금 회수 (미수금, 사기, 신용리스크)",
    "P_COMM": "바이어 커뮤니케이션·언어 (상담, 협상, 응대 공백)",
    "P_LOGIS": "물류·통관·인증 (선적, 통관, 규격/인증 대응)",
    "P_LEGAL_MIDDLE_EAST": "중동 현지법/Sponsor 및 영문 NDA 독소조항 리스크",
    "P_REGULATION_ASIA": "일본/러시아 등 국가별 복잡한 통관·인증 요건 및 제재",
    OTHER_CODE: OTHER_LABEL,
}

# [NEW] 인력구조 a) 해외영업/무역 전담
SALES_STRUCT = {
    "S_TEAM": "해외영업·무역 전담 팀 있음",
    "S_FEW": "담당자 1~2명이 전담",
    "S_NONE": "전담 인력 없음 (대표·기존 직원이 겸임)",
    OTHER_CODE: OTHER_LABEL,
}

# [NEW] 인력구조 b) 사내 법무/계약 검토
LEGAL_STRUCT = {
    "L_TEAM": "사내 법무팀 있음",
    "L_EXT": "외부 자문 로펌 이용 중",
    "L_NONE": "전담 변호사·로펌 없음 (내부 자체 검토)",
    OTHER_CODE: OTHER_LABEL,
}

# 규모 (선택형)
SIZE_BUCKETS = {
    "Z_S": "소기업 (임직원 ~50명 / 매출 ~100억)",
    "Z_M": "중소기업 (임직원 50~150명 / 매출 100~500억)",
    "Z_L": "중견 (임직원 150명+ / 매출 500억+)",
    OTHER_CODE: OTHER_LABEL,
}

# ─────────────────────────────────────────────────────────────────────────────
# [NEW] 외부 위임·솔루션 니즈 문항 (Pain Point & Solution 검증용)
#   저장만 하고 가설 매칭(MATCH_WEIGHTS)에는 반영하지 않는다. (수요 신호 수집용)
# ─────────────────────────────────────────────────────────────────────────────

# Q1) 통째로 외부에 맡기고 싶은 단계 (최대 2개 선택)
DELEGATE_STAGES = {
    "D_DISCOVERY": "기회 발굴 및 초기 소통 (바이어 발굴, 초기 영문 콜드메일 작성 및 NDA 체결)",
    "D_NEGOTIATION": "조건 협상 및 계약 (영문 계약서 조항 검토, 독점권·단가 등 비즈니스 조건 협상)",
    "D_COMPLIANCE": "컴플라이언스 및 통관 (수출 신고, HS코드 분류, 현지 규제·인증 확인)",
    "D_RISK": "리스크 및 사후 관리 (대금 회수(K-SURE 연계 등), 클레임 방어 및 현지 파트너 관리)",
    "D_ALL": "전체 위임 (특정 단계가 아닌 위 전체 과정을 챙겨주는 '외부 전담 실무팀(PMO)'이 필요)",
    OTHER_CODE: OTHER_LABEL,
}

# Q2) 겪었거나 우려한 '예상치 못한 실무적 문제' (복수 선택)
UNEXPECTED_PROBLEMS = {
    "U_TOXIC": "상대방이 보내온 영문 계약서의 독소 조항을 걸러낼 내부 인력이 없음",
    "U_CUSTOMS": "샘플 발송 등 소량 수출 시 수출신고·통관 절차를 몰라 사후 페널티·곤란을 겪을까 우려됨",
    "U_REGUL": "파트너십 체결 후 현지 규제(인증·라벨링 등)를 몰라 물건이 묶이거나 계약이 지연됨",
    "U_NETWORK": "문제가 터졌을 때 즉시 물어보고 해결해 줄 전문가(변호사·관세사 등) 네트워크가 없음",
    OTHER_CODE: OTHER_LABEL,
}

# Q3) 'Fractional PMO'가 있다면 가장 기대하는 역할 (하나 선택)
PMO_ROLES = {
    "M_EXECUTE": "직접 실행: 번역기 수준을 넘어선 전문 영문 이메일·비즈니스 서류 즉각 작성",
    "M_HUB": "전문가 허브: 사안에 맞춰 검증된 관세사·현지 변호사 등 적합한 전문가를 즉시 연결·통역/조율",
    "M_GOV": "정부 지원 연계: K-SURE(무역보험공사), KOTRA 등 정부 지원 사업·바우처를 알아서 찾아 연결",
    "M_MANAGE": "프로젝트 관리: 바이어 발굴부터 선적·대금 회수까지 전체 일정의 딜레이가 없도록 매니징",
    OTHER_CODE: OTHER_LABEL,
}

# 애로사항 → 주력 상품 매핑
#   Tops        : 무역 리스크(계약/법무/사기/대금) 가드레일
#   Global Desk : 크로스보더 운영/커뮤니케이션 실행 대행
PAIN_TO_PRODUCT = {
    "P_LEGAL": "Tops",
    "P_FRAUD": "Tops",
    "P_COMM": "Global Desk",
    "P_LOGIS": "Global Desk",
    "P_LEGAL_MIDDLE_EAST": "Tops",        # 준거법·NDA 독소조항 → 리스크 가드레일
    "P_REGULATION_ASIA": "Global Desk",   # 국가별 인증·제재 대응 → 크로스보더 운영지원
}


# ─────────────────────────────────────────────────────────────────────────────
# 2. 가설 매트릭스 (T1~T30) 시드
#    (region, industry, stage, sales, legal, pain, baseline_share%, baseline_meeting%)
#    창업자의 사전 가설값. 실제 값과 비교하기 위한 기준선.
# ─────────────────────────────────────────────────────────────────────────────

_SEED = [
    # 동남권 자동차부품 — 창업자가 1순위로 본 밀집 클러스터
    ("R_DONGN", "I_AUTO",  "E_GROWTH", "S_FEW",  "L_NONE", "P_LEGAL", 7.0, 45),
    ("R_DONGN", "I_AUTO",  "E_SCALE",  "S_TEAM", "L_EXT",  "P_FRAUD", 5.0, 40),
    ("R_DONGN", "I_MACH",  "E_GROWTH", "S_FEW",  "L_NONE", "P_COMM",  6.0, 50),
    ("R_DONGN", "I_METAL", "E_EARLY",  "S_NONE", "L_NONE", "P_COMM",  5.0, 55),
    ("R_DONGN", "I_CHEM",  "E_SCALE",  "S_TEAM", "L_TEAM", "P_LEGAL", 3.0, 30),
    # 대경권
    ("R_DAEGU", "I_AUTO",  "E_GROWTH", "S_FEW",  "L_NONE", "P_LEGAL", 5.0, 42),
    ("R_DAEGU", "I_ELEC",  "E_GROWTH", "S_FEW",  "L_EXT",  "P_FRAUD", 4.0, 38),
    ("R_DAEGU", "I_MACH",  "E_EARLY",  "S_NONE", "L_NONE", "P_COMM",  5.0, 52),
    ("R_DAEGU", "I_METAL", "E_EARLY",  "S_NONE", "L_NONE", "P_LOGIS", 4.0, 40),
    ("R_DAEGU", "I_CHEM",  "E_GROWTH", "S_FEW",  "L_NONE", "P_LEGAL", 3.0, 35),
    # 충청권
    ("R_CHUNG", "I_ELEC",  "E_GROWTH", "S_FEW",  "L_EXT",  "P_FRAUD", 4.0, 40),
    ("R_CHUNG", "I_CHEM",  "E_SCALE",  "S_TEAM", "L_EXT",  "P_LEGAL", 3.0, 32),
    ("R_CHUNG", "I_MACH",  "E_GROWTH", "S_FEW",  "L_NONE", "P_COMM",  4.0, 48),
    ("R_CHUNG", "I_AUTO",  "E_EARLY",  "S_NONE", "L_NONE", "P_COMM",  4.0, 50),
    ("R_CHUNG", "I_ELEC",  "E_EARLY",  "S_NONE", "L_NONE", "P_LOGIS", 3.0, 44),
    # 호남권
    ("R_HONAM", "I_CHEM",  "E_GROWTH", "S_FEW",  "L_NONE", "P_FRAUD", 3.0, 42),
    ("R_HONAM", "I_METAL", "E_EARLY",  "S_NONE", "L_NONE", "P_COMM",  3.0, 55),
    ("R_HONAM", "I_MACH",  "E_GROWTH", "S_FEW",  "L_NONE", "P_LEGAL", 3.0, 38),
    ("R_HONAM", "I_AUTO",  "E_EARLY",  "S_NONE", "L_NONE", "P_LOGIS", 2.0, 40),
    ("R_HONAM", "I_ELEC",  "E_SCALE",  "S_TEAM", "L_EXT",  "P_FRAUD", 2.0, 30),
    # 강원권
    ("R_GANGW", "I_CHEM",  "E_EARLY",  "S_NONE", "L_NONE", "P_COMM",  2.0, 50),
    ("R_GANGW", "I_MACH",  "E_EARLY",  "S_NONE", "L_NONE", "P_LOGIS", 2.0, 45),
    ("R_GANGW", "I_METAL", "E_GROWTH", "S_FEW",  "L_NONE", "P_LEGAL", 2.0, 35),
    # 겸임·자체검토 = 실행공백 큰 고반응 가설 (핵심 타겟)
    ("R_DONGN", "I_MACH",  "E_EARLY",  "S_NONE", "L_NONE", "P_FRAUD", 4.0, 58),
    ("R_DAEGU", "I_AUTO",  "E_EARLY",  "S_NONE", "L_NONE", "P_LEGAL", 4.0, 56),
    ("R_CHUNG", "I_CHEM",  "E_EARLY",  "S_NONE", "L_NONE", "P_FRAUD", 3.0, 54),
    # 성숙·다변화 = 저반응 가설 (이미 내부 역량 보유 → Fail 후보)
    ("R_DONGN", "I_ELEC",  "E_SCALE",  "S_TEAM", "L_TEAM", "P_LOGIS", 1.5, 20),
    ("R_CHUNG", "I_AUTO",  "E_SCALE",  "S_TEAM", "L_TEAM", "P_FRAUD", 1.5, 22),
    ("R_DAEGU", "I_MACH",  "E_SCALE",  "S_TEAM", "L_EXT",  "P_COMM",  1.5, 25),
    ("R_HONAM", "I_CHEM",  "E_SCALE",  "S_TEAM", "L_TEAM", "P_LEGAL", 1.5, 20),
    # 수도권·서비스업 = 지방 제조 가설로의 오매칭 방지용 전용 셀
    ("R_SEOUL", "I_SERV",  "E_EARLY",  "S_NONE", "L_NONE", "P_LEGAL", 1.0, 30),  # Tops
    ("R_SEOUL", "I_SERV",  "E_GROWTH", "S_FEW",  "L_NONE", "P_COMM",  1.0, 35),  # Global Desk
    # 화장품·바이오 수출 제조사 (다변화 마켓: 중동/러시아/일본) — 국가별 특수성 대응 공백
    # T33) 김포(수도권 외곽) 화장품, 다변화 수출, 중동 준거법·NDA·사기 우려 → Tops
    ("R_SEOUL", "I_BEAUTY", "E_SCALE",  "S_FEW",  "L_NONE", "P_LEGAL_MIDDLE_EAST", 1.0, 40),  # Tops
    # T34) 광주(호남) 화장품, 일본 수출, 복잡한 인증 요건·인력 공백 → Global Desk
    ("R_HONAM", "I_BEAUTY", "E_GROWTH", "S_NONE", "L_NONE", "P_REGULATION_ASIA",  1.0, 45),  # Global Desk
]


def build_hypothesis_matrix() -> pd.DataFrame:
    """T1~T30 가설 매트릭스를 DataFrame으로 반환."""
    rows = []
    for i, (reg, ind, stg, sal, leg, pain, share, meet) in enumerate(_SEED, start=1):
        product = PAIN_TO_PRODUCT[pain]
        persona = f"{REGIONS[reg].split(' ')[0]} {INDUSTRIES[ind]} · {STAGES[stg].split(' ')[0]}"
        rows.append({
            "tid": f"T{i}",
            "persona": persona,
            "region": reg,
            "industry": ind,
            "export_stage": stg,
            "sales_struct": sal,
            "legal_struct": leg,
            "top_pain": pain,
            "product": product,
            "baseline_share_pct": share,       # 기대 응답 비중(%)
            "baseline_meeting_pct": meet,      # 기대 미팅 허락률(%)
        })
    return pd.DataFrame(rows)


HYPOTHESIS_MATRIX = build_hypothesis_matrix()


# ─────────────────────────────────────────────────────────────────────────────
# 3. 룰 기반 실시간 분류 (Rule-based Matching)
# ─────────────────────────────────────────────────────────────────────────────

# 애트리뷰트별 가중치 (합 = 100). 애로사항이 상품 결정에 가장 결정적 → 최고 가중.
MATCH_WEIGHTS = {
    "top_pain": 30,
    "export_stage": 20,
    "sales_struct": 15,
    "legal_struct": 15,
    "industry": 12,
    "region": 8,
}


def match_response(response: dict, matrix: pd.DataFrame = HYPOTHESIS_MATRIX):
    """
    설문 응답 1건을 30개 가설 중 가장 일치율이 높은 셀로 분류한다.

    Parameters
    ----------
    response : dict
        최소 키: region, industry, export_stage, sales_struct, legal_struct, top_pain
    Returns
    -------
    dict : {"tid", "score", "product", "persona", "ranked"[상위 3개]}
    """
    scores = []
    for _, h in matrix.iterrows():
        s = 0.0
        for attr, w in MATCH_WEIGHTS.items():
            if response.get(attr) and response[attr] == h[attr]:
                s += w
        # 애로사항이 정확히 안 맞아도 '같은 상품군'이면 부분 점수 (상품 반응 검증이 목적이므로)
        if response.get("top_pain") and response["top_pain"] != h["top_pain"]:
            if PAIN_TO_PRODUCT.get(response["top_pain"]) == h["product"]:
                s += MATCH_WEIGHTS["top_pain"] * 0.4
        scores.append(s)

    m = matrix.copy()
    m["score"] = scores
    m = m.sort_values("score", ascending=False).reset_index(drop=True)
    best = m.iloc[0]
    return {
        "tid": best["tid"],
        "score": round(float(best["score"]), 1),
        "product": best["product"],
        "persona": best["persona"],
        "ranked": m.head(3)[["tid", "persona", "product", "score"]].to_dict("records"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. 동적 가설 판정 (Dynamic Pivot)
# ─────────────────────────────────────────────────────────────────────────────

# 판정 파라미터 — 데이터가 쌓이면 여기 임계치만 조정하면 됨
MIN_SAMPLE = 3            # 이 미만이면 데이터 부족(판정 보류)
SHARE_TOL = 0.5          # 실제 비중이 기대의 50% 이상이면 "물량은 왔다"
MEETING_TOL = 0.8        # 실제 미팅률이 기대의 80% 이상이면 "반응이 강하다"


def evaluate_hypotheses(responses_df: pd.DataFrame,
                        matrix: pd.DataFrame = HYPOTHESIS_MATRIX) -> pd.DataFrame:
    """
    누적 응답을 기반으로 30개 가설의 상태를 동적 판정한다.

    상태 규칙
    - INSUFFICIENT : 표본 < MIN_SAMPLE                       (판정 보류)
    - VALIDATED    : 표본 충분 + 실제 비중≥기대*SHARE_TOL + 실제 미팅률≥기대*MEETING_TOL
    - PIVOT        : 표본은 왔으나 미팅률이 기대에 못 미침    (메시지/오퍼 수정 필요)
    - FAIL         : 기대는 높았는데 표본이 거의 없음          (페르소나 자체 재검토)
    점수화(0~100) : 비중달성률·미팅달성률의 가중 평균.
    """
    total = len(responses_df)
    out = []
    for _, h in matrix.iterrows():
        subset = responses_df[responses_df["matched_tid"] == h["tid"]] if total else responses_df.iloc[0:0]
        n = len(subset)
        actual_share = (n / total * 100) if total else 0.0
        actual_meeting = (subset["allow_meeting"].mean() * 100) if n else 0.0

        share_ratio = actual_share / h["baseline_share_pct"] if h["baseline_share_pct"] else 0
        meeting_ratio = actual_meeting / h["baseline_meeting_pct"] if h["baseline_meeting_pct"] else 0
        score = round(min(100, (share_ratio * 0.4 + meeting_ratio * 0.6) * 100), 1)

        if n < MIN_SAMPLE:
            # 기대 비중은 높은데 표본이 사실상 0이면 조기 Fail 신호
            expected_n = h["baseline_share_pct"] / 100 * total
            status = "FAIL" if (total >= 20 and expected_n >= 3 and n == 0) else "INSUFFICIENT"
        elif share_ratio >= SHARE_TOL and meeting_ratio >= MEETING_TOL:
            status = "VALIDATED"
        elif share_ratio < 0.25:
            status = "FAIL"
        else:
            status = "PIVOT"

        out.append({
            "tid": h["tid"],
            "persona": h["persona"],
            "product": h["product"],
            "n": n,
            "baseline_share_pct": h["baseline_share_pct"],
            "actual_share_pct": round(actual_share, 1),
            "baseline_meeting_pct": h["baseline_meeting_pct"],
            "actual_meeting_pct": round(actual_meeting, 1),
            "score": score,
            "status": status,
        })
    return pd.DataFrame(out).sort_values(["status", "score"], ascending=[True, False])


# 라벨 역참조 헬퍼 (화면 표기용)
def label(dictionary: dict, code):
    return dictionary.get(code, code)
