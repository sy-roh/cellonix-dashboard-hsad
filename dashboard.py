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
        st.text_input("🔒 비밀번호를 입력하세요.", type="password", on_change=password_entered, key="password")
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
    
    # -----------------------------------------------------
    # 정기구독 시트
    # 실제 구글시트 구조:
    # 날짜 / 요일 / 브랜드 / 신규 구매 / 재 구매 / 정기구독 할인금액
    #
    # 내부에서는 컬럼명의 공백/언더바를 제거해 표준화해서 사용합니다.
    # -----------------------------------------------------
    try:
        df_sub = pd.read_csv(get_csv_url('정기구독'))

        # 혹시 첫 행이 실제 헤더가 아닌 경우 '날짜'가 있는 행을 헤더로 재설정
        raw_cols = [str(c).strip() for c in df_sub.columns]
        if not any(str(c).replace(' ', '') == '날짜' for c in raw_cols):
            mask = df_sub.astype(str).apply(
                lambda x: x.str.contains('날짜', na=False)
            ).any(axis=1)

            if mask.any():
                header_idx = mask.idxmax()
                df_sub.columns = (
                    df_sub.iloc[header_idx]
                    .astype(str)
                    .str.strip()
                    .tolist()
                )
                df_sub = df_sub.iloc[header_idx + 1:].reset_index(drop=True)

        # 컬럼명 표준화:
        # "신규 구매" -> "신규구매"
        # "재 구매" -> "재구매"
        # "정기구독 할인금액" -> "정기구독할인금액"
        def normalize_col_name(col):
            return (
                str(col)
                .strip()
                .replace(' ', '')
                .replace('_', '')
                .replace('\n', '')
            )

        rename_map = {
            c: normalize_col_name(c)
            for c in df_sub.columns
        }
        df_sub = df_sub.rename(columns=rename_map)

        required_cols = [
            '날짜',
            '브랜드',
            '신규구매',
            '재구매',
            '정기구독할인금액'
        ]

        missing_cols = [
            c for c in required_cols
            if c not in df_sub.columns
        ]

        if missing_cols:
            raise ValueError(
                "정기구독 시트에서 필요한 컬럼을 찾지 못했습니다: "
                + ", ".join(missing_cols)
                + " / 현재 컬럼: "
                + ", ".join(map(str, df_sub.columns))
            )

        # 날짜
        df_sub['날짜'] = pd.to_datetime(
            df_sub['날짜'],
            errors='coerce'
        )

        # 브랜드명 공백 제거
        df_sub['브랜드'] = (
            df_sub['브랜드']
            .astype(str)
            .str.strip()
            .str.replace(r'\s+', '', regex=True)
        )

        # 숫자형 변환
        def to_number(series):
            return pd.to_numeric(
                series.astype(str).str.replace(
                    r'[^\d.-]',
                    '',
                    regex=True
                ),
                errors='coerce'
            ).fillna(0)

        df_sub['신규구매_실매출'] = to_number(
            df_sub['신규구매']
        )

        df_sub['재구매_실매출'] = to_number(
            df_sub['재구매']
        )

        df_sub['정기구독_금액'] = to_number(
            df_sub['정기구독할인금액']
        )

        # 공식몰 매출 원액(차감 전):
        # 신규 구매 + 재 구매
        # 실제 KPI에서는 트리어드 정기구독 할인금액을 별도 차감
        df_sub['브랜드_실매출'] = (
            df_sub['신규구매_실매출']
            + df_sub['재구매_실매출']
        )

        # 날짜/브랜드가 없는 행 제거
        df_sub = df_sub[
            df_sub['날짜'].notna()
            & df_sub['브랜드'].ne('')
            & df_sub['브랜드'].ne('nan')
        ].copy()

    except Exception as e:
        st.error(
            "정기구독 시트를 읽지 못했습니다. "
            f"오류: {e}"
        )
        df_sub = pd.DataFrame({
            '날짜': pd.to_datetime([]),
            '브랜드': [],
            '신규구매_실매출': [],
            '재구매_실매출': [],
            '정기구독_금액': [],
            '브랜드_실매출': [],
        })

    # -----------------------------------------------------
    # 브랜드 데이터 생성
    # '셀티아이' / '트리어드' 개별 시트 대신 '전체' 시트에서 생성
    # -----------------------------------------------------
    UNCLASSIFIED_RATIO = {
        '셀티아이': 0.6017037623023724,   # 화면상 60.17%
        '트리어드': 0.30672158945459616, # 화면상 30.67%
        '기타': 0.09157464824303162,      # 화면상 9.16%
    }

    revenue_cols = [
        '신규방문_신규구매_매출액',
        '신규방문_재구매_매출액',
        '재방문_신규구매_매출액',
        '재방문_재구매_매출액',
    ]

    # 매출 컬럼 숫자형 정리
    for col in revenue_cols:
        if col in df_total.columns:
            df_total[col] = pd.to_numeric(
                df_total[col].astype(str).str.replace(',', '', regex=False),
                errors='coerce'
            ).fillna(0)

    # CATEGORY_1 ~ CATEGORY_5 태그 자동 탐색
    expected_category_cols = {f'CATEGORY_{i}' for i in range(1, 6)}
    category_cols = [
        c for c in df_total.columns
        if str(c).strip().upper() in expected_category_cols
    ]

    if not category_cols:
        raise ValueError("전체 시트에서 CATEGORY_1~CATEGORY_5 컬럼을 찾을 수 없습니다.")

    category_text = (
        df_total[category_cols]
        .fillna('')
        .astype(str)
        .agg(' | '.join, axis=1)
    )

    has_cellti = category_text.str.contains('셀티아이', case=False, regex=False)
    has_triad = category_text.str.contains('트리어드', case=False, regex=False)

    # 둘 중 하나만 명확히 태깅된 행만 직접 귀속
    cellti_mask = has_cellti & ~has_triad
    triad_mask = has_triad & ~has_cellti

    # 태그 없음 또는 두 브랜드가 동시에 들어간 행은 미분류
    unclassified_mask = ~(cellti_mask | triad_mask)

    # '기타' 제품이 CATEGORY에 명시되어 있으면 실제 기타로 사용
    explicit_other_mask = category_text.str.contains(
        '기타',
        case=False,
        regex=False
    )

    # 명확한 태그 데이터는 전체 시트에서 그대로 사용
    df_cellti_tagged = df_total[cellti_mask].copy()
    df_cellti_tagged['브랜드'] = '셀티아이'

    df_triad_tagged = df_total[triad_mask].copy()
    df_triad_tagged['브랜드'] = '트리어드'

    df_unclassified = df_total[unclassified_mask].copy()

    # 공식몰 실매출에 사용할 '기타'
    # 1순위: CATEGORY에 '기타'가 명시된 실제 행
    # 2순위: 명시적 기타가 없으면 기존 보정 방식(미분류의 9.16%) 사용
    df_other_explicit = df_total[explicit_other_mask].copy()
    if not df_other_explicit.empty:
        df_other_explicit['브랜드'] = '기타'

    def make_allocated_revenue_rows(source_df, brand_name, ratio):
        """미분류 행은 매출액만 비율 배분하고 기타 지표는 중복 합산하지 않음."""
        allocated = source_df.copy()
        allocated['브랜드'] = brand_name

        # 방문/가입/구매건수 등 숫자 지표는 중복 방지를 위해 0
        numeric_cols = allocated.select_dtypes(include='number').columns.tolist()
        non_revenue_numeric_cols = [c for c in numeric_cols if c not in revenue_cols]
        if non_revenue_numeric_cols:
            allocated[non_revenue_numeric_cols] = 0

        # 매출액만 지정 비율로 자동 배분
        for col in revenue_cols:
            if col in allocated.columns:
                allocated[col] = allocated[col].fillna(0) * ratio

        return allocated

    df_cellti_alloc = make_allocated_revenue_rows(
        df_unclassified, '셀티아이', UNCLASSIFIED_RATIO['셀티아이']
    )
    df_triad_alloc = make_allocated_revenue_rows(
        df_unclassified, '트리어드', UNCLASSIFIED_RATIO['트리어드']
    )
    df_other_alloc = make_allocated_revenue_rows(
        df_unclassified, '기타', UNCLASSIFIED_RATIO['기타']
    )

    # 전체 시트에서 명시적인 '기타' 태그가 있으면 그것을 우선 사용
    df_other = (
        df_other_explicit.copy()
        if not df_other_explicit.empty
        else df_other_alloc.copy()
    )

    df_cellti = pd.concat(
        [df_cellti_tagged, df_cellti_alloc],
        ignore_index=True
    )
    df_triad = pd.concat(
        [df_triad_tagged, df_triad_alloc],
        ignore_index=True
    )

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
    
    df_main = pd.concat([df_total, df_cellti, df_triad, df_other] + influencer_dfs, ignore_index=True)
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

