# CAU e-class 플러그인 연결

이 프로젝트는 로컬 stdio 플러그인과 원격 ChatGPT 플러그인을 지원한다. 현재 원격 서버는 한 명의 사용자와 한 개의 학교 계정을 지원한다. 실제 학교 SSO 로그인과 데이터 조회는 본인 계정으로 별도 검증해야 한다.

과목 목록은 기존 school favorites dashboard endpoint를 사용하므로 전체 수강 과목의 일부일 수 있다. 과제·자료실은 기존 API의 한 페이지를 조회하며 모든 페이지의 통합 조회는 아직 지원하지 않는다.

## 로컬 플러그인

Python 3.10 이상과 uv를 설치한 뒤 프로젝트에서 다음을 실행한다.

```bash
uv run python -m cau_eclass_mcp --setup
python scripts/package_plugin.py --output dist/cau-eclass-local.zip
```

ZIP에는 플러그인 manifest, 스킬, 아이콘, MCP 설정과 Python 소스가 함께 들어간다. 지원하는 로컬 클라이언트에 ZIP을 설치한다. 이 패키지는 로컬 프로세스를 실행한다. ChatGPT 웹이나 모바일에서 사용할 원격 서버를 생성하지 않는다. 키링 설정은 실제 실행할 사용자 PC에서 해야 한다.

## 원격 서버

기존 OAuth 제공자를 사용한다. 서버에 새 OAuth 제공자를 구현하거나 중앙대 SSO가 MCP OAuth를 지원한다고 가정하지 않는다. 제공자에는 다음을 설정한다.

- Authorization Code + PKCE, OAuth discovery.
- MCP 클라이언트 등록 방식(CIMD/DCR 또는 사전 등록 클라이언트) 중 제공자가 지원하는 방식.
- MCP resource/audience: 실제 서버 origin 뒤에 `/mcp`를 붙인 주소.
- 요청 scope: `eclass:read`.
- JWT access token: RS256 또는 ES256, `iss`, `aud`, `exp`, `sub`, `scope` 포함.
- 실제 ChatGPT 연결 화면에 표시되는 callback URL을 등록한다.

`remote.env.example`의 각 값을 배포 환경에 설정한다. 학교 자격 증명은 서버의 비밀 저장소에서 공급한다. `CAU_MCP_OWNER_SUB`에는 허용할 본인의 OAuth subject를 넣는다. 이메일이나 학교 학번과 같은 값이라고 추측하지 말고 제공자에서 확인한다.

| 설정 | 의미 |
|---|---|
| `CAU_MCP_PUBLIC_URL` | 공개 HTTPS origin. `/mcp`를 제외한다. |
| `CAU_MCP_OAUTH_ISSUER` | access token의 정확한 issuer 값. trailing slash도 맞춘다. |
| `CAU_MCP_JWKS_URL` | 제공자의 HTTPS signing-key endpoint. |
| `CAU_MCP_OWNER_SUB` | 한 명의 허용된 OAuth 사용자 subject. |
| `CAU_USERNAME`, `CAU_PASSWORD` | 학교 계정. 서버에만 설정한다. |

```bash
docker build -t cau-eclass-mcp .
docker run --rm --env-file /secure/path/remote.env -p 127.0.0.1:8000:8000 cau-eclass-mcp
```

같은 머신의 HTTPS reverse proxy가 `/mcp`, `/.well-known/oauth-protected-resource/mcp`, `/health`를 전달하도록 구성한다. 외부에서 접근 가능한 실제 HTTPS 주소가 필요하다. 이 저장소 또는 플러그인 ZIP을 업로드하는 것만으로 서버가 배포되지는 않는다.

연결 주소는 `CAU_MCP_PUBLIC_URL` 뒤에 `/mcp`를 붙인 주소다. 원격 서버는 기존 localhost credential API를 노출하지 않는다. 등록되지 않은 사용자, 다른 audience/issuer, 만료 또는 유효하지 않은 token, 누락된 scope를 거부한다. 로그에는 비밀번호나 token, 학교 API 응답 본문을 남기지 않는다.

## 원격 플러그인 패키지 생성

서버를 먼저 배포하고 OAuth 제공자의 discovery와 로그인 흐름을 구성한다. 배포된 실제 URL로 다음을 실행한다.

```bash
python scripts/package_plugin.py --remote-url "$CAU_MCP_PUBLIC_URL/mcp" --output dist/cau-eclass-remote.zip
```

이 스크립트는 공개 protected-resource metadata와 일치하는 MCP 주소를 확인한다. 가짜 주소나 미배포 주소로 패키지를 생성하지 않는다. metadata 확인은 전체 OAuth 로그인을 검증하지 않으므로 설치 후 연결 테스트가 별도로 필요하다.

사전 등록 OAuth 클라이언트를 사용하는 경우 패키지의 `mcp.json`에 제공자에 맞는 client 설정을 추가한다. secret은 manifest에 넣지 말고 연결 화면에 입력한다. Private plugin으로 저장하고 OAuth 연결을 완료한다. 공개 디렉터리 제출은 별도 단계다.

## 검증

```bash
uv run pytest tests/ -q
uv run pytest tests/ -q --live
```

기본 테스트는 학교 계정 없이 실행한다. `--live`는 학교 계정과 네트워크가 있는 환경에서만 실행한다. 로그인, 수강 과목, 실제 공지와 과제, 세션 갱신을 검증한다.

MCP Inspector와 ChatGPT에서 차례로 초기화, 7개 도구 발견, `get_connection_status`, `get_dashboard`, 공지/과제 조회, 다운로드 링크를 확인한다. 원격 파일 다운로드는 학교 로그인 브라우저에서 원문을 받는 방식이며 ChatGPT 파일 첨부를 구현한 것은 아니다. VOD 링크 제공은 영상 시청이나 출석 처리를 수행하지 않는다.

연결 해제는 ChatGPT 또는 OAuth 제공자에서 권한을 철회한다. 서버 프로세스를 종료하면 메모리의 학교 세션과 캐시가 정리된다. 토큰이 만료되기 전 즉시 취소가 필요하면 OAuth 제공자의 정책으로 access token을 폐기하거나 서버의 허용 subject 설정을 변경한다. 여러 사용자로 확장하려면 사용자별 credential/session/cache 분리가 먼저 필요하다.
