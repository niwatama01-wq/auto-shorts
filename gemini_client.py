"""Gemini ディスパッチャー

config.GEMINI_BACKEND に応じて、API またはブラウザ経由で Gemini を呼び分ける。
script_gen.py / news_fetcher.py からはこのモジュール経由で利用する。
"""
import config


def generate_json(prompt: str, max_tokens: int = 8192, retries: int = 5) -> dict:
    backend = getattr(config, "GEMINI_BACKEND", "api")

    if backend == "browser":
        import gemini_browser
        return gemini_browser.generate_json(
            prompt, max_tokens=max_tokens, retries=max(2, retries - 2)
        )
    elif backend == "api":
        import gemini_api
        return gemini_api.generate_json(
            prompt, max_tokens=max_tokens, retries=retries
        )
    else:
        raise ValueError(f"Unknown GEMINI_BACKEND: {backend}")