# 전체 + 개별 브랜드 동시 선택 시 원본이 중복 합산되는 것을 방지
effective_brands = ["전체"] if "전체" in selected_brands else selected_brands
df_filtered = df_all[df_all['브랜드'].isin(effective_brands)].copy()

def filter_actual_sales_by_brand(df_sub, brands):
    """
    정기구독 시트 브랜드 필터.
    전체 선택 시 셀티아이 + 트리어드를 사용합니다.
    개별 브랜드 선택 시 해당 브랜드만 사용합니다.
    """
    if df_sub.empty:
        return df_sub.copy()

    if "전체" in brands:
        return df_sub[
            df_sub['브랜드'].isin(['셀티아이', '트리어드'])
        ].copy()

    target_brands = set()

    for b in brands:
        if "셀티아이" in b:
            target_brands.add("셀티아이")

        if "트리어드" in b:
            target_brands.add("트리어드")

    if not target_brands:
        return df_sub.iloc[0:0].copy()

    return df_sub[
        df_sub['브랜드'].isin(target_brands)
    ].copy()


df_sub_filtered = filter_actual_sales_by_brand(
    df_sub_all,
    effective_brands
)

if any("인플루언서" in b for b in effective_brands):
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
df_sub_current = df_sub_filtered[
    (df_sub_filtered['날짜'].dt.date >= start_date)
    & (df_sub_filtered['날짜'].dt.date <= end_date)
]

