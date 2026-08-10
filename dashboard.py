import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta
import urllib.parse 
import gc

# ---------------------------------------------------------
# 1. 페이지 및 기본 설정
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# 2. UI CSS 설정
# ---------------------------------------------------------
st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"], [class*="st-"] { font-family: 'Pretendard', 'Noto Sans KR', sans-serif !important; }
    .block-container { padding-top: 2.5rem !important; padding-bottom: 2rem !important; }
    [data-testid="stMetricValue"] { font-size: 1.3rem !important; font-weight: 700 !important; color: #2c3e50; }
    [data-testid="stMetricLabel"] { font-size: 0.9rem !important; color: #7f8c8d; margin-bottom: -5px !important; font-weight: 600; }
    [data-testid="stMetricDelta"] { font-size: 0.8rem !important; }
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
# 3. 데이터 로드 및 전처리 (🌟 극한의 메모리 최적화 적용)
# ---------------------------------------------------------
# max_entries=1 옵션으로 이전 데이터 캐시를 쌓아두지 않고 삭제하여 RAM 터짐 방지
@st.cache_data(ttl=600, max_entries=1)
def load_data():
    raw_url = st.secrets["gsheet_url"]
    sheet_id = raw_url.split("/d/")[1].split("/")[0]
    
    def get_csv_url(sheet_name):
        encoded_name = urllib.parse.quote(sheet_name)
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={encoded_name}"
        
    # 데이터 용량을 획기적으로 줄이는 압축 함수
    def optimize_memory(df):
        for col in df.select_dtypes(include=['float64', 'int64']).columns:
            df[col] = pd.to_numeric(df[col], downcast='float')
        return df
    
    # [1] 전체 데이터 읽기 및 압축
    df_total = pd.read_csv(get_csv_url('전체'))
    df_total = optimize_memory(df_total)
    df_total['날짜'] = pd.to_datetime(df_total['날짜'], errors='coerce') 
    df_total['브랜드'] = '전체'
    df_total['인플루언서명'] = None
    
    # [2] 캠페인 데이터
    df_campaign = pd.read_csv(get_csv_url('캠페인'))
    df_campaign['시작일'] = pd.to_datetime(df_campaign['시작일'], errors='coerce')
    df_campaign['종료일'] = pd.to_datetime(df_campaign['종료일'], errors='coerce')
    mask_same_day = df_campaign['시작일'] == df_campaign['종료일']
    df_campaign.loc[mask_same_day, '종료일'] = df_campaign.loc[mask_same_day, '종료일'] + pd.Timedelta(days=1)
    
    # [3] 정기구독 데이터 (안전 로직)
    try:
        df_sub = pd.read_csv(get_csv_url('정기구독'))
        if '날짜' not in df_sub.columns:
            mask = df_sub.astype(str).apply(lambda x: x.str.contains('날짜')).any(axis=1)
            if mask.any():
                header_idx = mask.idxmax()
                df_sub.columns = df_sub.iloc[header_idx]
                df_sub = df_sub.iloc[header_idx+1:].reset_index(drop=True)
                
        df_sub['날짜'] = pd.to_datetime(df_sub['날짜'], errors='coerce')
        if '브랜드' not in df_sub.columns: df_sub['브랜드'] = '전체'
        
        sub_col = [c for c in df_sub.columns if pd.notnull(c) and '구독' in str(c)]
        if sub_col:
            df_sub['정기구독_매출액'] = df_sub[sub_col[-1]].astype(str).replace(',', '', regex=True)
            df_sub['정기구독_매출액'] = pd.to_numeric(df_sub['정기구독_매출액'], errors='coerce').fillna(0)
        else:
            df_sub['정기구독_매출액'] = 0
            
    except Exception as e:
        df_sub = pd.DataFrame({'날짜': pd.to_datetime([]), '브랜드': [], '정기구독_매출액': []})

    # [4] 셀티아이 & 트리어드 읽기 및 압축
    df_cellti = pd.read_csv(get_csv_url('셀티아이'))
    df_cellti = optimize_memory(df_cellti)
    df_cellti['날짜'] = pd.to_datetime(df_cellti['날짜'], errors='coerce')
    df_cellti['브랜드'] = '셀티아이'
    df_cellti['인플루언서명'] = None
    
    df_triad = pd.read_csv(get_csv_url('트리어드'))
    df_triad = optimize_memory(df_triad)
    df_triad['날짜'] = pd.to_datetime(df_triad['날짜'], errors='coerce')
    df_triad['브랜드'] = '트리어드'
    df_triad['인플루언서명'] = None
    
    # [5] 인플루언서 데이터 (전체 시트에서 추출)
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
    
    # [6] 메인 데이터 병합
    df_main = pd.concat([df_total, df_cellti, df_triad] + influencer_dfs, ignore_index=True)
    
    # 🌟 병합 후 불필요한 개별 데이터는 즉시 삭제하여 메모리 반환
    del df_total, df_cellti, df_triad, influencer_dfs
    gc.collect()
    
    # 🌟 용량이 큰 문자열(Object)을 아주 가벼운 카테고리로 2차 압축
    cat_cols = ['매체', '브랜드', '인플루언서명'] + [c for c in df_main.columns if 'CATEGORY' in c]
    for col in cat_cols:
        if col in df_main.columns:
            df_main[col] = df_main[col].astype('category')
    
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

df_filtered = df_all[df_all['브랜드'].isin(selected_brands)].copy()

sub_target_brands = set()
if "전체" in selected_brands: sub_target_brands.update(["전체", "셀티아이", "트리어드"])
else:
    for b in selected_brands:
        if "셀티아이" in b: sub_target_brands.add("셀티아이")
        if "트리어드" in b: sub_target_brands.add("트리어드")
        if "전체" in b: sub_target_brands.add("전체")

df_sub_filtered = df_sub_all[df_sub_all['브랜드'].isin(sub_target_brands)].copy() if sub_target_brands else df_sub_all.copy()

if any("인플루언서" in b for b in selected_brands):
    inf_list = df_filtered['인플루언서명'].dropna().unique().tolist()
    if inf_list:
        st.sidebar.markdown("---")
        selected_infs = st.sidebar.multiselect("👤 인플루언서 온/오프", inf_list, default=inf_list)
        mask_normal = df_filtered['인플루언서명'].isna()
        mask_selected_inf = df_filtered['인플루언서명'].isin(selected_infs)
        df_filtered = df_filtered[mask_normal | mask_selected_inf]
        st.sidebar.markdown("---")

min_date = df_all['날짜'].min().date()
max_date = df_all['날짜'].max().date()
default_start_date = max_date.replace(day=1) 
date_range = st.sidebar.date_input("🗓️ 조회 기간", value=(default_start_date, max_date), min_value=min_date, max_value=max_date)

if len(date_range) == 2: start_date, end_date = date_range
else: start_date, end_date = default_start_date, max_date 

media_options = ["전체"] + list(df_all['매체'].dropna().unique())
selected_media = st.sidebar.multiselect("📺 매체 선택", media_options, default=["전체"])

if "전체" not in selected_media:
    df_filtered = df_filtered[df_filtered['매체'].isin(selected_media)]

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
# [순서 1] 1줄: 깔끔하게 정리된 유입/구매 건수 요약
# =========================================================
st.caption(f"※ 비교 기준: 선택한 기간({duration}일)과 동일한 직전 기간({prev_start_date} ~ {prev_end_date}) 대비")

cur_total_visit = df_current['총방문수'].sum()
cur_new_visit = df_current['신규방문_총 방문수'].sum()
cur_ret_visit = df_current['재방문_총 방문수'].sum()
cur_total_buy = df_current['총구매수'].sum()
cur_new_buy = df_current['신규방문_신규구매_건수'].sum() + df_current['신규방문_재구매_건수'].sum()
cur_ret_buy = df_current['재방문_신규구매_건수'].sum() + df_current['재방문_재구매_건수'].sum()

prev_total_visit = df_prev['총방문수'].sum()
prev_new_visit = df_prev['신규방문_총 방문수'].sum()
prev_ret_visit = df_prev['재방문_총 방문수'].sum()
prev_total_buy = df_prev['총구매수'].sum()
prev_new_buy = df_prev['신규방문_신규구매_건수'].sum() + df_prev['신규방문_재구매_건수'].sum()
prev_ret_buy = df_prev['재방문_신규구매_건수'].sum() + df_prev['재방문_재구매_건수'].sum()

st.markdown("#### 👥 유입 및 🛒 구매 건수")
kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
kpi1.metric("총 방문수", format_number(cur_total_visit), delta=calculate_delta(cur_total_visit, prev_total_visit))
kpi2.metric("신규 방문수", format_number(cur_new_visit), delta=calculate_delta(cur_new_visit, prev_new_visit))
kpi3.metric("재방문수", format_number(cur_ret_visit), delta=calculate_delta(cur_ret_visit, prev_ret_visit))
kpi4.metric("총 구매", format_number(cur_total_buy), delta=calculate_delta(cur_total_buy, prev_total_buy))
kpi5.metric("신규 구매", format_number(cur_new_buy), delta=calculate_delta(cur_new_buy, prev_new_buy))
kpi6.metric("재방문 구매", format_number(cur_ret_buy), delta=calculate_delta(cur_ret_buy, prev_ret_buy))

st.markdown("<hr style='margin:0.5rem 0'>", unsafe_allow_html=True)

# =========================================================
# [순서 1-2] 2줄: 핵심 매출액 요약 (총 매출 = 신규+재구매+구독)
# =========================================================
cur_new_rev = df_current['신규방문_신규구매_매출액'].sum() + df_current['신규방문_재구매_매출액'].sum()
cur_ret_rev = df_current['재방문_신규구매_매출액'].sum() + df_current['재방문_재구매_매출액'].sum()
cur_sub_rev = df_sub_current['정기구독_매출액'].sum()
cur_grand_total_rev = cur_new_rev + cur_ret_rev + cur_sub_rev

prev_new_rev = df_prev['신규방문_신규구매_매출액'].sum() + df_prev['신규방문_재구매_매출액'].sum()
prev_ret_rev = df_prev['재방문_신규구매_매출액'].sum() + df_prev['재방문_재구매_매출액'].sum()
prev_sub_rev = df_sub_prev['정기구독_매출액'].sum()
prev_grand_total_rev = prev_new_rev + prev_ret_rev + prev_sub_rev

st.markdown("#### 💰 핵심 매출액 분석 (정기구독 포함)")
m1, m2, m3, m4 = st.columns(4)
m1.metric("🔥 총 매출", format_currency(cur_grand_total_rev), delta=calculate_delta(cur_grand_total_rev, prev_grand_total_rev))
m2.metric("✨ 신규 매출", format_currency(cur_new_rev), delta=calculate_delta(cur_new_rev, prev_new_rev))
m3.metric("🤝 재구매 매출", format_currency(cur_ret_rev), delta=calculate_delta(cur_ret_rev, prev_ret_rev))
m4.metric("🔄 정기구독 매출", format_currency(cur_sub_rev), delta=calculate_delta(cur_sub_rev, prev_sub_rev))

st.markdown("---")

# =========================================================
# [순서 2] 차트 및 타임라인
# =========================================================
col_chart_title, col_chart_opt = st.columns([5, 1])
with col_chart_title: st.markdown("#### 📅 유입 및 구매 추이")
with col_chart_opt: time_agg = st.radio("집계 기준", ["일간", "주간", "월간"], horizontal=True, label_visibility="collapsed")

if time_agg == "일간":
    df_trend = df_current.groupby(df_current['날짜'].dt.date)[['신규방문_총 방문수', '재방문_총 방문수', '총구매수']].sum().reset_index()
elif time_agg == "주간":
    df_trend = df_current.groupby(df_current['날짜'].dt.to_period('W').apply(lambda r: r.start_time))[['신규방문_총 방문수', '재방문_총 방문수', '총구매수']].sum().reset_index()
    df_trend['날짜'] = df_trend['날짜'].dt.date
else:
    df_trend = df_current.groupby(df_current['날짜'].dt.to_period('M').apply(lambda r: r.start_time))[['신규방문_총 방문수', '재방문_총 방문수', '총구매수']].sum().reset_index()
    df_trend['날짜'] = df_trend['날짜'].dt.date

fig_trend = go.Figure()
fig_trend.add_trace(go.Bar(x=df_trend['날짜'], y=df_trend['신규방문_총 방문수'], name="신규 유입수", marker_color='#82B1FF'))
fig_trend.add_trace(go.Bar(x=df_trend['날짜'], y=df_trend['재방문_총 방문수'], name="재방문 유입수", marker_color='#304FFE'))
fig_trend.add_trace(go.Scatter(x=df_trend['날짜'], y=df_trend['총구매수'], name="총 구매수", mode='lines+markers', yaxis='y2', line=dict(color='#FF5252', width=2.5), marker=dict(size=6)))
fig_trend.update_layout(template="plotly_white", barmode='stack', height=330, yaxis=dict(title='유입수', side='left', showgrid=True, gridcolor='#f0f2f6'), yaxis2=dict(title='구매건수', overlaying='y', side='right', showgrid=False), legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5), margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified")
st.plotly_chart(fig_trend, use_container_width=True)

if not df_camp_all.empty:
    camp_df = df_camp_all.copy()
    camp_target_brands = set()
    if "전체" in selected_brands:
        camp_target_brands.update(["전체", "셀티아이", "트리어드"])
    else:
        for b in selected_brands:
            if "셀티아이" in b: camp_target_brands.add("셀티아이")
            if "트리어드" in b: camp_target_brands.add("트리어드")
            
    camp_df = camp_df[camp_df['브랜드'].isin(camp_target_brands)]
        
    if not camp_df.empty:
        fig_gantt = px.timeline(camp_df, x_start="시작일", x_end="종료일", y="내용", color="구분", text="내용", height=200, color_discrete_sequence=['#4CAF50', '#FF9800'])
        fig_gantt.update_layout(template="plotly_white", xaxis=dict(range=[str(start_date), str(end_date)], type='date', showgrid=True, gridcolor='#f0f2f6'), yaxis=dict(title="", autorange="reversed"), showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.3, xanchor="center", x=0.5), margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig_gantt, use_container_width=True)

st.markdown("---")

# =========================================================
# [순서 3] 고객 여정 퍼널
# =========================================================
st.markdown("#### 🔽 고객 여정 퍼널")
col_funnel1, col_funnel2 = st.columns(2)

funnel_new = pd.DataFrame({'단계': ['1. 방문', '2. 관심', '3. 가입', '4. 구매시도', '5. 최종구매'], '수치': [df_current['신규방문_총 방문수'].sum(), df_current['신규방문_관심행동1'].sum(), df_current['신규방문_회원가입'].sum(), df_current['신규방문_구매시도'].sum(), cur_new_buy]})
fig_fnew = px.funnel(funnel_new, x='수치', y='단계', title="신규방문 퍼널", color_discrete_sequence=['#82B1FF'])
fig_fnew.update_traces(textinfo="value+percent initial") 
fig_fnew.update_layout(template="plotly_white", margin=dict(t=30, b=0), height=300)
col_funnel1.plotly_chart(fig_fnew, use_container_width=True)

funnel_ret = pd.DataFrame({'단계': ['1. 방문', '2. 관심', '3. 가입', '4. 구매시도', '5. 최종구매'], '수치': [df_current['재방문_총 방문수'].sum(), df_current['재방문_관심행동1'].sum(), df_current['재방문_회원가입'].sum(), df_current['재방문_구매시도'].sum(), cur_ret_buy]})
fig_fret = px.funnel(funnel_ret, x='수치', y='단계', title="재방문 퍼널", color_discrete_sequence=['#304FFE'])
fig_fret.update_traces(textinfo="value+percent initial")
fig_fret.update_layout(template="plotly_white", margin=dict(t=30, b=0), height=300)
col_funnel2.plotly_chart(fig_fret, use_container_width=True)

st.markdown("---")

# =========================================================
# [순서 4] 주요 매체 Top 5
# =========================================================
st.markdown("#### 🏆 주요 매체 Top 5")
col_top1, col_top2, col_top3 = st.columns(3)

top_visit = df_current.groupby('매체')['총방문수'].sum().reset_index().sort_values(by='총방문수', ascending=False).head(5)
fig_top_visit = px.bar(top_visit, x='총방문수', y='매체', orientation='h', title='1. 유입 기준', text_auto='.2s', color_discrete_sequence=['#B39DDB'])
fig_top_visit.update_layout(template="plotly_white", yaxis={'categoryorder':'total ascending'}, margin=dict(t=30, l=0, r=0, b=0), height=250) 
col_top1.plotly_chart(fig_top_visit, use_container_width=True)

top_signup = df_current.groupby('매체')['총회원가입'].sum().reset_index().sort_values(by='총회원가입', ascending=False).head(5)
fig_top_signup = px.bar(top_signup, x='총회원가입', y='매체', orientation='h', title='2. 가입 기준', text_auto='.0f', color_discrete_sequence=['#4DD0E1'])
fig_top_signup.update_layout(template="plotly_white", yaxis={'categoryorder':'total ascending'}, margin=dict(t=30, l=0, r=0, b=0), height=250)
col_top2.plotly_chart(fig_top_signup, use_container_width=True)

top_buy = df_current.groupby('매체')['총구매수'].
