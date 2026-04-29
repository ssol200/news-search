import streamlit as st
import pandas as pd
import os
import json
import re
from google import genai
from google.genai import types
from datetime import datetime


def get_api_key():
    return os.environ.get("GEMINI_API_KEY")


def clean_and_parse_json(raw_text):
    clean_text = re.sub(r"```json|```", "", raw_text).strip()

    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", clean_text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def search_news_with_gemini(keyword, model_name):
    api_key = get_api_key()

    if not api_key:
        st.error("GEMINI_API_KEY가 설정되지 않았습니다.")
        st.stop()

    client = genai.Client(api_key=api_key)

    prompt = f"""
    "{keyword}"에 대한 최신 뉴스 기사 5건을 검색해줘.

    조건:
    - 반드시 google_search 도구를 사용해 실시간 정보를 확인할 것
    - 한국어로 요약할 것
    - 응답은 JSON 배열만 출력할 것
    - 설명 문장, 코드블록, 마크다운은 출력하지 말 것

    형식:
    [
      {{
        "title": "기사 제목",
        "press": "언론사",
        "date": "YYYY-MM-DD",
        "url": "기사 URL",
        "summary": "기사 내용을 3~4문장으로 요약"
      }}
    ]
    """

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[
                    types.Tool(
                        google_search=types.GoogleSearchRetrieval()
                    )
                ],
                response_mime_type="application/json"
            )
        )

        return clean_and_parse_json(response.text)

    except Exception as e:
        error_msg = str(e)

        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            st.error("Gemini API 사용량 한도를 초과했습니다.")
            st.warning(
                "잠시 후 다시 시도하거나, 왼쪽 사이드바에서 다른 모델을 선택해보세요."
            )
            st.code(error_msg[:1000])
        else:
            st.error("뉴스 검색 중 오류가 발생했습니다.")
            st.code(error_msg[:1000])

        return None


def render_article_card(article):
    title = article.get("title", "제목 없음")
    url = article.get("url", "#")
    press = article.get("press", "언론사 정보 없음")
    date = article.get("date", "날짜 정보 없음")
    summary = article.get("summary", "요약 없음")

    with st.container(border=True):
        st.markdown(f"### [{title}]({url})")
        st.caption(f"🏢 {press} | 📅 {date}")
        st.write(summary)


def main():
    st.set_page_config(
        page_title="Gemini 뉴스 검색기",
        page_icon="📰",
        layout="wide"
    )

    st.title("📰 Gemini 뉴스 검색기")
    st.write("키워드를 입력하면 최신 뉴스를 검색하고 AI가 요약합니다.")

    model_name = st.sidebar.selectbox(
        "Gemini 모델 선택",
        [
            "gemini-1.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-pro"
        ],
        index=0
    )

    st.sidebar.info(
        "429 오류가 나면 사용량 한도 초과입니다. "
        "다른 모델을 선택하거나 잠시 후 다시 시도하세요."
    )

    if "search_results" not in st.session_state:
        st.session_state.search_results = None

    if "last_keyword" not in st.session_state:
        st.session_state.last_keyword = ""

    with st.form("search_form"):
        keyword = st.text_input(
            "검색 키워드",
            placeholder="예: 한국보건의료정보원, 생성형 AI, 의료데이터"
        )
        submitted = st.form_submit_button("뉴스 검색")

    if submitted:
        if not keyword.strip():
            st.warning("검색어를 입력해주세요.")
        else:
            with st.spinner("뉴스를 검색하고 요약하는 중입니다..."):
                results = search_news_with_gemini(keyword, model_name)

                if results:
                    st.session_state.search_results = results
                    st.session_state.last_keyword = keyword

    if st.session_state.search_results:
        st.subheader(f"검색 결과: {st.session_state.last_keyword}")

        for article in st.session_state.search_results:
            render_article_card(article)

        df = pd.DataFrame(st.session_state.search_results)

        csv_data = df.to_csv(index=False, encoding="utf-8-sig")

        st.download_button(
            label="CSV 다운로드",
            data=csv_data,
            file_name=f"news_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )


if __name__ == "__main__":
    main()