duration = (end_date - start_date).days + 1
prev_start_date = start_date - timedelta(days=duration)
prev_end_date = start_date - timedelta(days=1)
df_prev = df_filtered[(df_filtered['날짜'].dt.date >= prev_start_date) & (df_filtered['날짜'].dt.date <= prev_end_date)]
df_sub_prev = df_sub_filtered[
    (df_sub_filtered['날짜'].dt.date >= prev_start_date)
    & (df_sub_filtered['날짜'].dt.date <= prev_end_date)
]

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
# 매출 지표
#
# 1) 공식몰 실매출
#    = 정기구독 시트의 셀티아이 + 트리어드
#      (신규 구매 + 재 구매)
#
# 2) 로그 신규 매출
#    = 전체 시트 신규방문 구매 매출
#
# 3) 로그 재방문 매출
#    = 전체 시트 재방문 구매 매출
#
# 4) 정기구독
#    = 정기구독 시트의 트리어드 '정기구독 할인금액'
# ---------------------------------------------------------

# -------------------------
# 로그 기준 신규 / 재방문
# -------------------------
cur_log_new_rev = (
    df_current['신규방문_신규구매_매출액'].sum()
    + df_current['신규방문_재구매_매출액'].sum()
)

cur_log_return_rev = (
    df_current['재방문_신규구매_매출액'].sum()
    + df_current['재방문_재구매_매출액'].sum()
)

prev_log_new_rev = (
    df_prev['신규방문_신규구매_매출액'].sum()
    + df_prev['신규방문_재구매_매출액'].sum()
)

prev_log_return_rev = (
    df_prev['재방문_신규구매_매출액'].sum()
    + df_prev['재방문_재구매_매출액'].sum()
)

# 로그 매출 합계
cur_log_total_rev = (
    cur_log_new_rev
    + cur_log_return_rev
)

prev_log_total_rev = (
    prev_log_new_rev
    + prev_log_return_rev
)

# -------------------------
# 공식몰 실매출 + 정기구독
# 정기구독 시트 기준
#
# 공식몰 실매출은 '정기구독 할인금액'을 제외한 순매출로 계산
# - 전체: (셀티아이 + 트리어드 신규구매/재구매) - 트리어드 정기구독
# - 트리어드: 트리어드 신규구매/재구매 - 트리어드 정기구독
# - 셀티아이: 셀티아이 신규구매/재구매 (차감 없음)
# -------------------------
if "전체" in effective_brands:
    official_target_brands = ['셀티아이', '트리어드']
