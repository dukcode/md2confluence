# md2confluence

Markdown 파일을 Confluence 페이지로 변환·업로드하는 스크립트.

## 왜?

Confluence의 Markdown 매크로 블록은 테이블, 코드 블록 언어 감지, 중첩 구조 등에서 렌더링이 불완전하다.
이 스크립트는 Markdown을 Confluence 네이티브 storage format으로 변환하므로 이런 제약이 없다.

## 의존성

### 외부

| 이름 | 용도 | 설치 |
|---|---|---|
| Python 3.10+ | 스크립트 실행 | macOS 기본 포함 또는 `brew install python` |
| [pandoc](https://pandoc.org/) | Markdown → HTML 변환 | `brew install pandoc` |

## Confluence PAT 발급

1. Confluence 접속
2. 우측 상단 **프로필 아이콘** → **설정(Settings)**
3. 좌측 메뉴 **Personal Access Tokens** 선택
4. **Create token** → 이름 입력 → 생성
5. 토큰 복사 후 환경변수에 등록:

```bash
# 영구 등록 (~/.zshenv 또는 ~/.zshrc에 추가 후 source)
echo "export MD2CONFLUENCE_TOKEN='발급받은_토큰'" >> ~/.zshenv
source ~/.zshenv

# 임시 등록 (현재 터미널 세션에서만 유효)
export MD2CONFLUENCE_TOKEN='발급받은_토큰'
```

## 사용법

> 이 스크립트는 기존 페이지의 내용을 덮어쓰는 방식입니다.
> 새 글을 작성하려면 Confluence에서 **빈 페이지를 먼저 생성**한 뒤, 해당 페이지 URL을 인자로 넣어주세요.

```bash
# 기본 사용
python3 md2confluence.py <md_파일> <confluence_페이지_url>

# 변환 결과만 확인 (업로드 안 함, URL 생략 가능)
python3 md2confluence.py <md_파일> --dry-run
```

### 예시

```bash
# 업로드
python3 md2confluence.py ./analysis.md \
  "https://your-domain.atlassian.net/wiki/spaces/SPACE/pages/123456789/페이지+제목"

# dry-run (URL 없이 변환 결과만 확인)
python3 md2confluence.py ./analysis.md --dry-run
```

