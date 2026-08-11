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
brand_options = ["전체", "셀티아이", "셀티아이 인플루언서", "트리어드", "트리어드 인플루언서", "기타"]
selected_brands = st.sidebar.multiselect("📌 브랜드 선택", brand_options, default=["전체"])

if not selected_brands:
    st.warning("👈 브랜드를 선택해 주세요.")
    st.stop()

effective_brands = ["전체"] if "전체" in selected_brands else selected_brands
df_filtered = df_all[df_all['브랜드'].isin(effective_brands)].copy()

def filter_actual_sales_by_brand(df_sub, brands):
    if df_sub.empty:
        return df_sub.copy()
    if "전체" in brands:
        return df_sub[df_sub['브랜드'].isin(['셀티아이', '트리어드'])].copy()
    target_brands = set()
    for b in brands:
        if "셀티아이" in b: target_brands.add("셀티아이")
        if "트리어드" in b: target_brands.add("트리어드")
    if not target_brands:
        return df_sub.iloc[0:0].copy()
    return df_sub[df_sub['브랜드'].isin(target_brands)].copy()

df_sub_filtered = filter_actual_sales_by_brand(df_sub_all, effective_brands)

if any("인플루언서" in b for b in effective_brands):
    inf_list = df_filtered.get('인플루언서명', pd.Series()).dropna().unique().tolist()
    if inf_list:
        selected_infs = st.sidebar.multiselect("👤 인플루언서 온/오프", inf_list, default=inf_list)
        df_filtered = df_filtered[df_filtered['인플루언서명'].isna() | df_filtered['인플루언서명'].isin(selected_infs)]

min_date, max_date = df_all['날짜'].min().date(), df_all['날짜'].max().date()

# ---------------------------------------------------------
# 🌟 빠른 월 선택 기능 (1월 ~ 12월 버튼)
# ---------------------------------------------------------
if 'my_date_picker' not in st.session_state:
    st.session_state['my_date_picker'] = (max_date.replace(day=1), max_date)

st.sidebar.markdown("---")
st.sidebar.markdown("**🗓️ 빠른 월 선택**")

years = list(range(min_date.year, max_date.year + 1))
selected_year = st.sidebar.selectbox("연도", years, index=years.index(max_date.year), label_visibility="collapsed")

def set_month(y, m):
    s_date = pd.Timestamp(y, m, 1).date()
    e_date = (pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)).date()
    if s_date < min_date: s_date = min_date
    if e_date > max_date: e_date = max_date
    st.session_state['my_date_picker'] = (s_date, e_date)

for row in range(4):
    cols = st.sidebar.columns(3)
    for col_idx in range(3):
        m = row * 3 + col_idx + 1
        if cols[col_idx].button(f"{m}월", key=f"btn_m_{m}", use_container_width=True):
            set_month(selected_year, m)

date_range = st.sidebar.date_input("직접 기간 선택", min_value=min_date, max_value=max_date, key='my_date_picker')
start_date, end_date = date_range if len(date_range) == 2 else (date_range[0], date_range[0])

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
# 상단 KPI (유입 / 구매건수 분리)
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

st.markdown("<hr style='margin:0.5rem 0'>", unsafe_allow_html=True)

# ---------------------------------------------------------
# 매출 지표 (공식몰 실매출 / 로그 매출 / 정기구독)
# ---------------------------------------------------------
cur_log_new_rev = df_current['신규방문_신규구매_매출액'].sum() + df_current['신규방문_재구매_매출액'].sum()
cur_log_return_rev = df_current['재방문_신규구매_매출액'].sum() + df_current['재방문_재구매_매출액'].sum()
prev_log_new_rev = df_prev['신규방문_신규구매_매출액'].sum() + df_prev['신규방문_재구매_매출액'].sum()
prev_log_return_rev = df_prev['재방문_신규구매_매출액'].sum() + df_prev['재방문_재구매_매출액'].sum()

cur_log_total_rev = cur_log_new_rev + cur_log_return_rev
prev_log_total_rev = prev_log_new_rev + prev_log_return_rev

