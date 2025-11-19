import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import folium
from streamlit_folium import st_folium

# 페이지 설정
st.set_page_config(
    page_title="아파트 vs 오피스텔 가격 비교",
    page_icon="🏢",
    layout="wide"
)

# API 키
API_KEY = "2b4480410a199ed715b0bb4f8c6efa36ad6e4dc3d0858545737b5aaa53b02be6"

# 올바른 API 엔드포인트
APT_API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
OFFICETEL_API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade"

# 서울시 지역코드
REGION_CODES = {
    "종로구": "11110",
    "중구": "11140",
    "용산구": "11170",
    "성동구": "11200",
    "광진구": "11215",
    "동대문구": "11230",
    "중랑구": "11260",
    "성북구": "11290",
    "강북구": "11305",
    "도봉구": "11320",
    "노원구": "11350",
    "은평구": "11380",
    "서대문구": "11410",
    "마포구": "11440",
    "양천구": "11470",
    "강서구": "11500",
    "구로구": "11530",
    "금천구": "11545",
    "영등포구": "11560",
    "동작구": "11590",
    "관악구": "11620",
    "서초구": "11650",
    "강남구": "11680",
    "송파구": "11710",
    "강동구": "11740"
}

# 지역별 중심 좌표
REGION_COORDS = {
    "종로구": [37.5735, 126.9792],
    "중구": [37.5641, 126.9979],
    "용산구": [37.5326, 126.9909],
    "성동구": [37.5634, 127.0368],
    "광진구": [37.5388, 127.0824],
    "동대문구": [37.5744, 127.0400],
    "중랑구": [37.6063, 127.0926],
    "성북구": [37.5894, 127.0167],
    "강북구": [37.6398, 127.0256],
    "도봉구": [37.6688, 127.0471],
    "노원구": [37.6543, 127.0568],
    "은평구": [37.6176, 126.9227],
    "서대문구": [37.5791, 126.9368],
    "마포구": [37.5663, 126.9019],
    "양천구": [37.5170, 126.8664],
    "강서구": [37.5509, 126.8495],
    "구로구": [37.4955, 126.8874],
    "금천구": [37.4563, 126.8956],
    "영등포구": [37.5264, 126.8962],
    "동작구": [37.5124, 126.9393],
    "관악구": [37.4784, 126.9516],
    "서초구": [37.4837, 127.0324],
    "강남구": [37.5172, 127.0473],
    "송파구": [37.5145, 127.1059],
    "강동구": [37.5301, 127.1238]
}


def get_real_estate_data(api_url, lawd_cd, deal_ymd):
    """실거래 데이터 API 호출"""
    params = {
        'serviceKey': API_KEY,
        'LAWD_CD': lawd_cd,
        'DEAL_YMD': deal_ymd,
        'numOfRows': 1000
    }
    
    try:
        response = requests.get(api_url, params=params, timeout=10)
        
        if response.status_code == 500:
            return None
        
        response.raise_for_status()
        
        import xml.etree.ElementTree as ET
        root = ET.fromstring(response.content)
        
        result_code = root.find('.//resultCode')
        
        if result_code is not None:
            code = result_code.text
            if code not in ['00', '000']:
                return None
        
        items = []
        for item in root.findall('.//item'):
            data = {}
            for child in item:
                data[child.tag] = child.text
            items.append(data)
        
        if items:
            return pd.DataFrame(items)
        else:
            return None
            
    except Exception as e:
        return None


