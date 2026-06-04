"""
동물생산업 · 동물판매업 · 유기유실동물 통합 대시보드
- 데이터 출처: 공공데이터포털(data.go.kr)
- 실행: streamlit run app.py
"""
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime

# ──────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────
st.set_page_config(page_title="동물 영업·구조 통합 대시보드", page_icon="🐾",
                   layout="wide", initial_sidebar_state="expanded")

# 브랜드 컬러 (동물자유연대)
C1, C2, C3 = "#F37021", "#03428E", "#00ABB0"
PLOTLY_COLORS = [C2, C1, C3, "#7F77DD", "#639922"]

st.markdown(f"""
<style>
    div[data-testid="stMetric"] {{
        background:#FFFFFF; border:1px solid #ECECEC; border-radius:12px;
        padding:16px 18px;
    }}
    div[data-testid="stMetricValue"] {{ color:{C2}; font-weight:700; }}
    h1,h2,h3 {{ color:{C2}; }}
    .stTabs [data-baseweb="tab-list"] {{ gap:4px; }}
    .stTabs [data-baseweb="tab"] {{ font-weight:500; padding:8px 18px; border-radius:8px 8px 0 0; }}
    .stTabs [aria-selected="true"] {{ background:{C2}; color:#FFFFFF; }}
    .src-note {{ font-size:12px; color:#888; margin-top:-6px; }}
</style>
""", unsafe_allow_html=True)


def get_api_key():
    """secrets에 키가 있으면 사용, 없으면 None"""
    try:
        return st.secrets["PUBLIC_DATA_API_KEY"]
    except Exception:
        return None


# ──────────────────────────────────────────
# API 호출 함수
# ──────────────────────────────────────────

@st.cache_data(ttl=86400)
def fetch_business(api_key: str, kind: str, num_rows: int = 1000) -> pd.DataFrame:
    """
    동물생산업 / 동물판매업 조회 (행정안전부 조회서비스 오픈API)
    kind: 'production'(생산업) | 'sales'(판매업)
    구조: End Point 뒤에 세부기능명을 붙여 호출. 응답은 JSON.
    """
    # End Point (data.go.kr 상세화면 기준, 세부기능명 중복 없이)
    services = {
        "production": "https://apis.data.go.kr/1741000/animal_breeding",
        "sales":      "https://apis.data.go.kr/1741000/animal_sales",
    }
    url = services.get(kind)
    params = {
        "serviceKey": api_key,
        "pageNo": 1,
        "numOfRows": num_rows,
        "type": "json",
    }
    label = "생산업" if kind == "production" else "판매업"
    try:
        res = requests.get(url, params=params, timeout=15)
        # 오류여도 응답 본문에 원인이 담겨 있으므로 먼저 확인
        if res.status_code != 200:
            st.warning(f"{label} 응답 코드 {res.status_code}. 서버 메시지: {res.text[:300]}")
            return pd.DataFrame()
        try:
            data = res.json()
        except ValueError:
            st.warning(f"{label}: JSON이 아닌 응답. 응답 일부: {res.text[:300]}")
            return pd.DataFrame()
        # 응답 구조 자동 탐색 (기관마다 body/items 위치가 조금씩 다름)
        body = data.get("response", {}).get("body", data.get("body", data))
        items = (body.get("items", {}) if isinstance(body, dict) else {})
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        if not items and isinstance(body, dict):
            items = body.get("item", [])
        return pd.DataFrame(items) if items else pd.DataFrame()
    except Exception as e:
        st.warning(f"{label} 데이터 조회 실패: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def fetch_rescued(api_key: str, sido_cd: str = "", begin: str = "", end: str = "",
                  num_rows: int = 500) -> pd.DataFrame:
    """유기·유실동물(구조동물) 조회 - 농림축산검역본부 (표준 엔드포인트)"""
    url = "https://apis.data.go.kr/1543061/abandonmentPublicService_v2/abandonmentPublic_v2"
    params = {"serviceKey": api_key, "numOfRows": num_rows, "pageNo": 1, "_type": "json"}
    # state(공고상태)는 생략 — 일부 조합에서 500을 유발. 기간/지역만으로 조회
    if sido_cd:
        params["upr_cd"] = sido_cd
    if begin:
        params["bgnde"] = begin
    if end:
        params["endde"] = end
    try:
        res = requests.get(url, params=params, timeout=15)
        res.raise_for_status()
        try:
            data = res.json()
        except ValueError:
            st.warning(f"유기·유실동물: JSON이 아닌 응답. 응답 일부: {res.text[:200]}")
            return pd.DataFrame()
        items = data.get("response", {}).get("body", {}).get("items", {})
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        return pd.DataFrame(items) if items else pd.DataFrame()
    except Exception as e:
        st.warning(f"유기·유실동물 데이터 조회 실패: {e}")
        return pd.DataFrame()


