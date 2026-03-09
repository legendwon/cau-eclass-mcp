# 🎓 CAU e-class MCP

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**브라우저 없이 Claude에서 바로 중앙대 e-class를 확인하세요!**

공지사항, 과제, 강의자료를 Claude와 대화하면서 확인할 수 있는 MCP 서버입니다.

> ⚠️ 학생이 만든 **비공식** 도구입니다. 중앙대학교와 무관하며, 사용에 따른 책임은 본인에게 있습니다.

---

## ✨ 이런 걸 할 수 있어요

| 기능 | 설명 |
|---|---|
| 📋 **대시보드** | 수강 중인 전체 과목 한눈에 보기 |
| 📢 **공지사항** | 과목별 공지사항 읽기 |
| 📝 **과제** | 과제 목록 + 마감일 + 제출 상태 확인 |
| 🎬 **강의자료** | 주차별 강의 모듈 + 출석 현황 |
| 🌐 **Web UI** | 브라우저에서 인증 설정 + 서버 모니터링 |

---

## 🚀 시작하기

### 필요한 것

- **Python 3.10** 이상
- **중앙대 포탈 계정** (학번 + 비밀번호)
- **Claude Code** ([설치 링크](https://claude.com/code))

### Step 1: 설치

**방법 A) GitHub에서 바로 설치** (가장 간단)

```bash
pip install git+https://github.com/legendwon/cau-eclass-mcp.git
```

**방법 B) 직접 클론해서 설치** (개발용)

```bash
git clone https://github.com/legendwon/cau-eclass-mcp.git
cd cau-eclass-mcp
pip install -e .
```

> 💡 **venv를 쓰고 있다면?** 반드시 해당 venv의 pip으로 설치하세요:
> ```bash
> # Windows
> .\venv\Scripts\pip.exe install -e .
> 
> # macOS/Linux
> ./venv/bin/pip install -e .
> ```

### Step 2: 인증 설정

최초 1회만 하면 됩니다. 3가지 방법 중 편한 걸 골라주세요:

#### 🔐 방법 1: OS 키링에 저장 (추천)

가장 안전합니다. 비밀번호가 운영체제의 보안 저장소에 암호화되어 저장돼요.

```bash
python -c "from cau_eclass_mcp.utils.credentials import CredentialManager; m = CredentialManager(); m.prompt_for_credentials()"
```

학번과 비밀번호를 입력하면 끝!

- Windows → 자격 증명 관리자
- macOS → 키체인
- Linux → GNOME Keyring / KWallet

#### 🌐 방법 2: Web UI에서 설정

터미널이 불편하다면 웹 브라우저에서도 설정할 수 있어요:

```bash
python -m cau_eclass_mcp --sse
```

브라우저에서 http://localhost:8000 을 열고, 학번/비밀번호를 입력하면 됩니다.

#### ⚡ 방법 3: 환경변수

임시로 쓰거나 CI/CD에서 유용합니다:

```bash
# Windows (PowerShell)
$env:CAU_USERNAME="학번"
$env:CAU_PASSWORD="비밀번호"

# macOS/Linux
export CAU_USERNAME="학번"
export CAU_PASSWORD="비밀번호"
```

#### 🤷 방법 4: 그냥 실행하기

아무 설정 안 해도 첫 실행 시 자동으로 물어봅니다!

### Step 3: Claude Code에 연결

Claude Code가 이 MCP 서버를 인식하도록 설정 파일을 추가해주세요.

**모든 프로젝트에서 쓰고 싶다면** → `~/.claude/claude.json` 편집:

```json
{
  "mcpServers": {
    "cau-eclass": {
      "command": "python",
      "args": ["-m", "cau_eclass_mcp"]
    }
  }
}
```

> Windows 경로: `C:\Users\사용자이름\.claude\claude.json`

**특정 프로젝트에서만 쓰고 싶다면** → 프로젝트 루트에 `.mcp.json` 생성:

```json
{
  "mcpServers": {
    "cau-eclass": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "cau_eclass_mcp"]
    }
  }
}
```

> 💡 **venv를 쓰고 있다면?** `"command"`를 venv의 python 경로로 바꿔주세요:
> ```json
> {
>   "mcpServers": {
>     "cau-eclass": {
>       "type": "stdio",
>       "command": "D:\\경로\\cau-eclass-mcp\\venv\\Scripts\\python.exe",
>       "args": ["-m", "cau_eclass_mcp"],
>       "cwd": "D:\\경로\\cau-eclass-mcp",
>       "env": {
>         "PYTHONPATH": "D:\\경로\\cau-eclass-mcp\\src"
>       }
>     }
>   }
> }
> ```

설정 후 **Claude Code를 재시작**하면 끝!

---

## 💬 사용법

Claude Code에서 자연스럽게 말하면 됩니다:

