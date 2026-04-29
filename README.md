# 📰 Gemini 실시간 뉴스 검색기 만들기

이 프로젝트는 구글의 최신 AI(Gemini)를 활용해 실시간으로 뉴스를 검색하고, 내용을 요약하여 CSV 파일로 저장할 수 있는 웹 애플리케이션입니다. 코딩을 몰라도 다음 단계를 따라하면 10분 만에 완성할 수 있습니다!

## 🚀 시작하기 5단계

### [1단계] AI Studio에서 Gemini API 키 발급받기
AI의 두뇌를 빌려 쓰기 위한 '출입증'을 받는 과정입니다.
1. [Google AI Studio](https://aistudio.google.com/apikey)에 접속하세요.
2. 구글 로그인을 합니다.
3. 좌측 상단 파란색 **"Get API key"** 버튼을 클릭하세요.
4. **"Create API key in new project"**를 클릭하여 키를 생성합니다.
5. `AIza...`로 시작하는 긴 문자열이 나옵니다. 옆의 복사 아이콘을 눌러 메모장에 잘 적어두세요.
   - ⚠️ **주의**: 이 키가 공개되면 다른 사람이 내 한도를 다 쓸 수 있습니다. 절대 코드에 직접 적지 마세요!

### [2단계] GitHub에 코드 올리기
내 코드를 저장할 '온라인 저장소'를 만드는 과정입니다.
1. [GitHub](https://github.com)에 로그인하고 오른쪽 상단 `+` 버튼 -> **New repository**를 누릅니다.
2. 이름(예: `my-news-app`)을 정하고 **Create repository**를 누릅니다.
3. 위에서 제공된 `app.py`, `requirements.txt` 파일을 직접 만들거나 업로드하세요.

### [3단계] GitHub Codespaces 열기
내 컴퓨터에 설치 없이 인터넷 브라우저 상에서 서버를 실행하는 과정입니다.
1. 내 저장소 화면 상단 초록색 **"<> Code"** 버튼을 누릅니다.
2. **"Codespaces"** 탭을 클릭하고 **"Create codespace on main"**을 누릅니다.
3. 잠시 기다리면 웹 브라우저 안에 VS Code 편집기가 나타납니다.

### [4단계] Secrets에 API 키 등록하기 (★ 가장 중요)
가장 많이 실수하는 부분입니다. 보안을 위해 키를 숨겨서 등록해야 합니다.
1. [GitHub Codespaces 설정 페이지](https://github.com/settings/codespaces)로 이동합니다.
2. **"Personal Codespaces secrets"** 섹션에서 **"New secret"**을 누릅니다.
3. **Name**에는 정확히 `GEMINI_API_KEY` 라고 적습니다.
4. **Value**에는 아까 복사한 `AIza...`로 시작하는 키를 붙여넣습니다.
5. **Repository access**에서 이 프로젝트 저장소를 선택하고 **Add secret**을 누릅니다.
6. ⚠️ **중요**: 다시 Codespace 화면으로 돌아와서 `Ctrl + Shift + P`를 누르고 `Codespaces: Rebuild Container`를 검색해 실행하세요. (설정을 새로고침하는 과정입니다)

### [5단계] 앱 실행하기
1. 화면 하단 터미널(Terminal) 창에 다음 명령어를 입력하고 엔터를 누릅니다.
   ```bash
   pip install -r requirements.txt