if "전체" in effective_brands:
    official_target_brands = ['셀티아이', '트리어드']
else:
    official_target_brands = []
    for b in effective_brands:
        if "셀티아이" in b and "셀티아이" not in official_target_brands: official_target_brands.append("셀티아이")
        if "트리어드" in b and "트리어드" not in official_target_brands: official_target_brands.append("트리어드")

show_triad_subscription = ("전체" in effective_brands or any("트리어드" in b for b in effective_brands))

if show_triad_subscription:
    cur_subscription_log = df_sub_current[df_sub_current['브랜드'] == '트리어드']['정기구독_매출액'].sum()
    prev_subscription_log = df_sub_prev[df_sub_prev['브랜드'] == '트리어드']['정기구독_매출액'].sum()
else:
    cur_subscription_log = 0
    prev_subscription_log = 0

df_sub_current['브랜드_실매출'] = pd.to_numeric(df_sub_current.get('신규구매', 0), errors='coerce').fillna(0) + pd.to_numeric(df_sub_current.get('재구매', 0), errors='coerce').fillna(0)
df_sub_prev['브랜드_실매출'] = pd.to_numeric(df_sub_prev.get('신규구매', 0), errors='coerce').fillna(0) + pd.to_numeric(df_sub_prev.get('재구매', 0), errors='coerce').fillna(0)

cur_official_gross = df_sub_current[df_sub_current['브랜드'].isin(official_target_brands)]['브랜드_실매출'].sum()
prev_official_gross = df_sub_prev[df_sub_prev['브랜드'].isin(official_target_brands)]['브랜드_실매출'].sum()

cur_official_actual = cur_official_gross - cur_subscription_log
prev_official_actual = prev_official_gross - prev_subscription_log

st.markdown("#### 💰 매출 요약")
st.caption("※ 공식몰 실매출은 정기구독 시트의 셀티아이·트리어드 '신규 구매 + 재 구매'에서 트리어드 '정기구독 할인금액'을 제외한 순매출입니다. 로그 매출 합계는 전체 시트의 로그 신규 매출 + 로그 재방문 매출이며, 정기구독은 트리어드의 '정기구독 할인금액'입니다.")

m1, sep1, m2, m3, m4, sep2, m5 = st.columns([1.25, 0.06, 1.15, 1.15, 1.15, 0.06, 1.15])

m1.metric("🔥 공식몰 실매출", format_currency(cur_official_actual), delta=calculate_delta(cur_official_actual, prev_official_actual))
with sep1: st.markdown("<div style='border-left:1px solid #D9D9D9;height:92px;margin:6px auto 0 auto;width:1px;'></div>", unsafe_allow_html=True)
m2.metric("📊 로그 매출 합계", format_currency(cur_log_total_rev), delta=calculate_delta(cur_log_total_rev, prev_log_total_rev))
m3.metric("✨ 로그 신규 매출", format_currency(cur_log_new_rev), delta=calculate_delta(cur_log_new_rev, prev_log_new_rev))
m4.metric("🤝 로그 재방문 매출", format_currency(cur_log_return_rev), delta=calculate_delta(cur_log_return_rev, prev_log_return_rev))
with sep2: st.markdown("<div style='border-left:1px solid #D9D9D9;height:92px;margin:6px auto 0 auto;width:1px;'></div>", unsafe_allow_html=True)
m5.metric("🔄 정기구독", format_currency(cur_subscription_log), delta=calculate_delta(cur_subscription_log, prev_subscription_log))

st.markdown("---")

# ---------------------------------------------------------
# 차트 및 타임라인
# ---------------------------------------------------------
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
    if "전체" in effective_brands: camp_target_brands.update(["전체", "셀티아이", "트리어드"])
    else:
        for b in effective_brands:
            if "셀티아이" in b: camp_target_brands.add("셀티아이")
            if "트리어드" in b: camp_target_brands.add("트리어드")
    camp_df = camp_df[camp_df['브랜드'].isin(camp_target_brands)]
    if not camp_df.empty:
        fig_gantt = px.timeline(camp_df, x_start="시작일", x_end="종료일", y="내용", color="구분", text="내용", height=200, color_discrete_sequence=['#4CAF50', '#FF9800'])
        fig_gantt.update_layout(template="plotly_white", xaxis=dict(range=[str(start_date), str(end_date)], type='date', showgrid=True, gridcolor='#f0f2f6'), yaxis=dict(title="", autorange="reversed"), showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.3, xanchor="center", x=0.5), margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig_gantt, use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------
