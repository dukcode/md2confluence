#!/usr/bin/env python3
"""
Markdown -> Atlassian (Confluence 페이지 / Jira 이슈 description) 업로드 스크립트

URL 패턴으로 대상을 자동 분기한다:
    /pages/<id>          → Confluence 페이지
    /browse/<KEY>-<num>  → Jira 이슈

사용법:
    python3 md2atlassian.py <md_file> <url>
    python3 md2atlassian.py <md_file> --dry-run --format {confluence,jira}

예시:
    python3 md2atlassian.py ./doc.md "https://wiki.atlassian.com/spaces/SPACE/pages/123456789/페이지+제목"
    python3 md2atlassian.py ./doc.md "https://jira.atlassian.com/browse/PROJECT-1234"
    python3 md2atlassian.py ./doc.md --dry-run --format confluence

환경변수:
    MD2CONFLUENCE_TOKEN  - Confluence Personal Access Token
    MD2JIRA_TOKEN        - Jira Personal Access Token
                          (대상에 따라 필요한 것만 설정하면 됨)
                          발급: 각 제품 프로필 설정 → Personal Access Tokens
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import ssl


TOKEN_ENV = {
    "confluence": "MD2CONFLUENCE_TOKEN",
    "jira": "MD2JIRA_TOKEN",
}


def detect_target(url: str) -> str:
    """URL에서 대상(confluence/jira)을 판별한다."""
    if "/browse/" in url:
        return "jira"
    if "/pages/" in url:
        return "confluence"
    print(f"ERROR: URL에서 대상을 판별할 수 없습니다: {url}", file=sys.stderr)
    print("       Confluence: .../pages/<id>/...", file=sys.stderr)
    print("       Jira:       .../browse/<KEY>-<num>", file=sys.stderr)
    sys.exit(1)


def parse_confluence_url(url: str) -> tuple[str, str]:
    """Confluence URL에서 base_url과 page_id를 추출한다."""
    parsed = urllib.parse.urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    match = re.search(r"/pages/(\d+)", parsed.path)
    if not match:
        print(f"ERROR: URL에서 page ID를 찾을 수 없습니다: {url}", file=sys.stderr)
        sys.exit(1)

    return base_url, match.group(1)


def parse_jira_url(url: str) -> tuple[str, str]:
    """Jira URL에서 base_url과 issue key를 추출한다."""
    parsed = urllib.parse.urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    match = re.search(r"/browse/([A-Z][A-Z0-9_]+-\d+)", parsed.path)
    if not match:
        print(f"ERROR: URL에서 issue key를 찾을 수 없습니다: {url}", file=sys.stderr)
        sys.exit(1)

    return base_url, match.group(1)


def preprocess_markdown(md: str) -> str:
    """공통 Markdown 전처리."""
    # 헤딩의 섹션 번호 제거 (예: "## 2.1 제목" → "## 제목")
    md = re.sub(r"^(#{1,6})\s+\d+(?:\.\d+)*\.?\s+", r"\1 ", md, flags=re.MULTILINE)
    # bold 텍스트 직후 리스트가 오는 경우 빈 줄 삽입
    md = re.sub(r"(\*\*[^*]+:\*\*)\n(- )", r"\1\n\n\2", md)
    # 백슬래시+공백 → pandoc이 non-breaking space로 해석하므로 이스케이프
    md = re.sub(r"\\(?= )", r"\\\\", md)
    # mermaid → 일반 코드 블록 (Confluence/Jira 모두 미지원)
    md = re.sub(r"```mermaid", "```", md)
    return md


def run_pandoc(md: str, to_format: str, extra_args: list[str] | None = None) -> str:
    """pandoc으로 Markdown 변환."""
    cmd = ["pandoc", "-f", "markdown", "-t", to_format, "--wrap=none"]
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(cmd, input=md, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: pandoc 실행 실패: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def md_to_confluence(md_path: str) -> str:
    """Markdown 파일 → Confluence storage format."""
    with open(md_path, "r", encoding="utf-8") as f:
        md = preprocess_markdown(f.read())

    html = run_pandoc(md, "html", ["--no-highlight"])

    # 코드 블록 → Confluence code 매크로
    def replace_code_block(match):
        lang = ""
        class_match = re.search(r'class="(?:language-)?(\w+)', match.group(0))
        if class_match:
            lang = class_match.group(1)

        code = re.search(r"<code[^>]*>(.*?)</code>", match.group(0), re.DOTALL)
        if not code:
            return match.group(0)

        content = code.group(1)
        for old, new in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")]:
            content = content.replace(old, new)

        lang_param = f'<ac:parameter ac:name="language">{lang}</ac:parameter>' if lang else ""
        return (
            f'<ac:structured-macro ac:name="code">{lang_param}'
            f'<ac:parameter ac:name="linenumbers">false</ac:parameter>'
            f"<ac:plain-text-body><![CDATA[{content}]]></ac:plain-text-body>"
            f"</ac:structured-macro>"
        )

    html = re.sub(r"<pre[^>]*><code[^>]*>.*?</code></pre>", replace_code_block, html, flags=re.DOTALL)

    # h1 제거 (Confluence 페이지 제목과 중복)
    html = re.sub(r"<h1[^>]*>.*?</h1>\n?", "", html)

    # blockquote → Confluence info 매크로
    def replace_blockquote(match):
        inner = match.group(1)
        return (
            f'<ac:structured-macro ac:name="info">'
            f"<ac:rich-text-body>{inner}</ac:rich-text-body>"
            f"</ac:structured-macro>"
        )

    html = re.sub(r"<blockquote>\n?(.*?)\n?</blockquote>", replace_blockquote, html, flags=re.DOTALL)

    return html


def md_to_jira(md_path: str) -> str:
    """Markdown 파일 → Jira wiki markup."""
    with open(md_path, "r", encoding="utf-8") as f:
        md = preprocess_markdown(f.read())

    body = run_pandoc(md, "jira")

    # 첫 h1 제거 (Jira 이슈 summary와 중복)
    body = re.sub(r"\Ah1\.\s.*\n+", "", body)

    return body


def get_confluence_page_info(base_url: str, page_id: str, token: str) -> dict:
    url = f"{base_url}/rest/api/content/{page_id}?expand=version,space"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read().decode())


def upload_confluence(base_url: str, page_id: str, token: str, body_html: str,
                      title: str, space_key: str, version: int) -> dict:
    url = f"{base_url}/rest/api/content/{page_id}"
    payload = json.dumps({
        "id": page_id,
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "body": {"storage": {"value": body_html, "representation": "storage"}},
        "version": {"number": version + 1},
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")

    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read().decode())


def get_jira_issue_info(base_url: str, issue_key: str, token: str) -> dict:
    url = f"{base_url}/rest/api/2/issue/{issue_key}?fields=summary"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read().decode())


def update_jira_description(base_url: str, issue_key: str, token: str, body: str) -> int:
    url = f"{base_url}/rest/api/2/issue/{issue_key}"
    payload = json.dumps({"fields": {"description": body}}).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")

    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx) as resp:
        return resp.status


def run_confluence(url: str, body_html: str, token: str):
    base_url, page_id = parse_confluence_url(url)
    print(f"페이지 조회 중: {page_id}")
    info = get_confluence_page_info(base_url, page_id, token)
    title = info["title"]
    space_key = info["space"]["key"]
    version = info["version"]["number"]
    print(f"  제목: {title}")
    print(f"  현재 버전: {version}")

    print("업로드 중...")
    result = upload_confluence(base_url, page_id, token, body_html, title, space_key, version)
    new_version = result["version"]["number"]
    result_url = f"{result['_links']['base']}{result['_links']['webui']}"
    print(f"완료! (v{version} → v{new_version})")
    print(f"URL: {result_url}")


def run_jira(url: str, body: str, token: str):
    base_url, issue_key = parse_jira_url(url)
    print(f"이슈 조회 중: {issue_key}")
    info = get_jira_issue_info(base_url, issue_key, token)
    summary = info["fields"]["summary"]
    print(f"  제목: {summary}")

    print("업데이트 중...")
    update_jira_description(base_url, issue_key, token, body)
    print("완료!")
    print(f"URL: {base_url}/browse/{issue_key}")


def main():
    parser = argparse.ArgumentParser(description="Markdown -> Atlassian(Confluence/Jira) 업로드")
    parser.add_argument("md_file", help="변환할 Markdown 파일 경로")
    parser.add_argument("url", nargs="?", help="대상 URL (Confluence 페이지 또는 Jira 이슈, --dry-run 시 생략 가능)")
    parser.add_argument("--dry-run", action="store_true", help="변환만 하고 업로드하지 않음 (결과를 stdout에 출력)")
    parser.add_argument("--format", choices=["confluence", "jira"],
                        help="dry-run 시 URL 없이 변환 포맷 지정")
    args = parser.parse_args()

    if not os.path.isfile(args.md_file):
        print(f"ERROR: 파일을 찾을 수 없습니다: {args.md_file}", file=sys.stderr)
        sys.exit(1)

    # pandoc 확인
    if subprocess.run(["which", "pandoc"], capture_output=True).returncode != 0:
        print("ERROR: pandoc이 설치되어 있지 않습니다. brew install pandoc", file=sys.stderr)
        sys.exit(1)

    # 대상 결정
    if args.url:
        target = detect_target(args.url)
    elif args.dry_run and args.format:
        target = args.format
    elif args.dry_run:
        parser.error("dry-run 시 URL이 없으면 --format 옵션이 필요합니다")
    else:
        parser.error("URL은 필수입니다 (--dry-run 시에만 생략 가능)")

    # 토큰 확인
    token_env = TOKEN_ENV[target]
    token = os.environ.get(token_env, "")
    if not token and not args.dry_run:
        print(f"ERROR: {token_env} 환경변수를 설정해주세요.", file=sys.stderr)
        print(f"       export {token_env}='your-token-here'", file=sys.stderr)
        sys.exit(1)

    # 변환
    print(f"변환 중: {args.md_file} (대상: {target})")
    if target == "confluence":
        body = md_to_confluence(args.md_file)
    else:
        body = md_to_jira(args.md_file)
    print(f"변환 완료 ({len(body):,} bytes)")

    if args.dry_run:
        print("--- dry-run: 변환 결과 ---")
        print(body)
        return

    if target == "confluence":
        run_confluence(args.url, body, token)
    else:
        run_jira(args.url, body, token)


if __name__ == "__main__":
    main()
