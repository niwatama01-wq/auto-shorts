"""Gemini API でジャンル別 Shorts 台本（JSON）を生成

v8変更点:
- Claude API → Gemini API に移行
- google-genai SDK を使用（gemini_client 経由、リトライ+JSON修復付き）

使い方:
  python main.py --genre horror "深夜のコンビニで起きた不可解な出来事"
  python main.py --genre ai_news "OpenAIが新モデル発表"
"""
import json
from datetime import datetime

import config
import gemini_client


def _format_prompt(template: str, theme: str, duration: int) -> str:
    """duration 対応のプロンプト整形。
    旧テンプレ (theme のみ受ける) との後方互換のため、
    プレースホルダー有無を見て分岐する。"""
    has_duration = "{duration}" in template
    if not has_duration:
        return template.format(theme=theme)
    # duration から各種数値を導出
    # 1秒あたり ~5字、scene 1個 ~3秒
    min_chars = int(duration * 5)
    max_chars = int(duration * 7)
    min_scenes = max(5, int(duration * 0.23))
    max_scenes = max(7, int(duration * 0.30))
    return template.format(
        theme=theme,
        duration=duration,
        min_chars=min_chars,
        max_chars=max_chars,
        min_scenes=min_scenes,
        max_scenes=max_scenes,
    )


def generate_script(theme: str, genre, duration: int | None = None) -> dict:
    """テーマとジャンルから台本JSONを生成して返す。同時にファイル保存。

    duration: 動画尺（秒）。Noneなら genre.DURATION_SEC、それも無ければ 30。
    """
    if duration is None:
        duration = getattr(genre, "DURATION_SEC", 30)

    prompt = _format_prompt(genre.PROMPT_TEMPLATE, theme, duration)
    max_tokens = getattr(genre, "GEMINI_MAX_TOKENS", config.GEMINI_MAX_TOKENS)
    script = gemini_client.generate_json(prompt, max_tokens=max_tokens)

    config.ensure_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = config.OUT_SCRIPTS / f"{genre.NAME}_{ts}.json"
    out_path.write_text(
        json.dumps(script, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    script["_meta"] = {
        "timestamp": ts,
        "path": str(out_path),
        "theme": theme,
        "genre": genre.NAME,
        "duration_sec": duration,
    }
    return script


if __name__ == "__main__":
    import sys
    from genres import load_genre
    genre_name = sys.argv[1] if len(sys.argv) > 1 else "horror"
    theme = sys.argv[2] if len(sys.argv) > 2 else "テスト"
    dur = int(sys.argv[3]) if len(sys.argv) > 3 else None
    g = load_genre(genre_name)
    s = generate_script(theme, g, duration=dur)
    print(f"Generated: {s['_meta']['path']}")
    print(f"Title candidates: {s['title_candidates']}")
    print(f"Scenes: {len(s['scenes'])}")
    print(f"Duration: {s['_meta'].get('duration_sec')}秒")
