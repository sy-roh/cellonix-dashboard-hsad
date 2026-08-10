import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta

# ---------------------------------------------------------
# 1. 페이지 및 기본 설정 (항상 최상단에 위치)
# ---------------------------------------------------------
st.set_page_config(page_title="셀로닉스 데이터 대시보드", layout="wide")

# =========================================================
# 🔒 보안: 대시보드 비밀번호 설정
# =========================================================
def check_password():
    """비밀번호가 일치하면 True를 반환합니다."""
    def password_entered():
        if st.session_state["password"] == "cellonix2026!":
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # 보안을 위해 세션에서 비밀번호 삭제
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔒 비밀번호를 입력하세요.", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("❌ 비밀번호가 틀렸습니다. 다시 입력하세요.", type="password", on_change=password_entered, key="password")
        return False
    return True

# 비밀번호가 틀리면 여기서 코드 실행을 멈춤
if not check_password():
    st.stop()
# =========================================================


# ---------------------------------------------------------
# 2. 초밀착(Compact) UI CSS
# ---------------------------------------------------------
st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    
    html, body, [class*="css"], [class*="st-"] {
        font-family: 'Pretendard', 'Noto Sans KR', sans-serif !important;
    }
    
    .block-container {
        padding-top: 2.5rem !important; 
        padding-bottom: 2rem !important;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 1.25rem !important;
        font-weight: 700 !important;
        color: #2c3e50;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
        color: #7f8c8d;
        margin-bottom: -5px !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.75rem !important;
    }
    
    h2, h3, h4 {
        padding-bottom: 0rem !important;
        margin-bottom: 0.5rem !important;
        margin-top: 0.5rem !important;
    }
    
    hr {
        margin-top: 0.8rem !important;
        margin-bottom: 0.8rem !important;
        border-color: #f0f2f6;
    }
    </style>