else:
    official_target_brands = []

    for b in effective_brands:
        if "셀티아이" in b and "셀티아이" not in official_target_brands:
            official_target_brands.append("셀티아이")

        if "트리어드" in b and "트리어드" not in official_target_brands:
            official_target_brands.append("트리어드")

# 정기구독은 트리어드가 선택 범위에 포함될 때만 차감/표시
show_triad_subscription = (
    "전체" in effective_brands
    or any("트리어드" in b for b in effective_brands)
)

if show_triad_subscription:
    cur_subscription_log = df_sub_current[
        df_sub_current['브랜드'] == '트리어드'
    ]['정기구독_금액'].sum()

    prev_subscription_log = df_sub_prev[
        df_sub_prev['브랜드'] == '트리어드'
    ]['정기구독_금액'].sum()
else:
    cur_subscription_log = 0
    prev_subscription_log = 0

# 차감 전 공식몰 매출
cur_official_gross = df_sub_current[
    df_sub_current['브랜드'].isin(official_target_brands)
]['브랜드_실매출'].sum()

prev_official_gross = df_sub_prev[
    df_sub_prev['브랜드'].isin(official_target_brands)
]['브랜드_실매출'].sum()

# 최종 공식몰 실매출 = 차감 전 매출 - 트리어드 정기구독 할인금액
cur_official_actual = (
    cur_official_gross
    - cur_subscription_log
)

prev_official_actual = (
    prev_official_gross
    - prev_subscription_log
)

st.markdown("#### 💰 매출 요약")

st.caption(
    "※ 공식몰 실매출은 정기구독 시트의 셀티아이·트리어드 "
    "'신규 구매 + 재 구매'에서 트리어드 '정기구독 할인금액'을 제외한 순매출입니다. "
    "로그 매출 합계는 전체 시트의 로그 신규 매출 + 로그 재방문 매출이며, "
    "정기구독은 트리어드의 '정기구독 할인금액'입니다."
)

# KPI 5개 + 그룹 구분선
# 공식몰 실매출 │ 로그 매출 합계 / 신규 / 재방문 │ 정기구독
m1, sep1, m2, m3, m4, sep2, m5 = st.columns(
    [1.25, 0.06, 1.15, 1.15, 1.15, 0.06, 1.15]
)

m1.metric(
    "🔥 공식몰 실매출",
    format_currency(cur_official_actual),
    delta=calculate_delta(
        cur_official_actual,
        prev_official_actual
    ),
    help=(
        "정기구독 시트 기준: "
        "셀티아이 + 트리어드의 신규 구매 + 재 구매 "
        "- 트리어드 정기구독 할인금액"
    )
)

with sep1:
    st.markdown(
        "<div style='border-left:1px solid #D9D9D9;height:92px;margin:6px auto 0 auto;width:1px;'></div>",
        unsafe_allow_html=True
    )

m2.metric(
    "📊 로그 매출 합계",
    format_currency(cur_log_total_rev),
    delta=calculate_delta(
        cur_log_total_rev,
        prev_log_total_rev
    ),
    help="전체 시트 기준: 로그 신규 매출 + 로그 재방문 매출"
)

m3.metric(
    "✨ 로그 신규 매출",
    format_currency(cur_log_new_rev),
    delta=calculate_delta(
        cur_log_new_rev,
        prev_log_new_rev
    ),
    help="전체 시트의 신규방문 구매 매출"
)

m4.metric(
    "🤝 로그 재방문 매출",
    format_currency(cur_log_return_rev),
    delta=calculate_delta(
        cur_log_return_rev,
        prev_log_return_rev
    ),
    help="전체 시트의 재방문 구매 매출"
)

with sep2:
    st.markdown(
        "<div style='border-left:1px solid #D9D9D9;height:92px;margin:6px auto 0 auto;width:1px;'></div>",
        unsafe_allow_html=True
    )

m5.metric(
    "🔄 정기구독",
    format_currency(cur_subscription_log),
    delta=calculate_delta(
        cur_subscription_log,
        prev_subscription_log
    ),
    help=(
        "정기구독 시트의 트리어드 "
        "'정기구독 할인금액' 합계"
    )
)

st.markdown("---")

