import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta
import urllib.parse 
import gc

st.set_page_config(page_title="셀로닉스 데이터 대시보드", layout="wide")

def check_password():
    def password_entered():
        if st.session_state["password"] == "cellonix2026!":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔒 광고주 전용 대시보드입니다. 비밀번호를 입력하세요.", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("❌ 비밀번호가 틀렸습니다. 다시 입력하세요.", type="password", on_change=password_entered, key="password")
        return False
    return True

if not check_password():
    st.stop()

def format_currency(val): return f"₩{val:,.0f}" if pd.notnull(val) else "₩0"
def format_number(val): return f"{val:,.0f}" if pd.notnull(val) else "0"
def calculate_delta(current_val, prev_val):
    if prev_val == 0 or pd.isnull(prev_val): return None
    return f"{((current_val - prev_val) / prev_val) * 100:.1f}%"

# ---------------------------------------------------------
# 데이터 로드
# ---------------------------------------------------------
@st.cache_data(ttl=600, max_entries=1)
def load_data():
    raw_url = st.secrets["gsheet_url"]
    sheet_id = raw_url.split("/d/")[1].split("/")[0]
    
    def get_csv_url(sheet_name):
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(sheet_name)}"
        
    df_total = pd.read_csv(get_csv_url('전체'))
    df_total['날짜'] = pd.to_datetime(df_total['날짜'], errors='coerce') 
    df_total['브랜드'] = '전체'
    
    df_campaign = pd.read_csv(get_csv_url('캠페인'))
    df_campaign['시작일'] = pd.to_datetime(df_campaign['시작일'], errors='coerce')
    df_campaign['종료일'] = pd.to_datetime(df_campaign['종료일'], errors='coerce')
    df_campaign.loc[df_campaign['시작일'] == df_campaign['종료일'], '종료일'] += pd.Timedelta(days=1)
    
    # 정기구독 시트 읽기
    try:
        df_sub = pd.read_csv(get_csv_url('정기구독'))
        if '날짜' not in [str(c).strip() for c in df_sub.columns]:
            mask = df_sub.astype(str).apply(lambda x: x.str.contains('날짜', na=False)).any(axis=1)
            if mask.any():
                header_idx = mask.idxmax()
                df_sub.columns = df_sub.iloc[header_idx].astype(str).str.strip().tolist()
                df_sub = df_sub.iloc[header_idx+1:].reset_index(drop=True)
        else:
            df_sub.columns = [str(c).strip() for c in df_sub.columns]
            
        df_sub['날짜'] = pd.to_datetime(df_sub['날짜'], errors='coerce')
        if '브랜드' not in df_sub.columns: df_sub['브랜드'] = '전체'
        else: df_sub['브랜드'] = df_sub['브랜드'].astype(str).str.strip()
            
        target_col = next((c for c in df_sub.columns if '구독' in str(c) or '할인금액' in str(c) or '금액' in str(c)), None)
        if target_col:
            df_sub['정기구독_매출액'] = pd.to_numeric(df_sub[target_col].astype(str).str.replace(r'[^\d]', '', regex=True), errors='coerce').fillna(0)
        else:
            df_sub['정기구독_매출액'] = 0
    except:
        df_sub = pd.DataFrame({'날짜': pd.to_datetime([]), '브랜드': [], '정기구독_매출액': []})

    df_cellti = pd.read_csv(get_csv_url('셀티아이'))
    df_cellti['날짜'] = pd.to_datetime(df_cellti['날짜'], errors='coerce')
    df_cellti['브랜드'] = '셀티아이'
    
    df_triad = pd.read_csv(get_csv_url('트리어드'))
    df_triad['날짜'] = pd.to_datetime(df_triad['날짜'], errors='coerce')
    df_triad['브랜드'] = '트리어드'
    
    # 인플루언서 매핑
    influencer_dfs = []
    str_cols = df_total.select_dtypes(include=['object']).columns
    is_meta_yt = df_total['매체'].astype(str).str.upper().isin(['META', '유튜브'])
    inf_keywords = {
        '문지애': r'(?i)문지애|jiae|지애', '김미경': r'(?i)김미경|mikyung|mkyu|미경',
        '채정안': r'(?i)채정안|jungan|정안', '이재성': r'(?i)이재성|jaesung',
        '한고은': r'(?i)한고은|고은|goeun', '강주은': r'(?i)강주은|jueun|주은|깡주은'
    }
    
    for idx, row in df_campaign[df_campaign['구분'] == '인플루언서'].iterrows():
        inf_name = str(row['내용']).strip()
        if inf_name in inf_keywords:
            try:
                start_date, end_date = pd.to_datetime(row['시작일']), pd.to_datetime(row['종료일']) + pd.Timedelta(days=14)
                is_valid_date = (df_total['날짜'] >= start_date) & (df_total['날짜'] <= end_date)
            except:
                is_valid_date = True 
            has_keyword = df_total[str_cols].apply(lambda x: x.astype(str).str.contains(inf_keywords[inf_name])).any(axis=1)
            df_inf = df_total[is_meta_yt & is_valid_date & has_keyword].copy()
            if not df_inf.empty:
                df_inf['인플루언서명'] = inf_name
                df_inf['브랜드'] = '셀티아이 인플루언서' if inf_name == '문지애' else '트리어드 인플루언서'
                influencer_dfs.append(df_inf)
    
    df_main = pd.concat([df_total, df_cellti, df_triad] + influencer_dfs, ignore_index=True)
    gc.collect()
    
    df_main['총매출액'] = (df_main['신규방문_신규구매_매출액'].fillna(0) + df_main['신규방문_재구매_매출액'].fillna(0) + df_main['재방문_신규구매_매출액'].fillna(0) + df_main['재방문_재구매_매출액'].fillna(0))
    df_main['총방문수'] = df_main['신규방문_총 방문수'].fillna(0) + df_main['재방문_총 방문수'].fillna(0)
    df_main['총회원가입'] = df_main['신규방문_회원가입'].fillna(0) + df_main['재방문_회원가입'].fillna(0)
    df_main['총구매수'] = (df_main['신규방문_신규구매_건수'].fillna(0) + df_main['신규방문_재구매_건수'].fillna(0) + df_main['재방문_신규구매_건수'].fillna(0) + df_main['재방문_재구매_건수'].fillna(0))
    
    return df_main, df_campaign, df_sub