# 고객 여정 퍼널 (🌟 에러가 발생했던 구간 완벽 수정됨)
# ---------------------------------------------------------
st.markdown("#### 🔽 고객 여정 퍼널")
col_funnel1, col_funnel2 = st.columns(2)

cur_new_buy = df_current['신규방문_신규구매_건수'].sum() + df_current['신규방문_재구매_건수'].sum()
prev_new_buy = df_prev['신규방문_신규구매_건수'].sum() + df_prev['신규방문_재구매_건수'].sum()
cur_ret_buy = df_current['재방문_신규구매_건수'].sum() + df_current['재방문_재구매_건수'].sum()
prev_ret_buy = df_prev['재방문_신규구매_건수'].sum() + df_prev['재방문_재구매_건수'].sum()

funnel_new = pd.DataFrame({
    '단계': ['1. 방문', '2. 관심', '3. 가입', '4. 구매시도', '5. 최종구매'], 
    '수치': [df_current['신규방문_총 방문수'].sum(), df_current['신규방문_관심행동1'].sum(), df_current['신규방문_회원가입'].sum(), df_current['신규방문_구매시도'].sum(), cur_new_buy],
    '이전': [df_prev['신규방문_총 방문수'].sum(), df_prev['신규방문_관심행동1'].sum(), df_prev['신규방문_회원가입'].sum(), df_prev['신규방문_구매시도'].sum(), prev_new_buy]
})
funnel_new['증감텍스트'] = (funnel_new['수치'] - funnel_new['이전']).apply(lambda x: f"▲ {int(x):,}" if x > 0 else (f"▼ {int(abs(x)):,}" if x < 0 else "-"))

fig_fnew = px.funnel(funnel_new, x='수치', y='단계', title="신규방문 퍼널", color_discrete_sequence=['#82B1FF'])
# 🌟 안정적인 강제 데이터 주입 방식 적용
fig_fnew.update_traces(customdata=funnel_new['증감텍스트'].tolist(), textinfo="value+percent initial", hovertemplate="<b>%{y}</b><br>수치: %{x:,}<br>전기간 대비: %{customdata}<extra></extra>") 
fig_fnew.update_layout(template="plotly_white", margin=dict(t=30, b=0), height=300)
col_funnel1.plotly_chart(fig_fnew, use_container_width=True)

funnel_ret = pd.DataFrame({
    '단계': ['1. 방문', '2. 관심', '3. 가입', '4. 구매시도', '5. 최종구매'], 
    '수치': [df_current['재방문_총 방문수'].sum(), df_current['재방문_관심행동1'].sum(), df_current['재방문_회원가입'].sum(), df_current['재방문_구매시도'].sum(), cur_ret_buy],
    '이전': [df_prev['재방문_총 방문수'].sum(), df_prev['재방문_관심행동1'].sum(), df_prev['재방문_회원가입'].sum(), df_prev['재방문_구매시도'].sum(), prev_ret_buy]
})
funnel_ret['증감텍스트'] = (funnel_ret['수치'] - funnel_ret['이전']).apply(lambda x: f"▲ {int(x):,}" if x > 0 else (f"▼ {int(abs(x)):,}" if x < 0 else "-"))