# ---------------------------------------------------------
# 차트 및 타임라인 (유입/구매 추이)
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
# 고객 여정 퍼널 (호버 시 증감수치 노출)
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
funnel_new['증감량'] = funnel_new['수치'] - funnel_new['이전']
funnel_new['증감텍스트'] = funnel_new['증감량'].apply(lambda x: f"▲ {int(x):,}" if x > 0 else (f"▼ {int(abs(x)):,}" if x < 0 else "-"))

fig_fnew = px.funnel(funnel_new, x='수치', y='단계', title="신규방문 퍼널", color_discrete_sequence=['#82B1FF'], custom_data=['증감텍스트'])
fig_fnew.update_traces(textinfo="value+percent initial", hovertemplate="<b>%{y}</b><br>수치: %{x:,}<br>전기간 대비: %{customdata[0]}<extra></extra>") 
fig_fnew.update_layout(template="plotly_white", margin=dict(t=30, b=0), height=300)
col_funnel1.plotly_chart(fig_fnew, use_container_width=True)

funnel_ret = pd.DataFrame({
    '단계': ['1. 방문', '2. 관심', '3. 가입', '4. 구매시도', '5. 최종구매'], 
    '수치': [df_current['재방문_총 방문수'].sum(), df_current['재방문_관심행동1'].sum(), df_current['재방문_회원가입'].sum(), df_current['재방문_구매시도'].sum(), cur_ret_buy],
    '이전': [df_prev['재방문_총 방문수'].sum(), df_prev['재방문_관심행동1'].sum(), df_prev['재방문_회원가입'].sum(), df_prev['재방문_구매시도'].sum(), prev_ret_buy]
})
funnel_ret['증감량'] = funnel_ret['수치'] - funnel_ret['이전']
funnel_ret['증감텍스트'] = funnel_ret['증감량'].apply(lambda x: f"▲ {int(x):,}" if x > 0 else (f"▼ {int(abs(x)):,}" if x < 0 else "-"))

