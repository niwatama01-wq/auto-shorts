"""Gemini API 共通クライアント（リトライ + JSON修復付き）"""
import json
import os
import re
import sys
import time

from google import genai
from dotenv import load_dotenv

import config

load_dotenv(config.ROOT / ".env")


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in environment or .env")
    return genai.Client(api_key=api_key)


def _fix_json(text: str) -> str:
    """よくある JSON 破損パターンを修復"""
    text = text.strip()
    # コードフェンス除去
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # JSON部分のみ抽出
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"JSON not found in response: {text[:200]}")
    text = text[start:end + 1]
    # 末尾カンマ除去 (},] や },})
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # 文字列内の生改行をエスケープ（JSON仕様違反の主因）
    # "..." の中に含まれる改行を \\n に変換
    def _escape_newlines_in_strings(s: str) -> str:
        result = []
        in_string = False
        escape_next = False
        for ch in s:
            if escape_next:
                result.append(ch)
                escape_next = False
                continue
            if ch == '\\':
                result.append(ch)
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                continue
            if in_string and ch == '\n':
                result.append('\\n')
                continue
            if in_string and ch == '\r':
                continue
            if in_string and ch == '\t':
                result.append('\\t')
                continue
            result.append(ch)
        return ''.join(result)
    text = _escape_newlines_in_strings(text)
    return text


def generate_json(prompt: str, max_tokens: int = 8192, retries: int = 5) -> dict:
    """Gemini API を呼び出し、JSON dict を返す。パース失敗時はリトライ。"""
    client = _get_client()
    last_error = None
    last_raw = ""

    # Gemini 2.5 系は思考トークンを消費するため明示的に無効化
    # 2.0 系では thinking_config 無視されるので付けても無害
    gen_config_kwargs = {
        "max_output_tokens": max_tokens,
        "response_mime_type": "application/json",
    }
    if "2.5" in config.GEMINI_MODEL:
        gen_config_kwargs["thinking_config"] = genai.types.ThinkingConfig(
            thinking_budget=0
        )

    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=genai.types.GenerateContentConfig(**gen_config_kwargs),
            )
            raw = response.text
            last_raw = raw
            fixed = _fix_json(raw)
            return json.loads(fixed)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            print(f"  [gemini] JSON parse error (attempt {attempt + 1}/{retries}): {e}",
                  file=sys.stderr)
            # デバッグ用: 生レスポンスをファイルに保存
            try:
                debug_path = config.ROOT / f"_debug_gemini_raw_{attempt}.txt"
                debug_path.write_text(last_raw, encoding="utf-8")
                print(f"  [gemini] Raw response saved: {debug_path}",
                      file=sys.stderr)
            except Exception:
                pass
            if attempt < retries - 1:
                time.sleep(3)
                continue
        except Exception as e:
            msg = str(e)
            # retryDelay があれば尊重（無ければデフォルトのバックオフ）
            retry_match = re.search(r"retry in (\d+)", msg)
            if "503" in msg or "UNAVAILABLE" in msg:
                wait = min(30, 10 * (attempt + 1))
            elif "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                wait = int(retry_match.group(1)) + 2 if retry_match else 60
                wait = min(wait, 90)
            else:
                raise
            print(f"  [gemini] API error, retrying in {wait}s: {msg[:120]}",
                  file=sys.stderr)
            time.sleep(wait)
            last_error = e
            continue

    raise RuntimeError(
        f"Gemini JSON generation failed after {retries} attempts: {last_error}\n"
        f"Last raw response (first 500 chars): {last_raw[:500]}"
    )
