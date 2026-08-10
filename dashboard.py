import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta
import urllib.parse 

# ---------------------------------------------------------
# 1. 페이지 및 기본 설정
# ---------------------------------------------------------
st.set_page_config(page_title="셀로닉스 데이터 대시보드", layout="wide")

# =========================================================
# 🔒 보안: 대시보드 자체 비밀번호 설정
# =========================================================
def check_password():
    def password_entered():
        if st.session_state["password"] == "cellonix2026!":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔒 광비밀번호를 입력하세요.", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("❌ 비밀번호가 틀렸습니다. 다시 입력하세요.", type="password", on_change=password_entered, key="password")
        return False
    return True

if not check_password():
    st.stop()
# =========================================================

# ---------------------------------------------------------
# 2. UI CSS 설정
# ---------------------------------------------------------
st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"], [class*="st-"] { font-family: 'Pretendard', 'Noto Sans KR', sans-serif !important; }
    .block-container { padding-top: 2.5rem !important; padding-bottom: 2rem !important; }
    [data-testid="stMetricValue"] { font-size: 1.25rem !important; font-weight: 700 !important; color: #2c3e50; }
    [data-testid="stMetricLabel"] { font-size: 0.9rem !important; color: #7f8c8d; margin-bottom: -5px !important; }
    [data-testid="stMetricDelta"] { font-size: 0.75rem !important; }
    h2, h3, h4 { padding-bottom: 0rem !important; margin-bottom: 0.5rem !important; margin-top: 0.5rem !important; }
    hr { margin-top: 0.8rem !important; margin-bottom: 0.8rem !important; border-color: #f0f2f6; }
    </style>
""", unsafe_allow_html=True)

def format_currency(val): return f"₩{val:,.0f}" if pd.notnull(val) else "₩0"
def format_number(val): return f"{val:,.0f}" if pd.notnull(val) else "0"
def calculate_delta(current_val, prev_val):
    if prev_val == 0 or pd.isnull(prev_val): return None
    return f"{((current_val - prev_val) / prev_val) * 100:.1f}%"

# ---------------------------------------------------------
# 3. 데이터 로드 및 전처리 (구글 스프레드시트 연동)
# ---------------------------------------------------------
@st.cache_data(ttl=600)
def load_data():
    raw_url = st.secrets["gsheet_url"]
    sheet_id = raw_url.split("/d/")[1].split("/")[0]
    
    def get_csv_url(sheet_name):
        encoded_name = urllib.parse.quote(sheet_name)
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={encoded_name}"
    
    # [1] 전체 데이터
    df_total = pd.read_csv(get_csv_url('전체'))
    df_total['날짜'] = pd.to_datetime(df_total['날짜'], errors='coerce') 
    df_total['브랜드'] = '전체'
    df_total['인플루언서명'] = None
    
    # 캠페인 데이터
    df_campaign = pd.read_csv(get_csv_url('캠페인'))
    df_campaign['시작일'] = pd.to_datetime(df_campaign['시작일'], errors='coerce')
    df_campaign['종료일'] = pd.to_datetime(df_campaign['종료일'], errors='coerce')
    mask_same_day = df_campaign['시작일'] == df_campaign['종료일']
    df_campaign.loc[mask_same_day, '종료일'] = df_campaign.loc[mask_same_day, '종료일'] + pd.Timedelta(days=1)
    
    # [NEW] 정기구독 데이터 로드 (금액 콤마 제거 등 에러 방어)
    try:
        df_sub = pd.read_csv(get_csv_url('정기구독'))
        df_sub['날짜'] = pd.to_datetime(df_sub['날짜'], errors='coerce')
        if '브랜드' not in df_sub.columns:
            df_sub['브랜드'] = '전체'
        
        # '구독'이라는 단어가 들어간 열을 자동으로 찾아 금액 변환
        sub_col = [c for c in df_sub.columns if '구독' in c]
        if sub_col:
            # 금액에 포함된 콤마(,) 제거 후 숫자로 변환
            df_sub['정기구독_매출액'] = df_sub[sub_col[-1]].astype(str).replace(',', '', regex=True)
            df_sub['정기구독_매출액'] = pd.to_numeric(df_sub['정기구독_매출액'], errors='coerce').fillna(0)
        else:
            df_sub['정기구독_매출액'] = 0
            
    except Exception as e:
        df_sub = pd.DataFrame({'날짜': pd.to_datetime([]), '브랜드': [], '정기구독_매출액': []})

    # [2] 셀티아이
    df_cellti = pd.read_csv(get_csv_url('셀티아이'))
    df_cellti['날짜'] = pd.to_datetime(df_cellti['날짜'], errors='coerce')
    df_cellti['브랜드'] = '셀티아이'
    df_cellti['인플루언서명'] = None
    
    # [4] 트리어드
    df_triad = pd.read_csv(get_csv_url('트리어드'))
    df_triad['날짜'] = pd.to_datetime(df_triad['날짜'], errors='coerce')
    df_triad['브랜드'] = '트리어드'
    df_triad['인플루언서명'] = None
    
    # [3 & 5] 인플루언서 데이터
    influencer_dfs = []
    str_cols = df_total.select_dtypes(include=['object']).columns
    is_meta_yt = df_total['매체'].astype(str).str.upper().isin(['META', '유튜브'])
    
    inf_keywords = {
        '문지애': r'(?i)문지애|jiae|지애',
        '김미경': r'(?i)김미경|mikyung|mkyu|미경',
        '채정안': r'(?i)채정안|jungan|정안',
        '이재성': r'(?i)이재성|jaesung',
        '한고은': r'(?i)한고은|고은|goeun',
        '강주은': r'(?i)강주은|jueun|주은|깡주은'
    }
    
    df_inf_campaigns = df_campaign[df_campaign['구분'] == '인플루언서']
    for idx, row in df_inf_campaigns.iterrows():
        inf_name = str(row['내용']).strip()
        if inf_name in inf_keywords:
            pattern = inf_keywords[inf_name]
            try:
                start_date = pd.to_datetime(row['시작일'])
                end_date = pd.to_datetime(row['종료일']) + pd.Timedelta(days=14)
                is_valid_date = (df_total['날짜'] >= start_date) & (df_total['날짜'] <= end_date)
            except:
                is_valid_date = True 
                
            has_keyword = df_total[str_cols].apply(lambda x: x.astype(str).str.contains(pattern)).any(axis=1)
            df_inf = df_total[is_meta_yt & is_valid_date & has_keyword].copy()
            
            if not df_inf.empty:
                df_inf['인플루언서명'] = inf_name
                if inf_name == '문지애': df_inf['브랜드'] = '셀티아이 인플루언서' 
                else: df_inf['브랜드'] = '트리어드 인플루언서' 
                influencer_dfs.append(df_inf)
    
    df_main = pd.concat([df_total, df_cellti, df_triad] + influencer_dfs, ignore_index=True)
    
    df_main['총매출액'] = (
        df_main['신규방문_신규구매_매출액'].fillna(0) + df_main['신규방문_재구매_매출액'].fillna(0) + 
        df_main['재방문_신규구매_매출액'].fillna(0) + df_main['재방문_재구매_매출액'].fillna(0)
    )
    df_main['총방문수'] = df_main['신규방문_총 방문수'].fillna(0) + df_main['재방문_총 방문수'].fillna(0)
    df_main['총회원가입'] = df_main['신규방문_회원가입'].fillna(0) + df_main['재방문_회원가입'].fillna(0)
    df_main['총구매수'] = (
        df_main['신규방문_신규구매_건수'].fillna(0) + df_main['신규방문_재구매_건수'].fillna(0) +
        df_main['재방문_신규구매_건수'].fillna(0) + df_main['재방문_재구매_건수'].fillna(0)
    )
    
    return df_main, df_campaign, df_sub

df_all, df_camp_all, df_sub_all = load_data()

# ---------------------------------------------------------
# 4. 사이드바 (필터) 및 대시보드 렌더링
# ---------------------------------------------------------
st.sidebar.header("📊 필터")
brand_options = ["전체", "셀티아이", "셀티아이 인플루언서", "트리어드", "트리어드 인플루언서"]
selected_brands = st.sidebar.multiselect("📌 브랜드 선택 (다중 선택 가능)", brand_options, default=["전체"])

if not selected_brands:
    st.warning("👈 왼쪽 사이드바에서 분석할 브랜드를 하나 이상 선택해 주세요.")
    st.stop()

# 1차 필터링
df_filtered = df_all[df_all['브랜드'].isin(selected_brands)].copy()

# 정기구독 데이터 필터링용 타겟 브랜드 산출
sub_target_brands = set()
if "전체" in selected_brands: sub_target_brands.update(["전체", "셀티아이", "트리어드"])
else:
    for b in selected_brands:
        if "셀티아이" in b: sub_target_brands.add("셀티아이")
        if "트리어드" in b: sub_target_brands.add("트리어드")
        if "전체" in b: sub_target_brands.add("전체")

df_sub_filtered = df_sub_all[df_sub_all['브랜드'].isin(sub_target_brands)].copy() if sub_target_brands else df_sub_all.copy()

# 2차 필터링: 인플루언서 추가/제거
if any("인플루언서" in b for b in selected_brands):
    inf_list = df_filtered['인플루언서명'].dropna().unique().tolist()
    if inf_list:
        st.sidebar.markdown("---")
        selected_infs = st.sidebar.multiselect("👤 인플루언서 온/오프", inf_list, default=inf_list)
        mask_normal = df_filtered['인플루언서명'].isna()
        mask_selected_inf = df_filtered['인플루언서명'].isin(selected_infs)
        df_filtered = df_filtered[mask_normal | mask_selected_inf]
        st.sidebar.markdown("---")

# 3차 필터링: 날짜
min_date = df_all['날짜'].min().date()
max_date = df_all['날짜'].max().date()
default_start_date = max_date.replace(day=1) 
date_range = st.sidebar.date_input("🗓️ 조회 기간", value=(default_start_date, max_date), min_value=min_date, max_value=max_date)

if len(date_range) == 2: start_date, end_date = date_range
else: start_date, end_date = default_start_date, max_date 

# 4차 필터링: 매체
media_options = ["전체"] + list(df_all['매체'].dropna().unique())
selected_media = st.sidebar.multiselect("📺 매체 선택", media_options, default=["전체"])

if "전체" not in selected_media:
    df_filtered = df_filtered[df_filtered['매체'].isin(selected_media)]

# 메인 및 구독 데이터 날짜 분리
df_current = df_filtered[(df_filtered['날짜'].dt.date >= start_date) & (df_filtered['날짜'].dt.date <= end_date)]
df_sub_current = df_sub_filtered[(df_sub_filtered['날짜'].dt.date >= start_date) & (df_sub_filtered['날짜'].dt.date <= end_date)]

duration = (end_date - start_date).days + 1
prev_end_date = start_date - timedelta(days=1)
prev_start_date = prev_end_date - timedelta(days=duration - 1)
df_prev = df_filtered[(df_filtered['날짜'].dt.date >= prev_start_date) & (df_filtered['날짜'].dt.date <= prev_end_date)]
df_sub_prev = df_sub_filtered[(df_sub_filtered['날짜'].dt.date >= prev_start_date) & (df_sub_filtered['날짜'].dt.date <= prev_end_date)]

display_title = " + ".join(selected_brands) if len(selected_brands) <= 2 else "종합"
st.title(f"📈 공식몰 성과 대시보드 ({display_title})")

# =========================================================
# [순서 1] 깔끔하게 정리된 2단 KPI 요약
# =========================================================
st.caption(f"※ 비교 기준: 선택한 기간({duration}일)과 동일한 직전 기간({prev_start_date} ~ {prev_end_date}) 대비")

# --- 유입 및 구매 건수 데이터 ---
cur_total_visit = df_current['총방문수'].sum()
cur_new_visit = df_current['신규방문_총 방문수'].sum()
cur_ret_visit = df_current['재방문_총 방문수'].sum()
cur_total_buy = df_current['총구매수'].sum()
cur_new_buy = df_current['신규방