fig_fret = px.funnel(funnel_ret, x='수치', y='단계', title="재방문 퍼널", color_discrete_sequence=['#304FFE'])
fig_fret.update_traces(customdata=funnel_ret['증감텍스트'].tolist(), textinfo="value+percent initial", hovertemplate="<b>%{y}</b><br>수치: %{x:,}<br>전기간 대비: %{customdata}<extra></extra>")
fig_fret.update_layout(template="plotly_white", margin=dict(t=30, b=0), height=300)
col_funnel2.plotly_chart(fig_fret, use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------
# 주요 매체 Top 5
# ---------------------------------------------------------
st.markdown("#### 🏆 주요 매체 Top 5")
col_top1, col_top2, col_top3 = st.columns(3)

top_visit = pd.merge(df_current.groupby('매체')['총방문수'].sum().reset_index(), df_prev.groupby('매체')['총방문수'].sum().reset_index().rename(columns={'총방문수':'이전'}), on='매체', how='left').fillna(0)
top_visit['증감텍스트'] = (top_visit['총방문수'] - top_visit['이전']).apply(lambda x: f"▲ {int(x):,}" if x > 0 else (f"▼ {int(abs(x)):,}" if x < 0 else "-"))
top_visit = top_visit.sort_values(by='총방문수', ascending=False).head(5)

fig_top_visit = px.bar(top_visit, x='총방문수', y='매체', orientation='h', title='1. 유입 기준', text_auto='.2s', color_discrete_sequence=['#B39DDB'])
fig_top_visit.update_traces(customdata=top_visit['증감텍스트'].tolist(), hovertemplate="<b>%{y}</b><br>유입수: %{x:,}<br>전기간 대비: %{customdata}<extra></extra>")
fig_top_visit.update_layout(template="plotly_white", yaxis={'categoryorder':'total ascending'}, margin=dict(t=30, l=0, r=0, b=0), height=250) 
col_top1.plotly_chart(fig_top_visit, use_container_width=True)

top_signup = pd.merge(df_current.groupby('매체')['총회원가입'].sum().reset_index(), df_prev.groupby('매체')['총회원가입'].sum().reset_index().rename(columns={'총회원가입':'이전'}), on='매체', how='left').fillna(0)
top_signup['증감텍스트'] = (top_signup['총회원가입'] - top_signup['이전']).apply(lambda x: f"▲ {int(x):,}" if x > 0 else (f"▼ {int(abs(x)):,}" if x < 0 else "-"))
top_signup = top_signup.sort_values(by='총회원가입', ascending=False).head(5)

fig_top_signup = px.bar(top_signup, x='총회원가입', y='매체', orientation='h', title='2. 가입 기준', text_auto='.0f', color_discrete_sequence=['#4DD0E1'])
fig_top_signup.update_traces(customdata=top_signup['증감텍스트'].tolist(), hovertemplate="<b>%{y}</b><br>가입수: %{x:,}<br>전기간 대비: %{customdata}<extra></extra>")
fig_top_signup.update_layout(template="plotly_white", yaxis={'categoryorder':'total ascending'}, margin=dict(t=30, l=0, r=0, b=0), height=250)
col_top2.plotly_chart(fig_top_signup, use_container_width=True)

top_sales = pd.merge(df_current.groupby('매체')['총매출액'].sum().reset_index(), df_prev.groupby('매체')['총매출액'].sum().reset_index().rename(columns={'총매출액': '이전'}), on='매체', how='left').fillna(0)
top_sales['증감텍스트'] = (top_sales['총매출액'] - top_sales['이전']).apply(lambda x: f"▲ ₩{int(x):,}" if x > 0 else (f"▼ ₩{int(abs(x)):,}" if x < 0 else "-"))
top_sales = top_sales.sort_values(by='총매출액', ascending=False).head(5)

fig_top_sales = px.bar(top_sales, x='총매출액', y='매체', orientation='h', title='3. 매체별 매출 기준', text_auto='.2s', color_discrete_sequence=['#F48FB1'])
fig_top_sales.update_traces(customdata=top_sales['증감텍스트'].tolist(), hovertemplate="<b>%{y}</b><br>매출: ₩%{x:,.0f}<br>전기간 대비: %{customdata}<extra></extra>")
fig_top_sales.update_layout(template="plotly_white", yaxis={'categoryorder': 'total ascending'}, margin=dict(t=30, l=0, r=0, b=0), height=250)
col_top3.plotly_chart(fig_top_sales, use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------
# 매체 점유율 및 현황표
# ---------------------------------------------------------
st.markdown("#### 🎯 매체별 점유율 (유입 및 매출)")
df_media_eff = df_current.groupby('매체')[['총방문수', '총구매수', '총매출액']].sum().reset_index().sort_values('총방문수', ascending=False)
col_pie1, col_pie2 = st.columns(2)

with col_pie1:
    fig_pie_visit = px.pie(df_media_eff, values='총방문수', names='매체', hole=0.4, title='유입 점유율 (트래픽 비중)', color_discrete_sequence=px.colors.sequential.Teal)
    fig_pie_visit.update_traces(textposition='inside', textinfo='percent+label', showlegend=False)
    fig_pie_visit.update_layout(template="plotly_white", margin=dict(t=40, b=0, l=0, r=0), height=350)
    st.plotly_chart(fig_pie_visit, use_container_width=True)

with col_pie2:
    fig_pie_sales = px.pie(df_media_eff, values='총매출액', names='매체', hole=0.4, title='매체별 매출 점유율', color_discrete_sequence=px.colors.sequential.OrRd)
    fig_pie_sales.update_traces(textposition='inside', textinfo='percent+label', showlegend=False, hovertemplate="<b>%{label}</b><br>매출: ₩%{value:,.0f}<br>비중: %{percent}<extra></extra>")
    fig_pie_sales.update_layout(template="plotly_white", margin=dict(t=40, b=0, l=0, r=0), height=350)
    st.plotly_chart(fig_pie_sales, use_container_width=True)

st.markdown("---")

st.markdown("#### 🔄 비교 기간 대비 매체 운영 현황")
st.caption("※ 설정된 기간과 직전 동일 기간을 비교합니다.")

df_curr_media = df_current.groupby('매체')[['총방문수', '총매출액']].sum().reset_index().rename(columns={'총방문수': '이번_유입수', '총매출액': '이번_매출'})
df_prev_media = df_prev.groupby('매체')[['총방문수', '총매출액']].sum().reset_index().rename(columns={'총방문수': '이전_유입수', '총매출액': '이전_매출'})
df_compare = pd.merge(df_prev_media, df_curr_media, on='매체', how='outer').fillna(0)

def get_media_status(row):
    if row['이전_유입수'] == 0 and row['이번_유입수'] > 0: return "🆕 신규 진입"
    elif row['이전_유입수'] > 0 and row['이번_유입수'] == 0: return "⏸️ 운영 중단"
    elif row['이번_유입수'] > row['이전_유입수']: return "🔼 유입 증가"
    elif row['이번_유입수'] < row['이전_유입수']: return "🔽 유입 감소"
    else: return "▶️ 유지"

df_compare['상태'] = df_compare.apply(get_media_status, axis=1)
df_compare['유입_증감률(%)'] = df_compare.apply(lambda r: ((r['이번_유입수'] - r['이전_유입수']) / r['이전_유입수'] * 100) if r['이전_유입수'] != 0 else 0, axis=1)
df_compare['매출_증감률(%)'] = df_compare.apply(lambda r: ((r['이번_매출'] - r['이전_매출']) / r['이전_매출'] * 100) if r['이전_매출'] != 0 else 0, axis=1)

df_compare = df_compare[['상태', '매체', '이전_유입수', '이번_유입수', '유입_증감률(%)', '이전_매출', '이번_매출', '매출_증감률(%)']].sort_values(by='이번_매출', ascending=False)

st.dataframe(
    df_compare, use_container_width=True, hide_index=True,
    column_config={
        "상태": st.column_config.TextColumn("상태", width="medium"),
        "매체": st.column_config.TextColumn("매체명", width="medium"),
        "이전_유입수": st.column_config.NumberColumn("이전 유입", format="%d"),
        "이번_유입수": st.column_config.NumberColumn("이번 유입", format="%d"),
        "유입_증감률(%)": st.column_config.NumberColumn("유입 증감률", format="%.1f%%"),
        "이전_매출": st.column_config.NumberColumn("이전 매출", format="₩%d"),
        "이번_매출": st.column_config.NumberColumn("이번 매출", format="₩%d"),
        "매출_증감률(%)": st.column_config.NumberColumn("매출 증감률", format="%.1f%%")
    }
)
