# md2atlassian

Markdown 파일을 **Confluence 페이지** 또는 **Jira 이슈 description**으로 변환·업로드하는 스크립트.

URL 패턴으로 대상을 자동 분기한다:

- `.../pages/<id>/...`        → Confluence 페이지
- `.../browse/<KEY>-<num>`    → Jira 이슈

## 왜?

- Confluence의 Markdown 매크로 블록은 테이블·코드 언어 감지·중첩 구조 등에서 렌더링이 불완전하다. 이 스크립트는 Markdown을 Confluence 네이티브 storage format으로 변환하므로 이런 제약이 없다.
- Jira description은 wiki markup 포맷이라 Markdown을 그대로 붙여넣을 수 없다. pandoc의 `-t jira` 출력으로 동일한 문서를 Jira에도 그대로 반영할 수 있다.

## 의존성

| 이름 | 용도 | 설치 |
|---|---|---|
| Python 3.10+ | 스크립트 실행 | macOS 기본 포함 또는 `brew install python` |
| [pandoc](https://pandoc.org/) | Markdown → HTML / Jira wiki markup 변환 | `brew install pandoc` |

## PAT 발급

Confluence/Jira 각각에서 Personal Access Token을 발급한다 (보통 별도 토큰).

1. 해당 제품(Confluence 또는 Jira) 접속
2. 우측 상단 **프로필 아이콘** → **설정(Settings)**
3. 좌측 메뉴 **Personal Access Tokens** 선택
4. **Create token** → 이름 입력 → 생성
5. 토큰 복사 후 환경변수에 등록 (사용할 대상만 등록하면 됨):

```bash
# 영구 등록 (~/.zshenv 또는 ~/.zshrc에 추가 후 source)
echo "export MD2CONFLUENCE_TOKEN='confluence_토큰'" >> ~/.zshenv
echo "export MD2JIRA_TOKEN='jira_토큰'" >> ~/.zshenv
source ~/.zshenv
```

## 사용법

> Confluence는 기존 페이지를, Jira는 기존 이슈 description을 **덮어쓰는** 방식입니다.
> Confluence의 경우 새 글을 작성하려면 Confluence에서 **빈 페이지를 먼저 생성**한 뒤, 해당 페이지 URL을 인자로 넣어주세요.

```bash
# 기본 사용 (URL로 대상 자동 분기)
python3 md2atlassian.py <md_파일> <url>

# 변환 결과만 확인 (URL 생략 시 --format 지정)
python3 md2atlassian.py <md_파일> --dry-run --format confluence
python3 md2atlassian.py <md_파일> --dry-run --format jira
```

### 예시

```bash
# Confluence 페이지 업로드
python3 md2atlassian.py ./analysis.md \
  "https://wiki.atlassian.com/spaces/SPACE/pages/123456789/페이지+제목"

# Jira 이슈 description 업데이트
python3 md2atlassian.py ./ticket.md \
  "https://jira.atlassian.com/browse/PROJECT-1234"

# dry-run
python3 md2atlassian.py ./analysis.md --dry-run --format confluence
```