def preprocess_data(df, property_type):
    """데이터 전처리"""
    if df is None or df.empty:
        return None
    
    df = df.copy()
    
    # 거래금액 처리
    if 'dealAmount' in df.columns:
        df['거래금액'] = df['dealAmount'].str.replace(',', '').str.replace(' ', '').str.strip()
        df['거래금액'] = pd.to_numeric(df['거래금액'], errors='coerce')
    else:
        return None
    
    # 전용면적 처리
    if 'excluUseAr' in df.columns:
        df['전용면적'] = pd.to_numeric(df['excluUseAr'], errors='coerce')
    else:
        return None
    
    # 평수 계산
    df['평수'] = (df['전용면적'] / 3.3058).round(1)
    
    # 평당가 계산
    df['평당가'] = (df['거래금액'] / df['평수']).round(0)
    
    # 거래일자
    if all(col in df.columns for col in ['dealYear', 'dealMonth', 'dealDay']):
        df['거래일자'] = pd.to_datetime(
            df['dealYear'] + '-' + 
            df['dealMonth'].str.zfill(2) + '-' + 
            df['dealDay'].str.zfill(2),
            errors='coerce'
        )
    
    # 필드명 통일
    if property_type == '아파트':
        if 'aptNm' in df.columns:
            df['아파트'] = df['aptNm']
        if 'sggNm' in df.columns:
            df['시군구'] = df['sggNm']
        if 'umdNm' in df.columns:
            df['법정동'] = df['umdNm']
    
    elif property_type == '오피스텔':
        if 'offiNm' in df.columns:
            df['오피스텔'] = df['offiNm']
            df['단지'] = df['offiNm']
        if 'sggNm' in df.columns:
            df['시군구'] = df['sggNm']
        if 'umdNm' in df.columns:
            df['법정동'] = df['umdNm']
    
    if 'floor' in df.columns:
        df['층'] = df['floor']
    if 'buildYear' in df.columns:
        df['건축년도'] = df['buildYear']
    
    df['유형'] = property_type
    
    # 면적대 분류
    df['면적대'] = pd.cut(
        df['전용면적'],
        bins=[0, 60, 85, 120, 200],
        labels=['소형(~60㎡)', '중형(60~85㎡)', '대형(85~120㎡)', '초대형(120㎡~)']
    )
    
    # 결측치 제거
    df = df.dropna(subset=['거래금액', '평당가', '전용면적'])
    
    if len(df) == 0:
        return None
    
    return df


def create_map(apt_df, office_df, region_name):
    """지도 생성"""
    center = REGION_COORDS.get(region_name, [37.5665, 126.9780])
    m = folium.Map(location=center, zoom_start=13)
    
    # 아파트 마커 (파란색)
    if apt_df is not None and not apt_df.empty:
        for idx, row in apt_df.head(100).iterrows():
            # 좌표가 없으므로 랜덤하게 분산 (실제로는 Geocoding API 필요)
            import random
            lat = center[0] + random.uniform(-0.02, 0.02)
            lng = center[1] + random.uniform(-0.02, 0.02)
            
            popup_text = f"""
            <b>{row.get('아파트', 'N/A')}</b><br>
            📍 {row.get('법정동', 'N/A')}<br>
            💰 {row.get('거래금액', 0):,.0f}만원<br>
            📐 {row.get('평수', 0):.1f}평<br>
            💎 평당 {row.get('평당가', 0):,.0f}만원
            """
            
            folium.Marker(
                location=[lat, lng],
                popup=folium.Popup(popup_text, max_width=200),
                icon=folium.Icon(color='blue', icon='home', prefix='fa')
            ).add_to(m)
    
    # 오피스텔 마커 (빨간색)
    if office_df is not None and not office_df.empty:
        for idx, row in office_df.head(100).iterrows():
            import random
            lat = center[0] + random.uniform(-0.02, 0.02)
            lng = center[1] + random.uniform(-0.02, 0.02)
            
            popup_text = f"""
            <b>{row.get('단지', 'N/A')}</b><br>
            📍 {row.get('법정동', 'N/A')}<br>
            💰 {row.get('거래금액', 0):,.0f}만원<br>
            📐 {row.get('평수', 0):.1f}평<br>
            💎 평당 {row.get('평당가', 0):,.0f}만원
            """
            
            folium.Marker(
                location=[lat, lng],
                popup=folium.Popup(popup_text, max_width=200),
                icon=folium.Icon(color='red', icon='building', prefix='fa')
            ).add_to(m)
    
    return m


def generate_insights(apt_df, office_df):
    """인사이트 생성"""
    insights = []
    
    if apt_df is not None and office_df is not None:
        apt_avg = apt_df['평당가'].mean()
        office_avg = office_df['평당가'].mean()
        diff = apt_avg - office_avg
        diff_pct = (diff / apt_avg * 100)
        
        if diff > 0:
            insights.append(f"💡 아파트가 평당 **{diff:,.0f}만원** ({diff_pct:.1f}%) 더 비쌉니다.")
        else:
            insights.append(f"💡 오피스텔이 평당 **{abs(diff):,.0f}만원** ({abs(diff_pct):.1f}%) 더 비쌉니다.")
        
        apt_count = len(apt_df)
        office_count = len(office_df)
        insights.append(f"📊 거래량: 아파트 **{apt_count}건**, 오피스텔 **{office_count}건**")
        
        apt_max = apt_df['평당가'].max()
        office_max = office_df['평당가'].max()
        insights.append(f"🏆 최고 평당가: 아파트 **{apt_max:,.0f}만원**, 오피스텔 **{office_max:,.0f}만원**")
    
    return insights


