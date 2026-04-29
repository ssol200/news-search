import streamlit as st
import pandas as pd
import os
import json
import re
from google import genai
from google.genai import types
from datetime import datetime

# 1. API 키 확인 함수 (보안을 위해 환경변수에서 가져옵니다)
def get_api_key():
    """시스템 설정에서 GEMINI_API_KEY를 가져옵니다."""
    key = os.environ.get("GEMINI_API_KEY")
    return key

# 2. 제미나이를 이용한 뉴스 검색 및 요약 함수
def search_news_with_gemini(keyword):
    """구글 검색 도구를 사용하여 키워드 관련 최신 뉴스 5건을 가져옵니다."""
    api_key = get_api_key()
    
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY가 설정되지 않았습니다. README의 4단계를 확인해주세요!")
        st.stop()

    # 클라이언트 생성 (새로운 google-genai SDK 방식)
    client = genai.Client(api_key=api_key)
    
    # AI에게 전달할 명확한 지시사항(프롬프트)
    prompt = f"""
    "{keyword}"에 대한 가장 최신의 뉴스 기사 5건을 찾아줘.
    반드시 google_search 도구를 사용해서 실시간 정보를 확인해.
    
    응답은 반드시 아래 형식을 지킨 JSON 배열로만 출력해줘. 다른 설명은 하지마.
    [
      {{
        "title": "기사 제목",
        "press": "언론사 이름",
        "date": "YYYY-MM-DD",
        "url": "원본 기사 URL",
        "summary": "3~4문장의 한국어 요약 내용"
      }}
    ]
    """

    try:
        # 구글 검색 기능(Grounding) 활성화하여 요청
        response = client.models.generate_content(
            model="gemini-2.0-flash", # 최신 모델 사용
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearchRetrieval())],
                response_mime_type="application/json" # JSON 응답 강제
            ),
            contents=prompt
        )
        
        # 응답 텍스트 추출
        raw_text = response.text
        
        # 안전한 JSON 파싱을 위한 전처리 (```json ... ``` 제거)
        clean_json = re.sub(r'```json\s*|```', '', raw_text).strip()
        
        # JSON 문자열을 파이썬 리스트로 변환
        news_data = json.loads(clean_json)
        return news_data

    except Exception as e:
        st.error(f"뉴스 검색 중 오류가 발생했습니다: {e}")
        # 만약 JSON 파싱 실패 시 원문 일부라도 보여주기 위함
        if 'raw_text' in locals():
            st.info("AI의 응답 형식이 올바르지 않습니다. 다시 시도해 주세요.")
        return None

# 3. 뉴스 기사를 카드 형태로 보여주는 함수
def render_article_card(idx, article):
    """각 뉴스 기사를 예쁜 카드 모양으로 화면에 그립니다."""
    with st.container():
        st.markdown(f"### [{article['title']}]({article['url']})")
        col1, col2 = st.columns([1, 1])
        with col1:
            st.caption(f"🏢 언론사: {article['press']}")
        with col2:
            st.caption(f"📅 발행일: {article['date']}")
        
        st.write(article['summary'])
        st.divider()

# 4. 메인 실행 함수
def main():
    # 웹 페이지 설정
    st.set_page_config(page_title="Gemini 뉴스 검색기", page_icon="📰")
    
    st.title("📰 Gemini 뉴스 검색기")
    st.write("키워드를 입력하면 최신 뉴스를 검색하고 AI가 요약해 드립니다.")

    # 세션 상태 초기화 (검색 결과 유지용)
    if 'search_results' not in st.session_state:
        st.session_state.search_results = None

    # 검색창 영역
    with st.form(key='search_form'):
        keyword = st.text_input("검색하고 싶은 키워드를 입력하세요", placeholder="예: 삼성전자 주가, 생성형 AI 트렌드")
        submit_button = st.form_submit_button(label='뉴스 검색')

    if submit_button and keyword:
        with st.spinner(f"'{keyword}'에 대한 최신 뉴스를 찾는 중..."):
            results = search_news_with_gemini(keyword)
            if results:
                st.session_state.search_results = results

    # 결과 표시 영역
    if st.session_state.search_results:
        st.subheader(f"🔍 '{keyword}' 검색 결과")
        
        # 5개 결과 출력
        for i, article in enumerate(st.session_state.search_results):
            render_article_card(i, article)
        
        # CSV 다운로드 준비
        df = pd.DataFrame(st.session_state.search_results)
        # 한글 깨짐 방지를 위해 utf-8-sig 인코딩 사용
        csv_data = df.to_csv(index=False, encoding='utf-8-sig')
        
        st.download_button(
            label="📊 결과 CSV로 다운로드",
            data=csv_data,
            file_name=f"news_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()