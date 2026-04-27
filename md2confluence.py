#!/usr/bin/env python3
"""
Markdown -> Confluence 페이지 업로드 스크립트

사용법:
    python3 md2confluence.py <md_file> <confluence_page_url>
    python3 md2confluence.py <md_file> --dry-run

예시:
    python3 md2confluence.py ./doc.md "https://wiki.atlassian.com/spaces/SPACE/pages/123456789/페이지+제목"
    python3 md2confluence.py ./doc.md --dry-run

환경변수:
    MD2CONFLUENCE_TOKEN  - Confluence Personal Access Token (필수)
                        발급: Confluence 프로필 설정 → Personal Access Tokens
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


def parse_confluence_url(url: str) -> tuple[str, str]:
    """Confluence URL에서 base_url과 page_id를 추출한다."""
    parsed = urllib.parse.urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    match = re.search(r"/pages/(\d+)", parsed.path)
    if not match:
        print(f"ERROR: URL에서 page ID를 찾을 수 없습니다: {url}", file=sys.stderr)
        print("       URL 형식: https://wiki.example.com/spaces/SPACE/pages/12345/...", file=sys.stderr)
        sys.exit(1)

    return base_url, match.group(1)


def get_page_info(base_url: str, page_id: str, token: str) -> dict:
    """현재 페이지 정보(title, version, space key)를 조회한다."""
    url = f"{base_url}/rest/api/content/{page_id}?expand=version,space"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")

    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read().decode())


def md_to_html(md_path: str) -> str:
    """Markdown 파일을 pandoc으로 HTML 변환 후 Confluence 매크로로 후처리한다."""
    with open(md_path, "r", encoding="utf-8") as f:
        md = f.read()

    # 전처리: 헤딩의 섹션 번호 제거 (예: "## 2.1 제목" → "## 제목")
    # 제거 대상: "1.", "2.1", "3.2.1" 등 숫자+점 조합 뒤에 공백이 오는 패턴
    # 비대상: "# 2024년 회고" 같이 숫자 뒤에 공백 없이 바로 글자가 오는 경우
    md = re.sub(r"^(#{1,6})\s+\d+(?:\.\d+)*\.?\s+", r"\1 ", md, flags=re.MULTILINE)

    # 전처리: bold 텍스트 직후 리스트가 오는 경우 빈 줄 삽입
    md = re.sub(r"(\*\*[^*]+:\*\*)\n(- )", r"\1\n\n\2", md)

    # 백슬래시+공백 → pandoc이 non-breaking space로 해석하므로 이스케이프
    md = re.sub(r"\\(?= )", r"\\\\", md)

    # mermaid → 일반 코드 블록 (Confluence 미지원)
    md = re.sub(r"```mermaid", "```", md)

    result = subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "html", "--wrap=none", "--no-highlight"],
        input=md,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: pandoc 실행 실패: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    html = result.stdout

    # 코드 블록 → Confluence code 매크로
    def replace_code_block(match):
        lang = ""
        # --no-highlight: class가 <pre>에 붙음 (예: <pre class="json">)
        # highlight: class가 <code>에 붙음 (예: <code class="language-json">)
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


def upload(base_url: str, page_id: str, token: str, body_html: str, title: str, space_key: str, version: int):
    """Confluence REST API로 페이지를 업데이트한다."""
    url = f"{base_url}/rest/api/content/{page_id}"
    payload = json.dumps({
        "id": page_id,
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "body": {
            "storage": {
                "value": body_html,
                "representation": "storage",
            }
        },
        "version": {"number": version + 1},
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")

    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read().decode())


def main():
    parser = argparse.ArgumentParser(description="Markdown -> Confluence 업로드")
    parser.add_argument("md_file", help="변환할 Markdown 파일 경로")
    parser.add_argument("confluence_url", nargs="?", help="Confluence 페이지 URL (--dry-run 시 생략 가능)")
    parser.add_argument("--dry-run", action="store_true", help="변환만 하고 업로드하지 않음 (결과를 stdout에 출력)")
    args = parser.parse_args()

    if not args.dry_run and not args.confluence_url:
        parser.error("confluence_url은 필수입니다 (--dry-run 시에만 생략 가능)")

    if not os.path.isfile(args.md_file):
        print(f"ERROR: 파일을 찾을 수 없습니다: {args.md_file}", file=sys.stderr)
        sys.exit(1)

    # pandoc 확인
    if subprocess.run(["which", "pandoc"], capture_output=True).returncode != 0:
        print("ERROR: pandoc이 설치되어 있지 않습니다. brew install pandoc", file=sys.stderr)
        sys.exit(1)

    token = os.environ.get("MD2CONFLUENCE_TOKEN", "")
    if not token and not args.dry_run:
        print("ERROR: MD2CONFLUENCE_TOKEN 환경변수를 설정해주세요.", file=sys.stderr)
        print("       export MD2CONFLUENCE_TOKEN='your-token-here'", file=sys.stderr)
        sys.exit(1)

    # 변환
    print(f"변환 중: {args.md_file}")
    body_html = md_to_html(args.md_file)
    print(f"변환 완료 ({len(body_html):,} bytes)")

    if args.dry_run:
        print("--- dry-run: 변환 결과 ---")
        print(body_html)
        return

    base_url, page_id = parse_confluence_url(args.confluence_url)

    # 페이지 정보 조회
    print(f"페이지 조회 중: {page_id}")
    page_info = get_page_info(base_url, page_id, token)
    title = page_info["title"]
    space_key = page_info["space"]["key"]
    version = page_info["version"]["number"]
    print(f"  제목: {title}")
    print(f"  현재 버전: {version}")

    # 업로드
    print("업로드 중...")
    result = upload(base_url, page_id, token, body_html, title, space_key, version)
    new_version = result["version"]["number"]
    result_url = f"{result['_links']['base']}{result['_links']['webui']}"
    print(f"완료! (v{version} → v{new_version})")
    print(f"URL: {result_url}")


if __name__ == "__main__":
    main()