def create_comparison_chart(apt_df, office_df):
    """평당가 분포 비교"""
    fig = go.Figure()
    
    if apt_df is not None and not apt_df.empty:
        fig.add_trace(go.Box(
            y=apt_df['평당가'],
            name='아파트',
            marker_color='#4A90E2',
            boxmean='sd'
        ))
    
    if office_df is not None and not office_df.empty:
        fig.add_trace(go.Box(
            y=office_df['평당가'],
            name='오피스텔',
            marker_color='#E94B3C',
            boxmean='sd'
        ))
    
    fig.update_layout(
        title='평당가 분포 비교',
        yaxis_title='평당가 (만원)',
        height=400,
        showlegend=True,
        template='plotly_white'
    )
    
    return fig


def create_trend_chart(apt_df, office_df):
    """시간별 트렌드"""
    fig = go.Figure()
    
    if apt_df is not None and '거래일자' in apt_df.columns:
        apt_trend = apt_df.groupby('거래일자')['평당가'].mean().reset_index()
        fig.add_trace(go.Scatter(
            x=apt_trend['거래일자'],
            y=apt_trend['평당가'],
            mode='lines+markers',
            name='아파트',
            line=dict(color='#4A90E2', width=3)
        ))
    
    if office_df is not None and '거래일자' in office_df.columns:
        office_trend = office_df.groupby('거래일자')['평당가'].mean().reset_index()
        fig.add_trace(go.Scatter(
            x=office_trend['거래일자'],
            y=office_trend['평당가'],
            mode='lines+markers',
            name='오피스텔',
            line=dict(color='#E94B3C', width=3)
        ))
    
    fig.update_layout(
        title='평당가 추이',
        xaxis_title='거래일자',
        yaxis_title='평균 평당가 (만원)',
        height=400,
        hovermode='x unified',
        template='plotly_white'
    )
    
    return fig


def create_area_comparison(apt_df, office_df):
    """면적대별 비교"""
    fig = go.Figure()
    
    if apt_df is not None and '면적대' in apt_df.columns:
        apt_area = apt_df.groupby('면적대')['평당가'].mean().reset_index()
        fig.add_trace(go.Bar(
            x=apt_area['면적대'],
            y=apt_area['평당가'],
            name='아파트',
            marker_color='#4A90E2'
        ))
    
    if office_df is not None and '면적대' in office_df.columns:
        office_area = office_df.groupby('면적대')['평당가'].mean().reset_index()
        fig.add_trace(go.Bar(
            x=office_area['면적대'],
            y=office_area['평당가'],
            name='오피스텔',
            marker_color='#E94B3C'
        ))
    
    fig.update_layout(
        title='면적대별 평당가 비교',
        xaxis_title='면적대',
        yaxis_title='평균 평당가 (만원)',
        height=400,
        barmode='group',
        template='plotly_white'
    )
    
    return fig