df_all, df_camp_all, df_sub_all = load_data()

# ---------------------------------------------------------
# 사이드바 필터
# ---------------------------------------------------------
st.sidebar.header("📊 필터")
brand_options = ["전체", "셀티아이", "셀티아이 인플루언서", "트리어드", "트리어드 인플루언서"]
selected_brands = st.sidebar.multiselect("📌 브랜드 선택", brand_options, default=["전체"])

if not selected_brands:
    st.warning("👈 브랜드를 선택해 주세요.")
    st.stop()

df_filtered = df_all[df_all['브랜드'].isin(selected_brands)].copy()

sub_target_brands = set()
if "전체" in selected_brands: sub_target_brands.update(["전체", "셀티아이", "트리어드"])
else:
    for b in selected_brands:
        if "셀티아이" in b: sub_target_brands.add("셀티아이")
        if "트리어드" in b: sub_target_brands.add("트리어드")

df_sub_filtered = df_sub_all[df_sub_all['브랜드'].isin(sub_target_brands)].copy() if sub_target_brands else df_sub_all.copy()

if any("인플루언서" in b for b in selected_brands):
    inf_list = df_filtered.get('인플루언서명', pd.Series()).dropna().unique().tolist()
    if inf_list:
        selected_infs = st.sidebar.multiselect("👤 인플루언서 온/오프", inf_list, default=inf_list)
        df_filtered = df_filtered[df_filtered['인플루언서명'].isna() | df_filtered['인플루언서명'].isin(selected_infs)]

min_date, max_date = df_all['날짜'].min().date(), df_all['날짜'].max().date()
date_range = st.sidebar.date_input("🗓️ 조회 기간", value=(max_date.replace(day=1), max_date), min_value=min_date, max_value=max_date)

start_date, end_date = date_range if len(date_range) == 2 else (max_date.replace(day=1), max_date)

media_options = ["전체"] + list(df_all['매체'].dropna().unique())
selected_media = st.sidebar.multiselect("📺 매체 선택", media_options, default=["전체"])
if "전체" not in selected_media:
    df_filtered = df_filtered[df_filtered['매체'].isin(selected_media)]

df_current = df_filtered[(df_filtered['날짜'].dt.date >= start_date) & (df_filtered['날짜'].dt.date <= end_date)]
df_sub_current = df_sub_filtered[(df_sub_filtered['날짜'].dt.date >= start_date) & (df_sub_filtered['날짜'].dt.date <= end_date)]