```
나: "e-class 대시보드 보여줘"
Claude: [수강 중인 8개 과목 목록 표시]

나: "암호와-인증 과목 공지사항 확인해줘"
Claude: [최근 공지사항 표시]

나: "이번 주 과제 뭐 있어?"
Claude: [마감일과 제출 상태를 포함한 과제 목록]

나: "공공기관NCS분석 강의자료 보여줘"
Claude: [주차별 강의 모듈 + 출석 현황]
```

---

## 🌐 Web UI 모드 (SSE)

터미널 대신 브라우저에서 쓰고 싶다면 SSE 모드로 실행하세요:

```bash
# 기본 실행 (http://localhost:8000)
python -m cau_eclass_mcp --sse

# 포트 변경
python -m cau_eclass_mcp --sse --port 9000
```

브라우저에서 http://localhost:8000 을 열면:

- **인증 설정** — 학번/비밀번호 등록, 확인, 삭제
- **서버 상태** — 실시간 모니터링, 인증 상태, 가동 시간
- **API 문서** — http://localhost:8000/docs 에서 Swagger UI 확인

종료하려면 터미널에서 `Ctrl+C`

---

## 🔧 MCP 도구 목록

Claude Code에서 자동으로 사용되는 도구들입니다:

| 도구 | 설명 | 파라미터 |
|---|---|---|
| `get_dashboard` | 전체 수강 과목 조회 | 없음 |
| `list_course_announcements` | 과목 공지사항 | `course_id` (필수), `limit` (선택, 기본 20) |
| `list_assignments` | 과제 목록 + 제출 상태 | `course_id` (필수) |
| `get_lecture_modules` | 주차별 강의 + 출석 | `course_id` (필수), `include_attendance` (선택) |

---

## 🏗️ 기술 구조

### CAU-ON 플랫폼

중앙대는 **CAU-ON**이라는 자체 LMS를 사용합니다 (Canvas 기반이지만 커스텀). 이 MCP 서버는:

1. CAU SSO 포탈에서 RSA 암호화로 로그인
2. API가 활성화된 세션 쿠키 획득
3. Canvas 스타일 REST API (`/api/v1/...`)로 데이터 조회

### 인증 흐름

```
학번/비밀번호 입력 → SSO 로그인 → RSA 비밀번호 암호화 → Canvas 세션
                → API 활성 쿠키 획득 → CAU-ON API 요청
```

- 서버가 제공하는 RSA 개인키로 클라이언트 측 암호화 (특이한 구조!)
- PKCS1v15 패딩
- HTTP/2 필수
- `Referer` 헤더가 세션 업그레이드에 필수
- 세션 쿠키: 208자 (기본) → 421자 (API 활성)

---

## ❓ 문제 해결

### "Failed to authenticate with CAU SSO"

- 학번/비밀번호가 맞는지 확인
- Web UI에서 다시 설정: http://localhost:8000 (SSE 모드)
- 또는 기존 인증 정보 삭제 후 재등록:
  ```bash
  python -c "from cau_eclass_mcp.utils.credentials import CredentialManager; m = CredentialManager(); m.delete_credentials()"
  ```

### "Keyring not available"

키링이 안 되면 환경변수를 사용하세요:
```bash
$env:CAU_USERNAME="학번"
$env:CAU_PASSWORD="비밀번호"
```

### MCP 서버가 응답하지 않을 때

1. 직접 실행해서 에러 확인:
   ```bash
   python -m cau_eclass_mcp          # stdio 모드
   python -m cau_eclass_mcp --sse    # SSE 모드
   ```
2. Claude Code 로그 확인
3. `.mcp.json` 또는 `claude.json` 설정 확인

### 세션 만료 에러

세션은 30분 동안 캐시되며, 만료 시 자동으로 재로그인됩니다. 그래도 에러가 나면 Claude Code를 재시작하세요.

---

## 🛠️ 개발 참여

### 테스트 실행

```bash
pip install -e .[dev]
pytest tests/ -v
```

### 코드 포맷팅

```bash
black src/ tests/
ruff check src/ tests/
```

### 기여하기

1. 이 repository를 Fork
2. 기능 브랜치 생성 (`git checkout -b feature/멋진기능`)
3. 커밋 (`git commit -m '멋진 기능 추가'`)
4. 푸시 (`git push origin feature/멋진기능`)
5. Pull Request 생성

---

## 🔒 보안

- 비밀번호는 OS 키링에 암호화 저장
- 비밀번호를 절대 Git에 커밋하지 마세요
- 보안 이슈 발견 시 [GitHub Issues](https://github.com/legendwon/cau-eclass-mcp/issues)로 알려주세요

## 📄 라이선스

MIT License — [LICENSE](LICENSE) 파일 참고

## 🙏 감사

- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- [Claude Code](https://claude.com/code)
- 13시간의 CAU-ON API 디버깅에서 탄생 🐛

---

**궁금한 점이나 버그는?** → [GitHub Issues](https://github.com/legendwon/cau-eclass-mcp/issues)에 남겨주세요!
