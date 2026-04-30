"""auto-shorts オーケストレーター（ジャンル切替対応）

v7変更点:
- --duration 30|45 フラグ追加（45秒尺の試作用）
- ハッシュタグに #FlashNews を追加

使い方:
  python main.py --genre horror "深夜のコンビニで起きた不可解な出来事"
  python main.py --genre ai_news "OpenAIが新モデル発表"
  python main.py --genre ai_news --duration 45 "テスラFSDで大事故"
  python main.py --script output/scripts/horror_20260421_120000.json
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import config
import script_gen
import tts
import image_gen
import video_assemble
import thumbnail_gen
from genres import load_genre, list_genres


def _infer_genre_from_script_path(path: str) -> str:
    stem = Path(path).stem
    m = re.match(r"^([a-z_]+)_\d{8}_\d{6}$", stem)
    if m:
        return m.group(1)
    raise ValueError(
        f"genreを推定できないscriptファイル名: {stem}\n"
        f"  --genre オプションで明示してください"
    )


def run(genre_name: str, theme: str | None = None,
        existing_script_path: str | None = None,
        duration: int | None = None) -> Path:
    config.ensure_dirs()
    genre = load_genre(genre_name)

    if not existing_script_path and not tts.voicevox_alive():
        print(f"❌ VOICEVOX が起動していません ({config.VOICEVOX_HOST})")
        print("   VOICEVOXアプリを起動してから再実行してください")
        sys.exit(1)
    ok, err = image_gen.backend_alive()
    if not ok:
        print(f"❌ 画像バックエンド: {err}")
        sys.exit(1)
    print(f"🖼️ 画像バックエンド: {config.IMAGE_BACKEND}")

    if existing_script_path:
        print(f"📜 既存台本を使用: {existing_script_path}")
        stem = Path(existing_script_path).stem
        m = re.match(r"^[a-z_]+_(\d{8}_\d{6})$", stem)
        ts_from_name = m.group(1) if m else stem
        enriched_path = config.OUT_VIDEOS / ts_from_name / "script.json"
        if enriched_path.exists():
            print(f"   enriched版を発見: {enriched_path}")
            script = json.loads(enriched_path.read_text(encoding="utf-8"))
        else:
            script = json.loads(Path(existing_script_path).read_text(encoding="utf-8"))
        script.setdefault("_meta", {})["timestamp"] = ts_from_name
        script["_meta"]["genre"] = genre.NAME
    else:
        eff_dur = duration if duration is not None else getattr(genre, "DURATION_SEC", 30)
        print(f"📜 [{genre.NAME}] Claude で台本生成中 ({eff_dur}秒尺): {theme}")
        script = script_gen.generate_script(theme, genre, duration=duration)
        print(f"   → {script['_meta']['path']}")
        print(f"   タイトル候補: {script['title_candidates']}")
        print(f"   サムネ煽り: {script['thumbnail_text']}")
        print(f"   シーン数: {len(script['scenes'])}")

        history_path = config.ROOT / "posted_history.json"
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except Exception:
            history = {"posted": []}
        history["posted"].append({
            "posted_at": datetime.now().isoformat(),
            "timestamp": script["_meta"]["timestamp"],
            "title": script.get("title_candidates", [""])[0],
            "theme": (theme or "")[:300],
            "thumbnail_text": script.get("thumbnail_text", ""),
            "duration_sec": script["_meta"].get("duration_sec"),
        })
        history["posted"] = history["posted"][-100:]
        history_path.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"   📚 履歴に記録しました（同ネタは今後選ばれません）")

    ts = script["_meta"]["timestamp"]
    run_dir = config.OUT_VIDEOS / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔊 VOICEVOX で音声生成中（speaker={genre.VOICEVOX_SPEAKER_ID}）...")
    audio_map = tts.synthesize_all(script, run_dir, genre)
    print(f"   → {len(audio_map)} シーン分の音声を生成")

    print(f"🎨 画像生成中（{config.IMAGE_BACKEND}）...")
    image_map = image_gen.generate_all(script, run_dir, genre)
    print(f"   → {len(image_map)} シーン分の画像を生成")

    print("🎬 MoviePy で動画組立中...")
    out_video = run_dir / f"{ts}_shorts.mp4"
    video_assemble.assemble(script, audio_map, image_map, out_video, genre)

    out_thumb = run_dir / f"{ts}_thumb.png"
    if False:  # disabled
        thumbnail_gen.generate_thumbnail(script, image_map, out_thumb, genre)

    # YouTube概要欄
    import web_image_search as _wis
    attrs = script.get("_attributions", [])
    title = script["title_candidates"][0] if script.get("title_candidates") else ""
    hook = script["scenes"][0]["narration"] if script.get("scenes") else ""
    import re as _re
    hook_clean = _re.sub(r"\*\*([^*]+?)\*\*", r"\1", hook).strip()
    theme = script["_meta"].get("theme", "")[:300]
    duration_label = script["_meta"].get("duration_sec", 30)

    sep = "━━━━━━━━━━━━━━━━━━━━"
    desc_lines = [
        f"📡 {title}",
        "",
        sep,
        "  60秒ニュース速報 / Flash News",
        f"  世界の今を、{duration_label}秒で。",
        sep,
        "",
        "▼ 本日のヘッドライン",
        f"　{hook_clean}",
        "",
        "▼ 詳細",
        f"　{theme}",
        "",
        "▼ このチャンネルについて",
        "　世界中のニュースを厳選・要約し、",
        f"　{duration_label}秒の報道調ショートにまとめてお届け。",
        "　テック、経済、政治、エンタメ、国際、社会——",
        "　ジャンル問わず、今この瞬間を速く、客観的に。",
        "",
        "#Shorts #ニュース速報 #30秒 #FlashNews",
        "",
        sep,
    ]
    if attrs:
        desc_lines.append("📸 Photo Credits")
        desc_lines.append(_wis.build_attribution_block(attrs).lstrip("\n").lstrip("🖼️ Image Credits:\n"))
        desc_lines.append("")
        desc_lines.append(sep)

    (run_dir / "youtube_description.txt").write_text(
        "\n".join(desc_lines), encoding="utf-8"
    )

    (run_dir / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"\n✅ 完成: {out_video}")
    print(f"🖼️  サムネ下書き: {out_thumb}")
    print(f"   作業ディレクトリ: {run_dir}")
    print(f"\n📌 タイトル候補:")
    for t in script["title_candidates"]:
        print(f"   - {t}")
    print(f"📌 サムネ煽り文: {script['thumbnail_text']}")
    if script.get("thumbnail_number"):
        print(f"📌 サムネ大数字: {script['thumbnail_number']}")
    print(f"\n💡 次のステップ:")
    print(f"   1. 動画を確認 → 必要なら台本を手直しして --script で再生成")
    print(f"   2. サムネを Canva 等で手作り（CTR半減リスクなので必須手動）")
    print(f"   3. タイトル選定")
    print(f"   4. YouTube Shorts として投稿")
    return out_video


def main():
    parser = argparse.ArgumentParser(description="auto-shorts ジャンル別Shorts自動生成")
    parser.add_argument("theme", nargs="?", help="台本のテーマ")
    parser.add_argument("--genre", choices=list_genres(),
                        help=f"ジャンル: {', '.join(list_genres())}")
    parser.add_argument("--script", help="既存台本JSONから再生成（genreはファイル名から推定）")
    parser.add_argument("--duration", type=int, choices=[30, 45], default=None,
                        help="動画尺（秒）。デフォルトはジャンル設定 (ai_news=30)")
    args = parser.parse_args()

    if not args.theme and not args.script:
        parser.print_help()
        sys.exit(1)

    if args.script and not args.genre:
        args.genre = _infer_genre_from_script_path(args.script)
    if not args.genre:
        print("❌ --genre を指定してください（例: --genre ai_news）")
        sys.exit(1)

    run(genre_name=args.genre, theme=args.theme,
        existing_script_path=args.script, duration=args.duration)


if __name__ == "__main__":
    main()