""", unsafe_allow_html=True)


def format_currency(val):
    return f"₩{val:,.0f}" if pd.notnull(val) else "₩0"

def format_number(val):
    return f"{val:,.0f}" if pd.notnull(val) else "0"

def calculate_delta(current_val, prev_val):
    if prev_val == 0 or pd.isnull(prev_val):
        return None
    change = ((current_val - prev_val) / prev_val) * 100
    return f"{change:.1f}%"

# ---------------------------------------------------------
# 3. 데이터 로드 및 전처리
# ---------------------------------------------------------
@st.cache_data(ttl=60)
def load_data():
    file_total = "2502-2608 공식몰전체 유입사용자_통계_데이터.xlsx"
    file_cellti = "2502-2608 셀티아이 유입사용자_통계_데이터.xlsx"
    file_triad = "2502-2608 트리어드 유입사용자_통계_데이터.xlsx"
    file_campaign = "캠페인 일정표.xlsx"
    
    df_total = pd.read_excel(file_total, sheet_name='유입 통계')
    df_total['브랜드'] = '전체'
    
    df_cellti = pd.read_excel(file_cellti, sheet_name='유입 통계')
    df_cellti['브랜드'] = '셀티아이'
    
    df_triad = pd.read_excel(file_triad, sheet_name='유입 통계')
    df_triad['브랜드'] = '트리어드'
    
    df_main = pd.concat([df_total, df_cellti, df_triad], ignore_index=True)
    df_main['날짜'] = pd.to_datetime(df_main['날짜'])
    
    df_main['총매출액'] = (
        df_main['신규방문_신규구매_매출액'].fillna(0) + 
        df_main['신규방문_재구매_매출액'].fillna(0) + 
        df_main['재방문_신규구매_매출액'].fillna(0) + 
        df_main['재방문_재구매_매출액'].fillna(0)
    )
    df_main['총방문수'] = df_main['신규방문_총 방문수'].fillna(0) + df_main['재방문_총 방문수'].fillna(0)
    df_main['총회원가입'] = df_main['신규방문_회원가입'].fillna(0) + df_main['재방문_회원가입'].fillna(0)
    df_main['총구매수'] = (
        df_main['신규방문_신규구매_건수'].fillna(0) + df_main['신규방문_재구매_건수'].fillna(0) +
        df_main['재방문_신규구매_건수'].fillna(0) + df_main['재방문_재구매_건수'].fillna(0)
    )
    
    df_campaign = pd.read_excel(file_campaign, sheet_name='Sheet2')
    df_campaign['시작일'] = pd.to_datetime(df_campaign['시작일'])
    df_campaign['종료일'] = pd.to_datetime(df_campaign['종료일'])
    
    mask_same_day = df_campaign['시작일'] == df_campaign['종료일']
    df_campaign.loc[mask_same_day, '종료일'] = df_campaign.loc[mask_same_day, '종료일'] + pd.Timedelta(days=1)
    
    return df_main, df_campaign

df_all, df_camp_all = load_data()

# ---------------------------------------------------------
# 4. 사이드바 (필터)
# ---------------------------------------------------------
st.sidebar.header("📊 필터")
brand_options = ["전체", "셀티아이", "트리어드"]
selected_brand = st.sidebar.selectbox("브랜드 선택", brand_options)

min_date = df_all['날짜'].min().date()
max_date = df_all['날짜'].max().date()
default_start_date = max_date.replace(day=1) 

date_range = st.sidebar.date_input(
    "조회 기간", 
    value=(default_start_date, max_date), 
    min_value=min_date, 
    max_value=max_date
)

if len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = default_start_date, max_date 

media_options = ["전체"] + list(df_all['매체'].dropna().unique())
selected_media = st.sidebar.multiselect("매체 선택", media_options, default=["전체"])

df_filtered = df_all.copy()
df_filtered = df_filtered[df_filtered['브랜드'] == selected_brand]

if "전체" not in selected_media:
    df_filtered = df_filtered[df_filtered['매체'].isin(selected_media)]

df_current = df_filtered[(df_filtered['날짜'].dt.date >= start_date) & (df_filtered['날짜'].dt.date <= end_date)]

duration = (end_date - start_date).days + 1
prev_end_date = start_date - timedelta(days=1)
prev_start_date = prev_end_date - timedelta(days=duration - 1)
df_prev = df_filtered[(df_filtered['날짜'].dt.date >= prev_start_date) & (df_filtered['날짜'].dt.date <= prev_end_date)]

st.title(f"📈 공식몰 성과 대시보드 ({selected_brand})")

# =========================================================
# [순서 1] 핵심 유입, 전환 및 매출 지표 (KPI)
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
# [순서 2] 일/주/월간 추이 복합 차트 & 마케팅 액션 타임라인
# =========================================================
col_chart_title, col_chart_opt = st.columns([5, 1])
with col_chart_title:
    st.markdown("#### 📅 유입 및 구매 추이")
with col_chart_opt:
    time_agg = st.radio("집계 기준", ["일간", "주간", "월간"], horizontal=True, label_visibility="collapsed")

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

fig_trend.update_layout(
    template="plotly_white", barmode='stack', height=330,
    yaxis=dict(title='유입수', side='left', showgrid=True, gridcolor='#f0f2f6'),
    yaxis2=dict(title='구매건수', overlaying='y', side='right', showgrid=False),
    legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5),
    margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified"
)
st.plotly_chart(fig_trend, use_container_width=True)

if not df_camp_all.empty:
    camp_df = df_camp_all.copy()
    if selected_brand != "전체":
        camp_df = camp_df[camp_df['브랜드'] == selected_brand]
    if not camp_df.empty:
        fig_gantt = px.timeline(camp_df, x_start="시작일", x_end="종료일", y="내용", color="구분", text="내용", height=200, color_discrete_sequence=['#4CAF50', '#FF9800'])
        fig_gantt.update_layout(
            template="plotly_white",
            xaxis=dict(range=[str(start_date), str(end_date)], type='date', showgrid=True, gridcolor='#f0f2f6'),
            yaxis=dict(title="", autorange="reversed"),
            showlegend=True,
            legend=dict(orientation="h", yanchor="top", y=-0.3, xanchor="center", x=0.5),
            margin=dict(l=0, r=0, t=20, b=0)
        )
        st.plotly_chart(fig_gantt, use_container_width=True)

st.markdown("---")

# =========================================================
# [순서 3] 유입 -> 전환 퍼널 차트
# =========================================================
st.markdown("#### 🔽 고객 여정 퍼널")
col_funnel1, col_funnel2 = st.columns(2)

funnel_new_data = {
    '단계': ['1. 방문', '2. 관심', '3. 가입', '4. 구매시도', '5. 최종구매'],
    '수치': [
        df_current['신규방문_총 방문수'].sum(), df_current['신규방문_관심행동1'].sum(),
        df_current['신규방문_회원가입'].sum(), df_current['신규방문_구매시도'].sum(), cur_new_buy
    ]
}
funnel_new = pd.DataFrame(funnel_new_data)
fig_fnew = px.funnel(funnel_new, x='수치', y='단계', title="신규방문 퍼널", color_discrete_sequence=['#82B1FF'])
fig_fnew.update_traces(textinfo="value+percent initial") 
fig_fnew.update_layout(template="plotly_white", margin=dict(t=30, b=0), height=300)
col_funnel1.plotly_chart(fig_fnew, use_container_width=True)

funnel_ret_data = {
    '단계': ['1. 방문', '2. 관심', '3. 가입', '4. 구매시도', '5. 최종구매'],
    '수치': [
        df_current['재방문_총 방문수'].sum(), df_current['재방문_관심행동1'].sum(),
        df_current['재방문_회원가입'].sum(), df_current['재방문_구매시도'].sum(), cur_ret_buy
    ]
}
funnel_ret = pd.DataFrame(funnel_ret_data)
fig_fret = px.funnel(funnel_ret, x='수치', y='단계', title="재방문 퍼널", color_discrete_sequence=['#304FFE'])
fig_fret.update_traces(textinfo="value+percent initial")
fig_fret.update_layout(template="plotly_white", margin=dict(t=30, b=0), height=300)
col_funnel2.plotly_chart(fig_fret, use_container_width=True)

st.markdown("---")

# =========================================================
# [순서 4] 매체별 랭킹 Top 5 (유입, 가입, 전환 3분할)
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
# [순서 5] NEW: 매체별 비중 및 CVR(전환율) 효율 분석
# =========================================================
st.markdown("#### 🎯 매체별 점유율 및 효율(CVR) 분석")

# 데이터 집계: 매체별 방문수, 구매수 합산 및 CVR 계산
df_media_eff = df_current.groupby('매체')[['총방문수', '총구매수']].sum().reset_index()
# 방문수가 0보다 큰 경우에만 CVR(구매/방문) 계산
df_media_eff['CVR(%)'] = df_media_eff.apply(
    lambda row: (row['총구매수'] / row['총방문수'] * 100) if row['총방문수'] > 0 else 0, axis=1
)

# 비중을 보기 좋게 정렬 (유입 많은 순)
df_media_eff = df_media_eff.sort_values('총방문수', ascending=False)

col_pie1, col_pie2, col_bar = st.columns([1, 1, 1.5])

# 1. 유입(방문) 비중 파이 차트
with col_pie1:
    fig_pie_visit = px.pie(
        df_media_eff, values='총방문수', names='매체', hole=0.4, 
        title='유입 점유율 (트래픽 비중)', 
        color_discrete_sequence=px.colors.sequential.Teal
    )
    fig_pie_visit.update_traces(textposition='inside', textinfo='percent+label', showlegend=False)
    fig_pie_visit.update_layout(template="plotly_white", margin=dict(t=40, b=0, l=0, r=0), height=320)
    st.plotly_chart(fig_pie_visit, use_container_width=True)

# 2. 전환(구매) 비중 파이 차트
with col_pie2:
    fig_pie_conv = px.pie(
        df_media_eff, values='총구매수', names='매체', hole=0.4, 
        title='전환 점유율 (구매 비중)', 
        color_discrete_sequence=px.colors.sequential.OrRd
    )
    fig_pie_conv.update_traces(textposition='inside', textinfo='percent+label', showlegend=False)
    fig_pie_conv.update_layout(template="plotly_white", margin=dict(t=40, b=0, l=0, r=0), height=320)
    st.plotly_chart(fig_pie_conv, use_container_width=True)

# 3. 매체별 CVR(전환율) 바 차트
with col_bar:
    # CVR 높은 순으로 정렬하여 탑 10개만 시각화
    df_cvr_top = df_media_eff.sort_values('CVR(%)', ascending=False).head(10)
    fig_cvr_bar = px.bar(
        df_cvr_top, x='매체', y='CVR(%)', 
        title='매체별 구매 전환율 (CVR Top 10)', 
        text_auto='.2f', color='CVR(%)', color_continuous_scale='Blues'
    )
    fig_cvr_bar.update_layout(
        template="plotly_white", 
        margin=dict(t=40, b=0, l=0, r=0), height=320,
        coloraxis_showscale=False # 컬러바 숨기기
    )
    st.plotly_chart(fig_cvr_bar, use_container_width=True)