duration = (end_date - start_date).days + 1
prev_start_date = start_date - timedelta(days=duration)
prev_end_date = start_date - timedelta(days=1)
df_prev = df_filtered[(df_filtered['날짜'].dt.date >= prev_start_date) & (df_filtered['날짜'].dt.date <= prev_end_date)]
df_sub_prev = df_sub_filtered[(df_sub_filtered['날짜'].dt.date >= prev_start_date) & (df_sub_filtered['날짜'].dt.date <= prev_end_date)]

st.title(f"📈 공식몰 성과 대시보드 ({' + '.join(selected_brands) if len(selected_brands) <= 2 else '종합'})")

# ---------------------------------------------------------
# 상단 KPI
# ---------------------------------------------------------
st.caption(f"※ 비교 기간: 직전 동일 기간 ({prev_start_date} ~ {prev_end_date}) 대비")

col_kpi1, col_kpi2 = st.columns(2)
with col_kpi1:
    st.markdown("#### 👥 유입 지표")
    k1, k2, k3 = st.columns(3)
    k1.metric("총 방문수", format_number(df_current['총방문수'].sum()), delta=calculate_delta(df_current['총방문수'].sum(), df_prev['총방문수'].sum()))
    k2.metric("신규 방문수", format_number(df_current['신규방문_총 방문수'].sum()), delta=calculate_delta(df_current['신규방문_총 방문수'].sum(), df_prev['신규방문_총 방문수'].sum()))
    k3.metric("재방문수", format_number(df_current['재방문_총 방문수'].sum()), delta=calculate_delta(df_current['재방문_총 방문수'].sum(), df_prev['재방문_총 방문수'].sum()))

with col_kpi2:
    st.markdown("#### 🛒 구매 건수 지표")
    k4, k5, k6 = st.columns(3)
    k4.metric("총 구매", format_number(df_current['총구매수'].sum()), delta=calculate_delta(df_current['총구매수'].sum(), df_prev['총구매수'].sum()))
    k5.metric("신규 구매", format_number(df_current['신규방문_신규구매_건수'].sum() + df_current['신규방문_재구매_건수'].sum()), delta=calculate_delta(df_current['신규방문_신규구매_건수'].sum() + df_current['신규방문_재구매_건수'].sum(), df_prev['신규방문_신규구매_건수'].sum() + df_prev['신규방문_재구매_건수'].sum()))
    k6.metric("재방문 구매", format_number(df_current['재방문_신규구매_건수'].sum() + df_current['재방문_재구매_건수'].sum()), delta=calculate_delta(df_current['재방문_신규구매_건수'].sum() + df_current['재방문_재구매_건수'].sum(), df_prev['재방문_신규구매_건수'].sum() + df_prev['재방문_재구매_건수'].sum()))

st.markdown("---")

cur_new_rev = df_current['신규방문_신규구매_매출액'].sum() + df_current['신규방문_재구매_매출액'].sum()
cur_ret_rev = df_current['재방문_신규구매_매출액'].sum() + df_current['재방문_재구매_매출액'].sum()
cur_sub_rev = df_sub_current['정기구독_매출액'].sum()
cur_grand_total = cur_new_rev + cur_ret_rev + cur_sub_rev

prev_new_rev = df_prev['신규방문_신규구매_매출액'].sum() + df_prev['신규방문_재구매_매출액'].sum()
prev_ret_rev = df_prev['재방문_신규구매_매출액'].sum() + df_prev['재방문_재구매_매출액'].sum()
prev_sub_rev = df_sub_prev['정기구독_매출액'].sum()
prev_grand_total = prev_new_rev + prev_ret_rev + prev_sub_rev

st.markdown("#### 💰 핵심 매출액 분석 (정기구독 포함)")
m1, m2, m3, m4 = st.columns(4)
m1.metric("🔥 총 매출", format_currency(cur_grand_total), delta=calculate_delta(cur_grand_total, prev_grand_total))
m2.metric("✨ 신규 매출", format_currency(cur_new_rev), delta=calculate_delta(cur_new_rev, prev_new_rev))
m3.metric("🤝 재구매 매출", format_currency(cur_ret_rev), delta=calculate_delta(cur_ret_rev, prev_ret_rev))
m4.metric("🔄 정기구독 매출", format_currency(cur_sub_rev), delta=calculate_delta(cur_sub_rev, prev_sub_rev))

st.markdown("---")
