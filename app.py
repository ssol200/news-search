import streamlit as st
import pandas as pd
import json
import re
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from supabase import create_client, Client

# -------------------------------------------------------------------
# 1. 페이지 기본 설정
# -------------------------------------------------------------------
st.set_page_config(page_title="LLM 기반 뉴스 검색 앱", page_icon="📰", layout="wide")

# -------------------------------------------------------------------
# 2. 비밀 키(Secrets) 불러오기 및 초기화
# -------------------------------------------------------------------
# Streamlit Cloud의 Secrets(또는 로컬의 .streamlit/secrets.toml)에서 키를 읽어옵니다.
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# 과제 2 추가: 네이버 뉴스 검색 API 키
# 네이버 Developers에서 애플리케이션을 등록한 뒤 발급받은 값을 Secrets에 저장합니다.
NAVER_CLIENT_ID = st.secrets["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]

# Supabase 클라이언트 연결
@st.cache_resource  # 데이터베이스 연결을 매번 하지 않고 캐싱(저장)해두어 속도를 높입니다.
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# Gemini 클라이언트 연결
client = genai.Client(api_key=GEMINI_API_KEY)

# -------------------------------------------------------------------
# 3. 공통 함수
# -------------------------------------------------------------------
def clean_html(text: str) -> str:
    """네이버 뉴스 API 응답에 포함된 <b> 태그 등 HTML 태그를 제거합니다."""
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text()


def is_valid_url(url: str) -> bool:
    """URL 형식이 정상인지 확인합니다."""
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in ["http", "https"] and bool(parsed.netloc)


def normalize_text(text: str) -> str:
    """제목 비교를 위해 특수문자를 제거하고 소문자로 변환합니다."""
    if not text:
        return ""
    text = clean_html(text).lower()
    text = re.sub(r"[^0-9a-zA-Z가-힣\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def token_overlap_score(a: str, b: str) -> float:
    """두 문장의 주요 토큰이 얼마나 겹치는지 계산합니다."""
    tokens_a = {t for t in normalize_text(a).split() if len(t) >= 2}
    tokens_b = {t for t in normalize_text(b).split() if len(t) >= 2}

    if not tokens_a or not tokens_b:
        return 0.0

    return len(tokens_a & tokens_b) / len(tokens_a)


def fetch_page_title(url: str):
    """URL에 접속해 최종 URL, HTTP 상태코드, 페이지 제목을 가져옵니다."""
    if not is_valid_url(url):
        return {
            "input_url": url,
            "final_url": "",
            "status_code": None,
            "page_title": "",
            "ok": False,
            "error": "URL 형식 오류"
        }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    try:
        res = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        ok = 200 <= res.status_code < 400
        page_title = ""

        if ok and res.text:
            soup = BeautifulSoup(res.text[:50000], "html.parser")
            if soup.title and soup.title.string:
                page_title = soup.title.string.strip()

        return {
            "input_url": url,
            "final_url": res.url,
            "status_code": res.status_code,
            "page_title": clean_html(page_title),
            "ok": ok,
            "error": ""
        }

    except Exception as e:
        return {
            "input_url": url,
            "final_url": "",
            "status_code": None,
            "page_title": "",
            "ok": False,
            "error": str(e)
        }


def verify_news_link(title: str, primary_url: str, fallback_url: str = "") -> dict:
    """
    기사 제목과 링크를 더블 체크합니다.
    1순위 URL에 접속해 상태코드와 페이지 제목을 확인하고,
    제목 유사도가 낮거나 접속 실패 시 2순위 URL을 확인합니다.
    """
    candidates = []
    for label, url in [("primary", primary_url), ("fallback", fallback_url)]:
        if url and url not in [c["url"] for c in candidates]:
            candidates.append({"label": label, "url": url})

    checked = []
    for candidate in candidates:
        info = fetch_page_title(candidate["url"])
        score = token_overlap_score(title, info.get("page_title", ""))
        info["candidate_type"] = candidate["label"]
        info["title_match_score"] = score
        checked.append(info)

    # 페이지 접속이 되고 제목 유사도가 일정 수준 이상인 링크를 우선 선택
    for info in checked:
        if info["ok"] and info["title_match_score"] >= 0.25:
            info["link_status"] = "확인됨"
            info["link_note"] = "URL 접속 및 제목 유사도 확인"
            return info

    # 제목 유사도는 낮지만 접속 가능한 링크가 있으면 사용하되 주의 표시
    for info in checked:
        if info["ok"]:
            info["link_status"] = "접속 가능/제목 확인 필요"
            info["link_note"] = "URL은 접속되지만 페이지 제목과 검색 결과 제목의 유사도가 낮음"
            return info

    # 모두 실패하면 원래 후보 중 첫 번째를 반환
    if checked:
        info = checked[0]
        info["link_status"] = "확인 실패"
        info["link_note"] = info.get("error") or "URL 접속 실패"
        return info

    return {
        "input_url": "",
        "final_url": "",
        "status_code": None,
        "page_title": "",
        "ok": False,
        "candidate_type": "none",
        "title_match_score": 0.0,
        "link_status": "URL 없음",
        "link_note": "확인할 URL이 없음"
    }


def extract_json_array(raw_text: str):
    """Gemini 응답에서 JSON 배열 부분만 추출합니다."""
    match = re.search(r'\[\s*\{.*?\}\s*\]', raw_text, re.DOTALL)
    clean_json_str = match.group(0) if match else raw_text
    return json.loads(clean_json_str)


def search_google_news_with_gemini(keyword: str, result_count: int = 5):
    """Gemini Google Search 도구를 활용해 최신 뉴스를 JSON 형식으로 받습니다."""
    prompt = f"""
    다음 키워드에 대한 가장 최신 뉴스 {result_count}건을 검색하고 요약해주세요: '{keyword}'

    [요구사항]
    1. Google Search를 사용해 최신 정보를 가져오세요.
    2. 각 뉴스별로 제목(title), 출처(source), 날짜(news_date), 원본 URL(url), 3~4문장의 요약(summary)을 작성하세요.
    3. url은 Google Search 결과에서 확인된 실제 기사 URL만 사용하세요. URL을 임의로 만들지 마세요.
    4. 제목과 URL의 기사 내용이 일치하는 결과만 포함하세요.
    5. 응답은 반드시 아래 형태의 JSON 배열(Array)로만 출력해야 합니다.
    [
        {{
            "title": "뉴스 제목",
            "source": "언론사 이름",
            "news_date": "YYYY-MM-DD",
            "url": "https://...",
            "summary": "3~4문장의 요약 내용"
        }}
    ]
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}],
            temperature=0.2
        )
    )

    return extract_json_array(response.text)


def search_naver_news(keyword: str, display: int = 5, sort: str = "date"):
    """네이버 뉴스 검색 API를 호출하여 뉴스 검색 결과를 리스트로 반환합니다."""
    url = "https://openapi.naver.com/v1/search/news.json"

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }

    params = {
        "query": keyword,
        "display": display,
        "start": 1,
        "sort": sort  # date: 최신순, sim: 정확도순
    }

    response = requests.get(url, headers=headers, params=params, timeout=10)

    if response.status_code != 200:
        raise Exception(f"네이버 API 오류: {response.status_code} / {response.text}")

    items = response.json().get("items", [])

    news_list = []
    for item in items:
        title = clean_html(item.get("title", ""))
        originallink = item.get("originallink", "")
        naver_link = item.get("link", "")
        verification = verify_news_link(
            title=title,
            primary_url=originallink,   # 언론사 원문 링크 우선
            fallback_url=naver_link     # 원문 확인 실패 시 네이버 뉴스 링크 사용
        )

        news_list.append({
            "keyword": keyword,
            "title": title,
            "originallink": originallink,
            "link": naver_link,
            "best_link": verification.get("final_url") or originallink or naver_link,
            "link_status": verification.get("link_status"),
            "link_note": verification.get("link_note"),
            "page_title": verification.get("page_title"),
            "title_match_score": verification.get("title_match_score"),
            "description": clean_html(item.get("description", "")),
            "pub_date": item.get("pubDate", "")
        })

    return news_list


def save_google_news(keyword: str, news: dict):
    """Gemini+Google Search 뉴스 결과를 기존 news_history 테이블에 저장합니다."""
    db_record = {
        "keyword": keyword,
        "title": news.get("title"),
        "source": news.get("source"),
        "news_date": news.get("news_date"),
        "url": news.get("url"),
        "summary": news.get("summary")
    }
    return supabase.table("news_history").insert(db_record).execute()


def save_naver_news(news: dict):
    """네이버 검색 결과를 과제용 추가 테이블 naver_news_history에 저장합니다."""
    db_record = {
        "keyword": news.get("keyword"),
        "title": news.get("title"),
        "originallink": news.get("originallink"),
        "link": news.get("link"),
        "best_link": news.get("best_link"),
        "link_status": news.get("link_status"),
        "link_note": news.get("link_note"),
        "page_title": news.get("page_title"),
        "title_match_score": news.get("title_match_score"),
        "description": news.get("description"),
        "pub_date": news.get("pub_date")
    }
    return supabase.table("naver_news_history").insert(db_record).execute()


def get_table_data(table_name: str):
    """Supabase 테이블 데이터를 최신순으로 조회합니다."""
    return supabase.table(table_name).select("*").order("created_at", desc=True).execute().data


# -------------------------------------------------------------------
# 4. 화면 UI 구성
# -------------------------------------------------------------------
st.title("📰 LLM 기반 뉴스 검색 앱")
st.info(
    "💡 구글과 네이버를 활용한 뉴스 검색 결과를 비교하고, "
    "각 결과를 Supabase DB에 저장할 수 있습니다."
)

tab1, tab2, tab3, tab4 = st.tabs([
    "🔍 검색 및 비교",
    "💾 구글 검색 결과",
    "🟢 네이버 검색 결과",
    "📊 통계/DB 설명"
])

# ==========================================
# 탭 1: 구글 검색 결과와 네이버 검색 결과 비교
# ==========================================
with tab1:
    st.subheader("구글 검색 결과와 네이버 검색 결과 비교")

    keyword = st.text_input("검색할 뉴스 키워드를 입력하세요", placeholder="예: 인공지능, 보건의료데이터, 데이터뱅크")
    st.markdown("#### 검색 조건")
    display_count = st.slider("검색 결과 개수", min_value=5, max_value=20, value=5, step=1)

    with st.expander("🟢 네이버 뉴스 API 정렬 옵션", expanded=False):
        st.caption("구글 검색은 별도 정렬 기준을 직접 지정하기 어려워, 네이버 뉴스 API에만 정렬 기준을 적용합니다.")
        naver_sort_label = st.radio("네이버 뉴스 정렬 기준", ["최신순", "정확도순"], horizontal=True)

    naver_sort = "date" if naver_sort_label == "최신순" else "sim"

    if st.button("뉴스 검색 및 비교", type="primary"):
        if not keyword:
            st.warning("키워드를 입력해주세요!")
        else:
            col1, col2 = st.columns(2)

            # --------------------------
            # Google Search + Gemini 결과
            # --------------------------
            with col1:
                st.markdown("### ① 구글 검색 결과")
                google_saved_count = 0
                google_duplicate_count = 0

                with st.spinner("Gemini가 구글 검색을 사용해 최신 뉴스를 검색하고 요약 중입니다..."):
                    try:
                        google_news_data = search_google_news_with_gemini(keyword, result_count=display_count)
                        st.success(f"구글 검색 결과 {len(google_news_data)}건 검색 완료")

                        for idx, news in enumerate(google_news_data, start=1):
                            verification = verify_news_link(
                                title=news.get("title", ""),
                                primary_url=news.get("url", "")
                            )
                            news["url"] = verification.get("final_url") or news.get("url")

                            with st.container(border=True):
                                st.markdown(f"#### {idx}. [{news.get('title')}]({news.get('url')})")
                                st.caption(f"🏢 출처: {news.get('source')} | 📅 날짜: {news.get('news_date')}")
                                st.caption(
                                    f"🔎 링크 검증: {verification.get('link_status')} "
                                    f"| 제목 일치도: {verification.get('title_match_score', 0):.2f}"
                                )
                                if verification.get("page_title"):
                                    st.caption(f"확인된 페이지 제목: {verification.get('page_title')}")
                                st.write(news.get("summary"))

                            # 기존 과제 앱 구조 유지: Google 결과는 기존 news_history 테이블에 자동 저장
                            # 단, 링크 접속이 실패한 결과는 잘못된 기사 저장을 막기 위해 저장하지 않습니다.
                            if not verification.get("ok"):
                                continue

                            try:
                                save_google_news(keyword, news)
                                google_saved_count += 1
                            except Exception as db_e:
                                if "duplicate key value" in str(db_e) or "23505" in str(db_e):
                                    google_duplicate_count += 1
                                else:
                                    st.error(f"Google 결과 DB 저장 중 오류: {db_e}")

                        st.caption(f"구글 결과 저장: 신규 {google_saved_count}건 / 중복 {google_duplicate_count}건")

                    except Exception as e:
                        st.error(f"구글 검색 중 오류가 발생했습니다: {e}")

            # --------------------------
            # Naver News API 결과
            # --------------------------
            with col2:
                st.markdown("### ② 네이버 검색 결과")
                naver_saved_count = 0
                naver_duplicate_count = 0

                with st.spinner("네이버 뉴스 API로 검색 중입니다..."):
                    try:
                        naver_news_data = search_naver_news(keyword, display=display_count, sort=naver_sort)
                        st.success(f"네이버 뉴스 {len(naver_news_data)}건 검색 완료")

                        for idx, news in enumerate(naver_news_data, start=1):
                            target_link = news.get("best_link") or news.get("originallink") or news.get("link")

                            with st.container(border=True):
                                st.markdown(f"#### {idx}. [{news.get('title')}]({target_link})")
                                st.caption(f"📅 발행일: {news.get('pub_date')}")
                                st.caption(
                                    f"🔎 링크 검증: {news.get('link_status')} "
                                    f"| 제목 일치도: {news.get('title_match_score', 0):.2f}"
                                )
                                if news.get("page_title"):
                                    st.caption(f"확인된 페이지 제목: {news.get('page_title')}")
                                st.write(news.get("description"))
                                st.caption(f"선택된 링크: {target_link}")
                                st.caption(f"언론사 원문 링크: {news.get('originallink')}")
                                st.caption(f"네이버 뉴스 링크: {news.get('link')}")

                            # 과제 2 추가: 네이버 결과는 naver_news_history 테이블에 자동 저장
                            # 접속 실패 링크는 저장하지 않아 잘못된 기사 누적을 방지합니다.
                            if news.get("link_status") == "확인 실패":
                                continue

                            try:
                                save_naver_news(news)
                                naver_saved_count += 1
                            except Exception as db_e:
                                if "duplicate key value" in str(db_e) or "23505" in str(db_e):
                                    naver_duplicate_count += 1
                                else:
                                    st.error(f"Naver 결과 DB 저장 중 오류: {db_e}")

                        st.caption(f"네이버 결과 저장: 신규 {naver_saved_count}건 / 중복 {naver_duplicate_count}건")

                    except Exception as e:
                        st.error(f"네이버 뉴스 검색 중 오류가 발생했습니다: {e}")

# ==========================================
# 탭 2: 기존 Google/Gemini 저장 뉴스 보기
# ==========================================
with tab2:
    st.subheader("구글 검색 결과 저장 목록")

    try:
        google_data = get_table_data("news_history")

        if google_data:
            df_google = pd.DataFrame(google_data)

            search_term = st.text_input("구글 검색 결과 필터링", "", key="google_filter")

            if search_term:
                df_google = df_google[
                    df_google["keyword"].str.contains(search_term, case=False, na=False) |
                    df_google["title"].str.contains(search_term, case=False, na=False)
                ]

            display_cols = [col for col in ["keyword", "title", "source", "news_date", "url", "created_at"] if col in df_google.columns]

            st.dataframe(
                df_google[display_cols],
                use_container_width=True,
                hide_index=True
            )

            csv_data = df_google.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                label="📥 구글 검색 결과 CSV 다운로드",
                data=csv_data,
                file_name="saved_google_news_history.csv",
                mime="text/csv"
            )
        else:
            st.info("아직 저장된 구글 검색 결과가 없습니다.")

    except Exception as e:
        st.error(f"구글 검색 결과를 불러오는 중 오류가 발생했습니다: {e}")

# ==========================================
# 탭 3: 네이버 저장 뉴스 보기
# ==========================================
with tab3:
    st.subheader("네이버 검색 결과 저장 목록")

    try:
        naver_data = get_table_data("naver_news_history")

        if naver_data:
            df_naver = pd.DataFrame(naver_data)

            search_term = st.text_input("네이버 검색 결과 필터링", "", key="naver_filter")

            if search_term:
                df_naver = df_naver[
                    df_naver["keyword"].str.contains(search_term, case=False, na=False) |
                    df_naver["title"].str.contains(search_term, case=False, na=False)
                ]

            display_cols = [
                col for col in
                ["keyword", "title", "description", "pub_date", "best_link", "link_status", "title_match_score", "page_title", "originallink", "link", "created_at"]
                if col in df_naver.columns
            ]

            st.dataframe(
                df_naver[display_cols],
                use_container_width=True,
                hide_index=True
            )

            csv_data = df_naver.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                label="📥 네이버 검색 결과 CSV 다운로드",
                data=csv_data,
                file_name="saved_naver_news_history.csv",
                mime="text/csv"
            )
        else:
            st.info("아직 저장된 네이버 뉴스가 없습니다. 탭 1에서 뉴스를 검색해보세요!")

    except Exception as e:
        st.error(
            "네이버 검색 결과를 불러오는 중 오류가 발생했습니다. "
            "Supabase에 naver_news_history 테이블이 생성되어 있는지 확인해주세요."
        )
        st.write(e)

# ==========================================
# 탭 4: 통계 및 DB 설명
# ==========================================
with tab4:
    st.subheader("검색 통계 및 데이터베이스 설명")

    try:
        google_data = get_table_data("news_history")
    except Exception:
        google_data = []

    try:
        naver_data = get_table_data("naver_news_history")
    except Exception:
        naver_data = []

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📌 구글 검색 결과 통계")
        if google_data:
            df_google_stats = pd.DataFrame(google_data)
            keyword_counts = df_google_stats["keyword"].value_counts()
            st.bar_chart(keyword_counts)

            if "created_at" in df_google_stats.columns:
                df_google_stats["date_only"] = pd.to_datetime(df_google_stats["created_at"]).dt.date
                date_counts = df_google_stats["date_only"].value_counts().sort_index()
                st.line_chart(date_counts)
        else:
            st.info("구글 검색 결과 통계를 표시할 데이터가 없습니다.")

    with col2:
        st.markdown("### 📌 네이버 검색 결과 통계")
        if naver_data:
            df_naver_stats = pd.DataFrame(naver_data)
            keyword_counts = df_naver_stats["keyword"].value_counts()
            st.bar_chart(keyword_counts)

            if "created_at" in df_naver_stats.columns:
                df_naver_stats["date_only"] = pd.to_datetime(df_naver_stats["created_at"]).dt.date
                date_counts = df_naver_stats["date_only"].value_counts().sort_index()
                st.line_chart(date_counts)
        else:
            st.info("네이버 검색 결과 통계를 표시할 데이터가 없습니다.")

    st.divider()

    st.markdown("### 🗂️ 추가 테이블 설명: `naver_news_history`")
    st.write(
        "과제 요구사항인 '네이버 검색 결과 저장을 위한 추가 테이블'로 "
        "`naver_news_history` 테이블을 사용합니다."
    )

    table_desc = pd.DataFrame({
        "컬럼명": [
            "id",
            "keyword",
            "title",
            "originallink",
            "link",
            "best_link",
            "link_status",
            "link_note",
            "page_title",
            "title_match_score",
            "description",
            "pub_date",
            "created_at"
        ],
        "설명": [
            "저장 데이터 고유 번호",
            "사용자가 입력한 검색어",
            "네이버 검색 결과 제목",
            "언론사 원문 링크",
            "네이버 뉴스 링크",
            "검증 후 최종 선택된 기사 링크",
            "링크 검증 결과",
            "링크 검증 관련 참고 사항",
            "실제 접속한 페이지의 HTML title",
            "검색 결과 제목과 페이지 제목 간 유사도",
            "뉴스 요약 설명",
            "네이버 API에서 제공하는 발행일",
            "Supabase에 저장된 시각"
        ]
    })

    st.table(table_desc)

    st.markdown("### Supabase SQL")
    st.code(
        """
create table if not exists naver_news_history (
    id bigint generated by default as identity primary key,
    keyword text not null,
    title text,
    originallink text,
    link text unique,
    best_link text,
    link_status text,
    link_note text,
    page_title text,
    title_match_score numeric,
    description text,
    pub_date text,
    created_at timestamp with time zone default timezone('utc'::text, now())
);
        """,
        language="sql"
    )

    st.markdown("### 기존 테이블을 이미 만든 경우 추가 실행 SQL")
    st.code(
        """
alter table naver_news_history add column if not exists best_link text;
alter table naver_news_history add column if not exists link_status text;
alter table naver_news_history add column if not exists link_note text;
alter table naver_news_history add column if not exists page_title text;
alter table naver_news_history add column if not exists title_match_score numeric;
        """,
        language="sql"
    )