def extract_sido(df: pd.DataFrame, addr_cols=("소재지전체주소", "도로명전체주소", "사업장소재지")) -> pd.Series:
    """주소 컬럼에서 시도명 추출"""
    for col in addr_cols:
        if col in df.columns:
            return df[col].fillna("").astype(str).str.split().str[0]
    return pd.Series(["미상"] * len(df))


# ──────────────────────────────────────────
# 사이드바
# ──────────────────────────────────────────
SIDO_MAP = {
    "전체": "", "서울특별시": "6110000", "부산광역시": "6260000", "대구광역시": "6270000",
    "인천광역시": "6280000", "광주광역시": "6290000", "대전광역시": "6300000",
    "울산광역시": "6310000", "세종특별자치시": "5690000", "경기도": "6410000",
    "강원도": "6530000", "충청북도": "6430000", "충청남도": "6440000",
    "전라북도": "6540000", "전라남도": "6460000", "경상북도": "6470000",
    "경상남도": "6480000", "제주특별자치도": "6500000",
}

with st.sidebar:
    st.markdown("## ⚙️ 설정")
    api_key_input = st.text_input("공공데이터 API 인증키", value=get_api_key() or "",
                                  type="password",
                                  help="data.go.kr에서 발급받은 인증키를 붙여넣으세요")
    API_KEY = api_key_input or get_api_key()

    st.markdown("---")
    st.markdown("### 📍 공통 지역 필터")
    sel_sido = st.selectbox("시도", list(SIDO_MAP.keys()))
    sido_cd = SIDO_MAP[sel_sido]

    st.markdown("### 📅 구조동물 조회 기간")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        d_begin = st.date_input("시작", value=datetime(2025, 1, 1))
    with col_d2:
        d_end = st.date_input("종료", value=datetime.now())

    st.markdown("---")
    st.caption(f"기준: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    st.caption("출처: 공공데이터포털(data.go.kr)")

# ──────────────────────────────────────────
# 헤더 + KPI
# ──────────────────────────────────────────
st.markdown("# 🐾 동물 영업·구조 통합 대시보드")
st.markdown(f"**{sel_sido}** 기준 · 동물생산업 · 동물판매업 · 유기·유실동물 통합 현황")

if not API_KEY:
    st.warning("⚠️ 사이드바에서 공공데이터 API 인증키를 입력해주세요.")
    st.stop()

with st.spinner("데이터 불러오는 중..."):
    df_prod = fetch_business(API_KEY, "production")
    df_sale = fetch_business(API_KEY, "sales")
    df_resc = fetch_rescued(API_KEY, sido_cd,
                            d_begin.strftime("%Y%m%d"), d_end.strftime("%Y%m%d"))

if sel_sido != "전체":
    if not df_prod.empty:
        df_prod = df_prod[extract_sido(df_prod).str.contains(sel_sido[:2], na=False)]
    if not df_sale.empty:
        df_sale = df_sale[extract_sido(df_sale).str.contains(sel_sido[:2], na=False)]

k1, k2, k3, k4 = st.columns(4)
k1.metric("동물생산업체", f"{len(df_prod):,} 곳")
k2.metric("동물판매업체", f"{len(df_sale):,} 곳")
k3.metric("유기·유실동물", f"{len(df_resc):,} 건")
k4.metric("총 영업장", f"{len(df_prod) + len(df_sale):,} 곳")

st.markdown("---")

# ──────────────────────────────────────────
# 탭
# ──────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🏭 동물생산업", "🏪 동물판매업", "🐶 유기·유실동물"])


def render_business_tab(df: pd.DataFrame, label: str):
    if df.empty:
        st.info(f"{label} 데이터가 없습니다. API 신청 상태와 엔드포인트(uddi)를 확인해주세요.")
        return
    df = df.copy()
    df["시도"] = extract_sido(df)

    col_a, col_b = st.columns([3, 2])
    with col_a:
        st.markdown(f'<div class="src-note">지역별 {label} 분포</div>', unsafe_allow_html=True)
        region = df["시도"].value_counts().reset_index()
        region.columns = ["지역", "업체수"]
        region = region[region["지역"] != ""].head(17).sort_values("업체수")
        fig = px.bar(region, x="업체수", y="지역", orientation="h",
                     template="plotly_white", color_discrete_sequence=[C2])
        fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0),
                          yaxis_title="", xaxis_title="업체 수")
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        status_col = next((c for c in ["영업상태명", "영업상태구분명", "상세영업상태명"] if c in df.columns), None)
        if status_col:
            st.markdown('<div class="src-note">영업상태 분포</div>', unsafe_allow_html=True)
            status = df[status_col].value_counts().reset_index()
            status.columns = ["상태", "수"]
            fig2 = px.pie(status, names="상태", values="수", hole=0.45,
                          template="plotly_white", color_discrete_sequence=PLOTLY_COLORS)
            fig2.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown(f'<div class="src-note">{label} 목록 ({len(df):,}건)</div>', unsafe_allow_html=True)
    name_cols = [c for c in ["사업장명", "영업상태명", "인허가일자", "소재지전화",
                             "소재지전체주소", "도로명전체주소", "총인원"] if c in df.columns]
    st.dataframe(df[name_cols] if name_cols else df, use_container_width=True, height=360)


