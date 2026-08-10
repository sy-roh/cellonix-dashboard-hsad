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
        st.text_input("🔒 비밀번호를 입력하세요.", type="password", on_change=password_entered, key="password")
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
    [data-testid="stMetricLabel"] { font-size: 0.85rem !important; color: #7f8c8d; margin-bottom: -5px !important; }
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
    
    # [1] 전체 데이터 읽어오기
    df_total = pd.read_csv(get_csv_url('전체'))
    
    # ==== 🌟 인플루언서 데이터 추출 자동화 🌟 ====
    str_cols = df_total.select_dtypes(include=['object']).columns
    is_meta_yt = df_total['매체'].astype(str).str.upper().isin(['META', '유튜브'])
    
    # 인플루언서별 정규식 패턴 (한글, 영문, 별명 모두 포함)
    influencers_dict = {
        '문지애': r'(?i)문지애|jiae|지애',
        '김미경': r'(?i)김미경|mikyung|mkyu|미경',
        '채정안': r'(?i)채정안|jungan|정안',
        '이재성': r'(?i)이재성|jaesung',
        '한고은': r'(?i)한고은|고은|goeun',
        '강주은': r'(?i)강주은|jueun|주은|깡주은'
    }
    
    influencer_dfs = []
    
    for name, pattern in influencers_dict.items():
        # 해당 인플루언서 패턴이 카테고리에 포함되어 있는지 검사
        mask = is_meta_yt & df_total[str_cols].apply(lambda x: x.astype(str).str.contains(pattern)).any(axis=1)
        df_inf = df_total[mask].copy()
        
        if not df_inf.empty:
            df_inf['인플루언서명'] = name
            
            # 브랜드 할당 (문지애 -> 셀티아이, 나머지 -> 트리어드)
            if name == '문지애':
                df_inf['브랜드'] = '셀티아이 인플루언서'
            else:
                df_inf['브랜드'] = '트리어드 인플루언서'
                
            influencer_dfs.append(df_inf)
    # ============================================
    
    df_total['브랜드'] = '전체'
    df_total['인플루언서명'] = None
    
    # [2] 셀티아이 / 트리어드 개별 데이터 읽어오기
    df_cellti = pd.read_csv(get_csv_url('셀티아이'))
    df_cellti['브랜드'] = '셀티아이'
    df_cellti['인플루언서명'] = None
    
    df_triad = pd.read_csv(get_csv_url('트리어드'))
    df_triad['브랜드'] = '트리어드'
    df_triad['인플루언서명'] = None
    
    # [3] 총 5가지 브랜드를 하나의 메인 데이터로 결합
    df_main = pd.concat([df_total, df_cellti, df_triad] + influencer_dfs, ignore_index=True)
    df_main['날짜'] = pd.to_datetime(df_main['날짜'])
    
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
    
    # 캠페인 일정 데이터 로드
    df_campaign = pd.read_csv(get_csv_url('캠페인'))
    df_campaign['시작일'] = pd.to_datetime(df_campaign['시작일'])
    df_campaign['종료일'] = pd.to_datetime(df_campaign['종료일'])
    mask_same_day = df_campaign['시작일'] == df_campaign['종료일']
    df_campaign.loc[mask_same_day, '종료일'] = df_campaign.loc[mask_same_day, '종료일'] + pd.Timedelta(days=1)
    
    return df_main, df_campaign

df_all, df_camp_all = load_data()

# ---------------------------------------------------------
# 4. 사이드바 (필터) 및 대시보드 렌더링
# ---------------------------------------------------------
st.sidebar.header("📊 필터")
brand_options = ["전체", "셀티아이", "셀티아이 인플루언서", "트리어드", "트리어드 인플루언서"]
selected_brand = st.sidebar.selectbox("브랜드 선택", brand_options)

# 1차 필터링: 브랜드 선택
df_filtered = df_all.copy()
df_filtered = df_filtered[df_filtered['브랜드'] == selected_brand]

# 2차 필터링: 인플루언서 개별 선택 (인플루언서 브랜드를 선택했을 때만 등장)
if "인플루언서" in selected_brand:
    inf_list = df_filtered['인플루언서명'].dropna().unique().tolist()
    if inf_list:
        selected_infs = st.sidebar.multiselect("👤 인플루언서 선택 (체크박스)", inf_list, default=inf_list)
        df_filtered = df_filtered[df_filtered['인플루언서명'].isin(selected_infs)]

# 3차 필터링: 날짜
min_date = df_all['날짜'].min().date()
max_date = df_all['날짜'].max().date()
default_start_date = max_date.replace(day=1) 
date_range = st.sidebar.date_input("조회 기간", value=(default_start_date, max_date), min_value=min_date, max_value=max_date)

if len(date_range) == 2: start_date, end_date = date_range
else: start_date, end_date = default_start_date, max_date 

# 4차 필터링: 매체
media_options = ["전체"] + list(df_all['매체'].dropna().unique())
selected_media = st.sidebar.multiselect("매체 선택", media_options, default=["전체"])

if "전체" not in selected_media:
    df_filtered = df_filtered[df_filtered['매체'].isin(selected_media)]

# 현재 데이터와 비교용 이전 기간 데이터 산출
df_current = df_filtered[(df_filtered['날짜'].dt.date >= start_date) & (df_filtered['날짜'].dt.date <= end_date)]

duration = (end_date - start_date).days + 1
prev_end_date = start_date - timedelta(days=1)
prev_start_date = prev_end_date - timedelta(days=duration - 1)
df_prev = df_filtered[(df_filtered['날짜'].dt.date >= prev_start_date) & (df_filtered['날짜'].dt.date <= prev_end_date)]

st.title(f"📈 공식몰 성과 대시보드 ({selected_brand})")

# =========================================================
# [순서 1] KPI
# =========================================================
st.caption(f"※ 비교 기준: 선택한 기간({duration}일)과 동일한 직전 기간({prev_start_date} ~ {prev_end_date}) 대비")

cur_total_visit = df_current['총방문수'].sum()
cur_new_visit = df_current['신규방문_총 방문수'].sum()
cur_ret_visit = df_current['재방문_총 방문수'].sum()
cur_total_buy = df_current['총구매수'].sum()
cur_new_buy = df_current['신규방문_신규구매_건수'].sum() + df_current['신규방문_재구매_건수'].sum()
cur_ret_buy = df_current['재방문_신규구매_건수'].sum() + df_current['재방문_재구매_건수'].sum()
cur_total_rev = df_current['총매출액'].sum()
cur_new_rev = df_current['신규방문_신규구매_매출액'].sum() + df_current['신규방문_재구매_매출액'].sum()
cur_ret_rev = df_current['재방문_신규구매_매출액'].sum() + df_current['재방문_재구매_매출액'].sum()

prev_total_visit = df_prev['총방문수'].sum()
prev_new_visit = df_prev['신규방문_총 방문수'].sum()
prev_ret_visit = df_prev['재방문_총 방문수'].sum()
prev_total_buy = df_prev['총구매수'].sum()
prev_new_buy = df_prev['신규방문_신규구매_건수'].sum() + df_prev['신규방문_재구매_건수'].sum()
prev_ret_buy = df_prev['재방문_신규구매_건수'].sum() + df_prev['재방문_재구매_건수'].sum()
prev_total_rev = df_prev['총매출액'].sum()
prev_new_rev = df_prev['신규방문_신규구매_매출액'].sum() + df_prev['신규방문_재구매_매출액'].sum()
prev_ret_rev = df_prev['재방문_신규구매_매출액'].sum() + df_prev['재방문_재구매_매출액'].sum()

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("**👥 유입 지표**")
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("총 방문수", format_number(cur_total_visit), delta=calculate_delta(cur_total_visit, prev_total_visit))
    cc2.metric("신규 방문", format_number(cur_new_visit), delta=calculate_delta(cur_new_visit, prev_new_visit))
    cc3.metric("재방문", format_number(cur_ret_visit), delta=calculate_delta(cur_ret_visit, prev_ret_visit))
with col2:
    st.markdown("**🛒 구매 건수**")
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("총 구매", format_number(cur_total_buy), delta=calculate_delta(cur_total_buy, prev_total_buy))
    cc2.metric("신규 구매", format_number(cur_new_buy), delta=calculate_delta(cur_new_buy, prev_new_buy))
    cc3.metric("재방문 구매", format_number(cur_ret_buy), delta=calculate_delta(cur_ret_buy, prev_ret_buy))
with col3:
    st.markdown("**💰 매출액**")
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("총 매출", format_currency(cur_total_rev), delta=calculate_delta(cur_total_rev, prev_total_rev))
    cc2.metric("신규 매출", format_currency(cur_new_rev), delta=calculate_delta(cur_new_rev, prev_new_rev))
    cc3.metric("재방문 매출", format_currency(cur_ret_rev), delta=calculate_delta(cur_ret_rev, prev_ret_rev))

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
    
    # 🌟 인플루언서 옵션 선택 시에도 해당 모(母)브랜드의 캠페인을 보여주도록 처리
    if selected_brand == "셀티아이 인플루언서":
        camp_df = camp_df[camp_df['브랜드'] == "셀티아이"]
    elif selected_brand == "트리어드 인플루언서":
        camp_df = camp_df[camp_df['브랜드'] == "트리어드"]
    elif selected_brand != "전체": 
        camp_df = camp_df[camp_df['브랜드'] == selected_brand]
        
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

top_buy = df_current.groupby('매체')['총구매수'].sum().reset_index().sort_values(by='총구매수', ascending=False).head(5)
fig_top_buy = px.bar(top_buy, x='총구매수', y='매체', orientation='h', title='3. 구매 기준', text_auto='.0f', color_discrete_sequence=['#F48FB1'])
fig_top_buy.update_layout(template="plotly_white", yaxis={'categoryorder':'total ascending'}, margin=dict(t=30, l=0, r=0, b=0), height=250)
col_top3.plotly_chart(fig_top_buy, use_container_width=True)

st.markdown("---")

# =========================================================
# [순서 5] 매체별 점유율 (파이차트)
# =========================================================
st.markdown("#### 🎯 매체별 점유율 (유입 및 전환)")
df_media_eff = df_current.groupby('매체')[['총방문수', '총구매수']].sum().reset_index().sort_values('총방문수', ascending=False)
col_pie1, col_pie2 = st.columns(2)

with col_pie1:
    fig_pie_visit = px.pie(df_media_eff, values='총방문수', names='매체', hole=0.4, title='유입 점유율 (트래픽 비중)', color_discrete_sequence=px.colors.sequential.Teal)
    fig_pie_visit.update_traces(textposition='inside', textinfo='percent+label', showlegend=False)
    fig_pie_visit.update_layout(template="plotly_white", margin=dict(t=40, b=0, l=0, r=0), height=350)
    st.plotly_chart(fig_pie_visit, use_container_width=True)

with col_pie2:
    fig_pie_conv = px.pie(df_media_eff, values='총구매수', names='매체', hole=0.4, title='전환 점유율 (구매 비중)', color_discrete_sequence=px.colors.sequential.OrRd)
    fig_pie_conv.update_traces(textposition='inside', textinfo='percent+label', showlegend=False)
    fig_pie_conv.update_layout(template="plotly_white", margin=dict(t=40, b=0, l=0, r=0), height=350)
    st.plotly_chart(fig_pie_conv, use_container_width=True)

st.markdown("---")

# =========================================================
# [순서 6] 매체별 증감 추이 및 전체 현황표
# =========================================================
st.markdown("#### 🔄 비교 기간 대비 매체 운영 현황")
st.caption("※ 설정된 기간과 직전 동일 기간을 비교합니다.")

df_curr_media = df_current.groupby('매체')['총방문수'].sum().reset_index().rename(columns={'총방문수': '이번_유입수'})
df_prev_media = df_prev.groupby('매체')['총방문수'].sum().reset_index().rename(columns={'총방문수': '이전_유입수'})
df_compare = pd.merge(df_prev_media, df_curr_media, on='매체', how='outer').fillna(0)

def get_media_status(row):
    if row['이전_유입수'] == 0 and row['이번_유입수'] > 0: return "🆕 신규 진입"
    elif row['이전_유입수'] > 0 and row['이번_유입수'] == 0: return "⏸️ 운영 중단"
    elif row['이번_유입수'] > row['이전_유입수']: return "🔼 유입 증가"
    elif row['이번_유입수'] < row['이전_유입수']: return "🔽 유입 감소"
    else: return "▶️ 유지"

df_compare['상태'] = df_compare.apply(get_media_status, axis=1)
df_compare['증감량'] = df_compare['이번_유입수'] - df_compare['이전_유입수']
df_compare['증감률(%)'] = df_compare.apply(lambda r: ((r['이번_유입수'] - r['이전_유입수']) / r['이전_유입수'] * 100) if r['이전_유입수'] != 0 else 0, axis=1)
df_compare = df_compare[['상태', '매체', '이전_유입수', '이번_유입수', '증감량', '증감률(%)']].sort_values(by='이번_유입수', ascending=False)

st.dataframe(
    df_compare, use_container_width=True, hide_index=True,
    column_config={
        "상태": st.column_config.TextColumn("상태", width="medium"),
        "매체": st.column_config.TextColumn("매체명", width="medium"),
        "이전_유입수": st.column_config.NumberColumn("이전 기간 유입", format="%d"),
        "이번_유입수": st.column_config.NumberColumn("이번 기간 유입", format="%d"),
        "증감량": st.column_config.NumberColumn("증감량", format="%d"),
        "증감률(%)": st.column_config.NumberColumn("증감률", format="%.1f%%")
    }
)