def main():
    # 헤더
    st.title("🏢 아파트 vs 오피스텔 매매가 비교")
    st.markdown("**실거래가 기반 데이터 분석 대시보드** | 국토교통부 공공데이터 활용")
    st.markdown("---")
    
    # 사이드바
    with st.sidebar:
        st.header("🔍 검색 조건")
        
        # 지역 선택
        selected_region = st.selectbox(
            "서울시 자치구 선택",
            options=list(REGION_CODES.keys()),
            index=22
        )
        lawd_cd = REGION_CODES[selected_region]
        
        # 기간 선택
        period = st.selectbox(
            "조회 기간",
            ["최근 1개월", "최근 3개월", "최근 6개월"],
            index=1
        )
        
        st.markdown("---")
        st.markdown("### 📏 면적 필터 (평)")
        
        col1, col2 = st.columns(2)
        with col1:
            min_pyeong = st.number_input(
                "최소 평수",
                min_value=0,
                max_value=100,
                value=0,
                step=5
            )
        with col2:
            max_pyeong = st.number_input(
                "최대 평수",
                min_value=0,
                max_value=100,
                value=100,
                step=5
            )
        
        st.markdown("---")
        st.markdown("### 💰 예산 필터")
        
        use_budget = st.checkbox("예산 필터 사용")
        
        if use_budget:
            max_budget = st.number_input(
                "최대 예산 (만원)",
                min_value=0,
                max_value=500000,
                value=100000,
                step=10000,
                format="%d"
            )
            st.caption(f"💡 **{max_budget:,}만원** 이하만 표시")
        
        st.markdown("---")
        
        # 검색 버튼
        search_button = st.button("🔍 데이터 조회", type="primary", use_container_width=True)
        
        st.markdown("---")
        st.caption("💡 **Tip**: 데이터 조회에 약 20~30초 소요됩니다.")
    
    # 데이터 조회
    if search_button:
        month_map = {"최근 1개월": 1, "최근 3개월": 3, "최근 6개월": 6}
        months = month_map[period]
        
        deal_dates = []
        current_date = datetime.now()
        for i in range(1, months + 1):
            date = current_date - timedelta(days=30*i)
            deal_dates.append(date.strftime("%Y%m"))
        
        deal_dates = sorted(list(set(deal_dates)), reverse=True)
        
        with st.spinner(f"🔄 **{selected_region}** 데이터를 불러오는 중..."):
            apt_dfs = []
            office_dfs = []
            
            progress_bar = st.progress(0)
            total_steps = len(deal_dates) * 2
            current_step = 0
            
            for deal_ymd in deal_dates:
                apt_data = get_real_estate_data(APT_API_URL, lawd_cd, deal_ymd)
                if apt_data is not None and not apt_data.empty:
                    apt_dfs.append(apt_data)
                current_step += 1
                progress_bar.progress(current_step / total_steps)
                time.sleep(0.5)
                
                office_data = get_real_estate_data(OFFICETEL_API_URL, lawd_cd, deal_ymd)
                if office_data is not None and not office_data.empty:
                    office_dfs.append(office_data)
                current_step += 1
                progress_bar.progress(current_step / total_steps)
                time.sleep(0.5)
            
            progress_bar.empty()
            
            # 데이터 결합 및 전처리
            apt_df = pd.concat(apt_dfs, ignore_index=True) if apt_dfs else None
            office_df = pd.concat(office_dfs, ignore_index=True) if office_dfs else None
            
            apt_df = preprocess_data(apt_df, '아파트')
            office_df = preprocess_data(office_df, '오피스텔')
            
            # ===== 필터 적용 =====
            if apt_df is not None:
                # 평수 필터
                apt_df = apt_df[(apt_df['평수'] >= min_pyeong) & (apt_df['평수'] <= max_pyeong)]
                
                # 예산 필터
                if use_budget:
                    apt_df = apt_df[apt_df['거래금액'] <= max_budget]
            
            if office_df is not None:
                # 평수 필터
                office_df = office_df[(office_df['평수'] >= min_pyeong) & (office_df['평수'] <= max_pyeong)]
                
                # 예산 필터
                if use_budget:
                    office_df = office_df[office_df['거래금액'] <= max_budget]
            
            # 빈 DataFrame 체크
            if apt_df is not None and apt_df.empty:
                apt_df = None
            if office_df is not None and office_df.empty:
                office_df = None
            
            # 세션에 저장
            st.session_state['apt_df'] = apt_df
            st.session_state['office_df'] = office_df
            st.session_state['region_name'] = selected_region
            
            if apt_df is not None or office_df is not None:
                total = (len(apt_df) if apt_df is not None else 0) + (len(office_df) if office_df is not None else 0)
                st.success(f"✅ 데이터 조회 완료! (총 {total}건)")
            else:
                st.warning("⚠️ 필터 조건에 맞는 데이터가 없습니다. 필터를 조정해주세요.")
    
    # 결과 표시
    if 'apt_df' in st.session_state or 'office_df' in st.session_state:
        apt_df = st.session_state.get('apt_df')
        office_df = st.session_state.get('office_df')
        region_name = st.session_state.get('region_name', '선택한 지역')
        
        if (apt_df is None or apt_df.empty) and (office_df is None or office_df.empty):
            st.error("❌ 표시할 데이터가 없습니다. 필터를 조정해주세요.")
        else:
            # 인사이트
            st.markdown(f"## 📊 {region_name} 분석 결과")
            insights = generate_insights(apt_df, office_df)
            for insight in insights:
                st.info(insight)
            
            st.markdown("---")
            
            # 요약 통계
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if apt_df is not None:
                    st.metric("🏠 아파트 평균", f"{apt_df['평당가'].mean():,.0f}만원")
                else:
                    st.metric("🏠 아파트 평균", "데이터 없음")
            
            with col2:
                if office_df is not None:
                    st.metric("🏢 오피스텔 평균", f"{office_df['평당가'].mean():,.0f}만원")
                else:
                    st.metric("🏢 오피스텔 평균", "데이터 없음")
            
            with col3:
                if apt_df is not None and office_df is not None:
                    diff = apt_df['평당가'].mean() - office_df['평당가'].mean()
                    st.metric("💰 가격 차이", f"{abs(diff):,.0f}만원")
                else:
                    st.metric("💰 가격 차이", "비교 불가")
            
            with col4:
                total_count = 0
                if apt_df is not None:
                    total_count += len(apt_df)
                if office_df is not None:
                    total_count += len(office_df)
                st.metric("📈 총 거래 건수", f"{total_count:,}건")
            
            st.markdown("---")
            
            # 차트
            tab1, tab2, tab3, tab4 = st.tabs(["📊 가격 분포", "📈 트렌드 분석", "📏 면적대별 비교", "🗺️ 지도 보기"])
            
            with tab1:
                st.plotly_chart(create_comparison_chart(apt_df, office_df), use_container_width=True, key="chart1")
            
            with tab2:
                st.plotly_chart(create_trend_chart(apt_df, office_df), use_container_width=True, key="chart2")
            
            with tab3:
                st.plotly_chart(create_area_comparison(apt_df, office_df), use_container_width=True, key="chart3")
            
            with tab4:
                st.markdown("### 📍 실거래 위치 지도")
                st.info("💡 파란색 🏠 = 아파트 | 빨간색 🏢 = 오피스텔 (좌표는 랜덤 분산, 실제 위치 아님)")
                real_estate_map = create_map(apt_df, office_df, region_name)
                st_folium(real_estate_map, width=1400, height=600, key="map1")
            
            st.markdown("---")
            
            # 가성비 TOP 5
            st.markdown("## 💎 가성비 TOP 5")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 🏠 아파트")
                if apt_df is not None and not apt_df.empty and '아파트' in apt_df.columns:
                    best_apt = apt_df.nsmallest(5, '평당가')[['아파트', '법정동', '평수', '거래금액', '평당가']].copy()
                    # 실제 데이터 개수에 맞춰 순위 생성
                    ranks = ['🥇', '🥈', '🥉', '4위', '5위'][:len(best_apt)]
                    best_apt.insert(0, '순위', ranks)
                    st.dataframe(best_apt, use_container_width=True, hide_index=True)
                else:
                    st.info("데이터가 없습니다.")
            
            with col2:
                st.markdown("### 🏢 오피스텔")
                if office_df is not None and not office_df.empty and '단지' in office_df.columns:
                    best_office = office_df.nsmallest(5, '평당가')[['단지', '법정동', '평수', '거래금액', '평당가']].copy()
                    # 실제 데이터 개수에 맞춰 순위 생성
                    ranks = ['🥇', '🥈', '🥉', '4위', '5위'][:len(best_office)]
                    best_office.insert(0, '순위', ranks)
                    st.dataframe(best_office, use_container_width=True, hide_index=True)
                else:
                    st.info("데이터가 없습니다.")
            
            st.markdown("---")
            
            # 실거래 테이블
            st.markdown("## 📋 실거래 상세 내역")
            
            tab_apt, tab_office = st.tabs(["🏠 아파트", "🏢 오피스텔"])
            
            with tab_apt:
                if apt_df is not None and not apt_df.empty:
                    display_cols = ['거래일자', '시군구', '법정동', '아파트', '전용면적', '평수', '거래금액', '평당가', '층', '건축년도']
                    available_cols = [col for col in display_cols if col in apt_df.columns]
                    st.dataframe(
                        apt_df[available_cols].sort_values('거래일자', ascending=False).head(100),
                        use_container_width=True,
                        height=400
                    )
                else:
                    st.info("아파트 데이터가 없습니다.")
            
            with tab_office:
                if office_df is not None and not office_df.empty:
                    display_cols = ['거래일자', '시군구', '법정동', '단지', '전용면적', '평수', '거래금액', '평당가', '층', '건축년도']
                    available_cols = [col for col in display_cols if col in office_df.columns]
                    st.dataframe(
                        office_df[available_cols].sort_values('거래일자', ascending=False).head(100),
                        use_container_width=True,
                        height=400
                    )
                else:
                    st.info("오피스텔 데이터가 없습니다.")
    
    else:
        st.info("👈 왼쪽 사이드바에서 지역과 기간을 선택한 후 '데이터 조회' 버튼을 눌러주세요!")


if __name__ == "__main__":
    main()