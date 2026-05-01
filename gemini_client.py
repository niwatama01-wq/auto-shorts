"""Gemini API 共通クライアント（リトライ + JSON修復付き）"""
import json
import os
import re
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
    return text


def generate_json(prompt: str, max_tokens: int = 8192, retries: int = 3) -> dict:
    """Gemini API を呼び出し、JSON dict を返す。パース失敗時はリトライ。"""
    client = _get_client()
    last_error = None

    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                ),
            )
            raw = response.text
            fixed = _fix_json(raw)
            return json.loads(fixed)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            print(f"  [gemini] JSON parse error (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2)
                continue
        except Exception as e:
            msg = str(e)
            if "503" in msg or "429" in msg or "UNAVAILABLE" in msg:
                wait = min(30, 10 * (attempt + 1))
                print(f"  [gemini] API error, retrying in {wait}s: {msg[:80]}")
                time.sleep(wait)
                last_error = e
                continue
            raise

    raise RuntimeError(f"Gemini JSON generation failed after {retries} attempts: {last_error}")