with tab1:
    render_business_tab(df_prod, "동물생산업")

with tab2:
    render_business_tab(df_sale, "동물판매업")

with tab3:
    if df_resc.empty:
        st.info("유기·유실동물 데이터가 없습니다. 조회 기간과 API 신청 상태를 확인해주세요.")
    else:
        df_r = df_resc.copy()
        c1, c2, c3 = st.columns(3)
        c1.metric("총 공고", f"{len(df_r):,} 건")
        if "kindCd" in df_r.columns:
            c2.metric("개", f"{df_r['kindCd'].str.contains('개', na=False).sum():,} 건")
            c3.metric("고양이", f"{df_r['kindCd'].str.contains('고양이', na=False).sum():,} 건")

        col_x, col_y = st.columns(2)
        with col_x:
            if "kindCd" in df_r.columns:
                st.markdown('<div class="src-note">축종별 구조 현황</div>', unsafe_allow_html=True)
                kind = df_r["kindCd"].str.extract(r'\[(.+?)\]', expand=False).fillna(df_r["kindCd"])
                kc = kind.value_counts().head(8).reset_index()
                kc.columns = ["축종", "건수"]
                figk = px.bar(kc, x="축종", y="건수", template="plotly_white",
                              color_discrete_sequence=[C3])
                figk.update_layout(height=330, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(figk, use_container_width=True)
        with col_y:
            if "processState" in df_r.columns:
                st.markdown('<div class="src-note">처리 상태</div>', unsafe_allow_html=True)
                ps = df_r["processState"].value_counts().reset_index()
                ps.columns = ["상태", "건수"]
                figp = px.pie(ps, names="상태", values="건수", hole=0.45,
                              template="plotly_white", color_discrete_sequence=PLOTLY_COLORS)
                figp.update_layout(height=330, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(figp, use_container_width=True)

        st.markdown(f'<div class="src-note">유기·유실동물 공고 목록 ({len(df_r):,}건)</div>', unsafe_allow_html=True)
        cmap = {"happenDt": "발생일", "happenPlace": "발생장소", "kindCd": "축종",
                "sexCd": "성별", "age": "나이", "weight": "체중",
                "processState": "상태", "careNm": "보호소", "careTel": "연락처"}
        dr = df_r.rename(columns={k: v for k, v in cmap.items() if k in df_r.columns})
        show = [v for v in cmap.values() if v in dr.columns]
        st.dataframe(dr[show] if show else dr, use_container_width=True, height=360)
