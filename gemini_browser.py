"""Gemini Web (gemini.google.com) 経由で JSON レスポンスを取得

Cookie 認証で Gemini Web アプリを操作。API レート制限を回避できるが
- 応答が遅い（30秒〜数分/呼び出し）
- Cookie が定期的に失効するため再エクスポートが必要
- UI 変更で動作不能になる可能性あり
"""
import json
import os
import re
import sys
import time

from dotenv import load_dotenv

import config

load_dotenv(config.ROOT / ".env")

# 同一プロセス内で使い回す Playwright セッション（高速化のため）
_session = None


def _start_session():
    """Playwright + Chromium + Cookie で認証済みページを返す"""
    from playwright.sync_api import sync_playwright

    cookies_json = os.environ.get("GEMINI_COOKIES_JSON")
    if not cookies_json:
        raise RuntimeError("GEMINI_COOKIES_JSON not set in environment or .env")

    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    )
    context.set_default_timeout(180000)

    cookies = json.loads(cookies_json)
    formatted = []
    for c in cookies:
        item = {
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain"),
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
        }
        if "expires" in c:
            item["expires"] = c["expires"]
        if "httpOnly" in c:
            item["httpOnly"] = c["httpOnly"]
        if "sameSite" in c and c["sameSite"] in ["Strict", "Lax", "None"]:
            item["sameSite"] = c["sameSite"]
        formatted.append(item)
    context.add_cookies(formatted)

    page = context.new_page()
    page.goto(
        "https://gemini.google.com/app",
        wait_until="domcontentloaded",
        timeout=120000,
    )
    time.sleep(15)
    return p, browser, context, page


def _close_session():
    global _session
    if _session is None:
        return
    try:
        _session[1].close()
    except Exception:
        pass
    try:
        _session[0].stop()
    except Exception:
        pass
    _session = None


def _new_chat(page):
    """新しい会話を開始（前のコンテキストを引きずらないため）"""
    try:
        # 「新しいチャット」ボタンを探す
        for sel in [
            "button[aria-label*='新しい']",
            "button[aria-label*='New chat']",
            "[data-test-id='new-chat-button']",
        ]:
            btn = page.query_selector(sel)
            if btn:
                btn.click()
                time.sleep(3)
                return
        # フォールバック: トップページに再ナビゲーション
        page.goto(
            "https://gemini.google.com/app",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        time.sleep(8)
    except Exception:
        pass


def _send_prompt(page, prompt: str) -> str:
    """ブラウザでプロンプトを送信し、レスポンスを返す"""
    textarea = page.query_selector("textarea, div[contenteditable='true']")
    if textarea is None:
        raise RuntimeError(
            "Gemini textarea not found - Cookie が失効した可能性があります"
        )

    tag_name = textarea.evaluate("el => el.tagName.toLowerCase()")
    if tag_name == "textarea":
        page.evaluate(
            """(args) => {
                const el = document.querySelector('textarea');
                if (el) {
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    ).set;
                    setter.call(el, args.text);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }""",
            {"text": prompt},
        )
    else:
        page.evaluate(
            """(args) => {
                const el = document.querySelector('div[contenteditable=true]');
                if (el) {
                    el.innerText = args.text;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }""",
            {"text": prompt},
        )

    time.sleep(2)
    page.keyboard.press("Enter")

    # 生成完了を待つ（停止ボタンが消えるまで、最大 5 分）
    time.sleep(10)
    for _ in range(25):
        time.sleep(8)
        stop_button = page.query_selector(
            "button[aria-label*='停止'], button[aria-label*='Stop']"
        )
        if not stop_button:
            time.sleep(5)
            break

    selectors = [
        "model-response",
        ".model-response-text",
        ".message-content",
        "[data-message-author-role='model']",
        ".markdown",
    ]
    for selector in selectors:
        responses = page.query_selector_all(selector)
        if responses:
            candidate = responses[-1].inner_text()
            if candidate and len(candidate.strip()) > 30:
                return candidate

    raise RuntimeError("Gemini からの応答取得に失敗")


def _extract_json(text: str) -> str:
    """Gemini Web の Markdown 出力から JSON 部分を抽出"""
    text = text.strip()
    # ```json ... ``` を抽出
    match = re.search(r"```(?:json)?\s*\n?(.+?)\n?```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    # JSON 部分（最外の {} ）のみ
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"JSON not found in response: {text[:200]}")
    text = text[start : end + 1]
    # 末尾カンマ除去
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def generate_json(prompt: str, max_tokens: int = 8192, retries: int = 2) -> dict:
    """Gemini Web 経由で JSON dict を取得（gemini_client と同じシグネチャ）

    max_tokens は無視される（Web 版は制御不可）。"""
    global _session

    json_prompt = (
        prompt
        + "\n\n【絶対遵守】回答は **純粋な JSON のみ** で返してください。"
        "前後の説明文・コードフェンス・思考過程は一切禁止。"
        "JSON は { から始まり } で終わる完結した形にしてください。"
    )

    last_error = None
    for attempt in range(retries):
        try:
            if _session is None:
                print(
                    "  [gemini-browser] Playwright セッション開始中...",
                    file=sys.stderr,
                )
                _session = _start_session()

            _, _, _, page = _session
            _new_chat(page)
            raw = _send_prompt(page, json_prompt)

            # デバッグ用に保存
            try:
                debug_path = config.ROOT / f"_debug_gemini_browser_{attempt}.txt"
                debug_path.write_text(raw, encoding="utf-8")
            except Exception:
                pass

            fixed = _extract_json(raw)
            return json.loads(fixed)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            print(
                f"  [gemini-browser] JSON parse error "
                f"(attempt {attempt + 1}/{retries}): {e}",
                file=sys.stderr,
            )
            if attempt < retries - 1:
                time.sleep(5)
                continue
        except Exception as e:
            last_error = e
            print(
                f"  [gemini-browser] Error "
                f"(attempt {attempt + 1}/{retries}): {e}",
                file=sys.stderr,
            )
            _close_session()
            if attempt < retries - 1:
                time.sleep(5)
                continue

    raise RuntimeError(
        f"Gemini browser generation failed after {retries} attempts: {last_error}"
    )


def cleanup():
    """プロセス終了時のクリーンアップ用"""
    _close_session()


import atexit  # noqa: E402

atexit.register(cleanup)