fig_fret = px.funnel(funnel_ret, x='수치', y='단계', title="재방문 퍼널", color_discrete_sequence=['#304FFE'], custom_data=['증감텍스트'])
fig_fret.update_traces(textinfo="value+percent initial", hovertemplate="<b>%{y}</b><br>수치: %{x:,}<br>전기간 대비: %{customdata[0]}<extra></extra>")
fig_fret.update_layout(template="plotly_white", margin=dict(t=30, b=0), height=300)
col_funnel2.plotly_chart(fig_fret, use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------
# 주요 매체 Top 5 (매체코드 기준 귀속매출 포함)
# ---------------------------------------------------------
st.markdown("#### 🏆 주요 매체 Top 5")
col_top1, col_top2, col_top3 = st.columns(3)

top_visit_cur = df_current.groupby('매체')['총방문수'].sum().reset_index()
top_visit_prev = df_prev.groupby('매체')['총방문수'].sum().reset_index().rename(columns={'총방문수':'이전'})
top_visit = pd.merge(top_visit_cur, top_visit_prev, on='매체', how='left').fillna(0)
top_visit['증감량'] = top_visit['총방문수'] - top_visit['이전']
top_visit['증감텍스트'] = top_visit['증감량'].apply(lambda x: f"▲ {int(x):,}" if x > 0 else (f"▼ {int(abs(x)):,}" if x < 0 else "-"))
top_visit = top_visit.sort_values(by='총방문수', ascending=False).head(5)

fig_top_visit = px.bar(top_visit, x='총방문수', y='매체', orientation='h', title='1. 유입 기준', text_auto='.2s', color_discrete_sequence=['#B39DDB'], custom_data=['증감텍스트'])
fig_top_visit.update_traces(hovertemplate="<b>%{y}</b><br>유입수: %{x:,}<br>전기간 대비: %{customdata[0]}<extra></extra>")
fig_top_visit.update_layout(template="plotly_white", yaxis={'categoryorder':'total ascending'}, margin=dict(t=30, l=0, r=0, b=0), height=250) 
col_top1.plotly_chart(fig_top_visit, use_container_width=True)

top_signup_cur = df_current.groupby('매체')['총회원가입'].sum().reset_index()
top_signup_prev = df_prev.groupby('매체')['총회원가입'].sum().reset_index().rename(columns={'총회원가입':'이전'})
top_signup = pd.merge(top_signup_cur, top_signup_prev, on='매체', how='left').fillna(0)
top_signup['증감량'] = top_signup['총회원가입'] - top_signup['이전']
top_signup['증감텍스트'] = top_signup['증감량'].apply(lambda x: f"▲ {int(x):,}" if x > 0 else (f"▼ {int(abs(x)):,}" if x < 0 else "-"))
top_signup = top_signup.sort_values(by='총회원가입', ascending=False).head(5)

fig_top_signup = px.bar(top_signup, x='총회원가입', y='매체', orientation='h', title='2. 가입 기준', text_auto='.0f', color_discrete_sequence=['#4DD0E1'], custom_data=['증감텍스트'])
fig_top_signup.update_traces(hovertemplate="<b>%{y}</b><br>가입수: %{x:,}<br>전기간 대비: %{customdata[0]}<extra></extra>")
fig_top_signup.update_layout(template="plotly_white", yaxis={'categoryorder':'total ascending'}, margin=dict(t=30, l=0, r=0, b=0), height=250)
col_top2.plotly_chart(fig_top_signup, use_container_width=True)

top_sales_cur = (
    df_current.groupby('매체')['총매출액']
    .sum()
    .reset_index()
)
top_sales_prev = (
    df_prev.groupby('매체')['총매출액']
    .sum()
    .reset_index()
    .rename(columns={'총매출액': '이전'})
)
top_sales = pd.merge(
    top_sales_cur,
    top_sales_prev,
    on='매체',
    how='left'
).fillna(0)

top_sales['증감량'] = (
    top_sales['총매출액'] - top_sales['이전']
)
top_sales['증감텍스트'] = top_sales['증감량'].apply(
    lambda x: (
        f"▲ ₩{int(x):,}" if x > 0
        else (
            f"▼ ₩{int(abs(x)):,}" if x < 0
            else "-"
        )
    )
)
top_sales = (
    top_sales
    .sort_values(by='총매출액', ascending=False)
    .head(5)
)

fig_top_sales = px.bar(
    top_sales,
    x='총매출액',
    y='매체',
    orientation='h',
    title='3. 매체 귀속 매출 기준',
    text_auto='.2s',
    color_discrete_sequence=['#F48FB1'],
    custom_data=['증감텍스트']
)
fig_top_sales.update_traces(
    hovertemplate=(
        "<b>%{y}</b><br>"
        "귀속 매출: ₩%{x:,.0f}<br>"
        "전기간 대비: %{customdata[0]}"
        "<extra></extra>"
    )
)
fig_top_sales.update_layout(
    template="plotly_white",
    yaxis={'categoryorder': 'total ascending'},
    margin=dict(t=30, l=0, r=0, b=0),
    height=250
)
col_top3.plotly_chart(
    fig_top_sales,
    use_container_width=True
)

st.markdown("---")

# ---------------------------------------------------------
# 매체별 점유율 (유입 / 귀속매출)
# ---------------------------------------------------------
st.markdown("#### 🎯 매체별 점유율 (유입 및 귀속 매출)")
df_media_eff = (
    df_current.groupby('매체')[
        ['총방문수', '총구매수', '총매출액']
    ]
    .sum()
    .reset_index()
    .sort_values('총방문수', ascending=False)
)
col_pie1, col_pie2 = st.columns(2)

with col_pie1:
    fig_pie_visit = px.pie(
        df_media_eff,
        values='총방문수',
        names='매체',
        hole=0.4,
        title='유입 점유율 (트래픽 비중)',
        color_discrete_sequence=px.colors.sequential.Teal
    )
    fig_pie_visit.update_traces(
        textposition='inside',
        textinfo='percent+label',
        showlegend=False
    )
    fig_pie_visit.update_layout(
        template="plotly_white",
        margin=dict(t=40, b=0, l=0, r=0),
        height=350
    )
    st.plotly_chart(
        fig_pie_visit,
        use_container_width=True
    )

with col_pie2:
    fig_pie_sales = px.pie(
        df_media_eff,
        values='총매출액',
        names='매체',
        hole=0.4,
        title='매체 귀속 매출 점유율',
        color_discrete_sequence=px.colors.sequential.OrRd
    )
    fig_pie_sales.update_traces(
        textposition='inside',
        textinfo='percent+label',
        showlegend=False,
        hovertemplate=(
            "<b>%{label}</b><br>"
            "귀속 매출: ₩%{value:,.0f}<br>"
            "비중: %{percent}"
            "<extra></extra>"
        )
    )
    fig_pie_sales.update_layout(
        template="plotly_white",
        margin=dict(t=40, b=0, l=0, r=0),
        height=350
    )
    st.plotly_chart(
        fig_pie_sales,
        use_container_width=True
    )

st.markdown("---")

# ---------------------------------------------------------
# 매체별 증감 추이 및 전체 현황표
# ---------------------------------------------------------
st.markdown("#### 🔄 비교 기간 대비 매체 운영 현황")
st.caption("※ 설정된 기간과 직전 동일 기간을 비교합니다.")

df_curr_media = (
    df_current.groupby('매체')[
        ['총방문수', '총매출액']
    ]
    .sum()
    .reset_index()
    .rename(columns={
        '총방문수': '이번_유입수',
        '총매출액': '이번_귀속매출'
    })
)

df_prev_media = (
    df_prev.groupby('매체')[
        ['총방문수', '총매출액']
    ]
    .sum()
    .reset_index()
    .rename(columns={
        '총방문수': '이전_유입수',
        '총매출액': '이전_귀속매출'
    })
)

df_compare = pd.merge(
    df_prev_media,
    df_curr_media,
    on='매체',
    how='outer'
).fillna(0)


def get_media_status(row):
    if (
        row['이전_유입수'] == 0
        and row['이번_유입수'] > 0
    ):
        return "🆕 신규 진입"
    elif (
        row['이전_유입수'] > 0
        and row['이번_유입수'] == 0
    ):
        return "⏸️ 운영 중단"
    elif row['이번_유입수'] > row['이전_유입수']:
        return "🔼 유입 증가"
    elif row['이번_유입수'] < row['이전_유입수']:
        return "🔽 유입 감소"
    else:
        return "▶️ 유지"


df_compare['상태'] = df_compare.apply(
    get_media_status,
    axis=1
)

df_compare['유입_증감량'] = (
    df_compare['이번_유입수']
    - df_compare['이전_유입수']
)

df_compare['유입_증감률(%)'] = df_compare.apply(
    lambda r: (
        (
            r['이번_유입수']
            - r['이전_유입수']
        )
        / r['이전_유입수']
        * 100
    )
    if r['이전_유입수'] != 0
    else 0,
    axis=1
)

df_compare['매출_증감량'] = (
    df_compare['이번_귀속매출']
    - df_compare['이전_귀속매출']
)

df_compare['매출_증감률(%)'] = df_compare.apply(
    lambda r: (
        (
            r['이번_귀속매출']
            - r['이전_귀속매출']
        )
        / r['이전_귀속매출']
        * 100
    )
    if r['이전_귀속매출'] != 0
    else 0,
    axis=1
)

df_compare = df_compare[
    [
        '상태',
        '매체',
        '이전_유입수',
        '이번_유입수',
        '유입_증감률(%)',
        '이전_귀속매출',
        '이번_귀속매출',
        '매출_증감률(%)'
    ]
].sort_values(
    by='이번_귀속매출',
    ascending=False
)

st.dataframe(
    df_compare,
    use_container_width=True,
    hide_index=True,
    column_config={
        "상태": st.column_config.TextColumn(
            "상태",
            width="medium"
        ),
        "매체": st.column_config.TextColumn(
            "매체명",
            width="medium"
        ),
        "이전_유입수": st.column_config.NumberColumn(
            "이전 유입",
            format="%d"
        ),
        "이번_유입수": st.column_config.NumberColumn(
            "이번 유입",
            format="%d"
        ),
        "유입_증감률(%)": st.column_config.NumberColumn(
            "유입 증감률",
            format="%.1f%%"
        ),
        "이전_귀속매출": st.column_config.NumberColumn(
            "이전 귀속매출",
            format="₩%d"
        ),
        "이번_귀속매출": st.column_config.NumberColumn(
            "이번 귀속매출",
            format="₩%d"
        ),
        "매출_증감률(%)": st.column_config.NumberColumn(
            "매출 증감률",
            format="%.1f%%"
        ),
    }
)
