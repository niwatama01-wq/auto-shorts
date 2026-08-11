"""YouTube Data API v3 で動画＋サムネを自動アップロード。

初回: `python youtube_upload.py <run_dir>` でブラウザが開き、
      Googleアカウントへの権限を許可すると token.json が保存される。
2回目以降: 同コマンドで自動アップロード。

例:
  python youtube_upload.py output/videos/20260421_192456 --privacy private --title-index 0
  python youtube_upload.py output/videos/20260421_192456 --privacy unlisted --schedule "2026-04-22T19:00:00+09:00"
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

CLIENT_SECRET = config.ROOT / "client_secret.json"
TOKEN_PATH = config.ROOT / "token.json"

CATEGORY_SCIENCE_TECH = "28"   # YouTube Category ID: 科学と技術
DEFAULT_TAGS = ["AIニュース", "AI", "生成AI", "ニュース解説", "テクノロジー", "日本経済", "Shorts", "藍のAI速報"]

# entity → 検索タグ（動画の中身に沿った動的タグ＝SEO。静的タグだけでは検索/関連に乗らない）
ENTITY_TAG_MAP = {
    "openai": "OpenAI", "anthropic": "Anthropic", "google": "Google",
    "microsoft": "Microsoft", "meta": "Meta", "apple": "Apple",
    "amazon": "Amazon", "nvidia": "NVIDIA", "tesla": "Tesla", "samsung": "Samsung",
    "claude": "Claude", "gpt": "GPT", "chatgpt": "ChatGPT", "gemini": "Gemini",
    "china": "中国AI", "usa": "アメリカ", "japan": "日本",
}


def _derive_tags(script: dict) -> list[str]:
    """台本の各シーンentityから、動画の中身に沿ったタグを生成する。"""
    out = []
    for sc in (script.get("scenes") or []):
        e = (sc.get("entity") or "").lower()
        tag = ENTITY_TAG_MAP.get(e)
        if tag and tag not in out:
            out.append(tag)
    return out


def get_authenticated_service():
    """OAuth 認証。初回はブラウザで同意、2回目以降は token.json を使う"""
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET.exists():
                raise RuntimeError(f"client_secret.json not found at {CLIENT_SECRET}")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent")
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        print(f"   token saved to {TOKEN_PATH}")
    return build("youtube", "v3", credentials=creds)


def _load_run(run_dir: Path) -> dict:
    """run_dirから必要なメタを収集"""
    ts = run_dir.name
    video = run_dir / f"{ts}_shorts.mp4"
    thumb = run_dir / f"{ts}_thumb.png"
    script_path = run_dir / "script.json"
    desc_path = run_dir / "youtube_description.txt"

    if not video.exists():
        raise FileNotFoundError(f"video not found: {video}")
    if not script_path.exists():
        raise FileNotFoundError(f"script.json not found: {script_path}")

    script = json.loads(script_path.read_text(encoding="utf-8"))
    description = (
        desc_path.read_text(encoding="utf-8") if desc_path.exists() else ""
    )
    return {
        "ts": ts,
        "video": video,
        "thumb": thumb if thumb.exists() else None,
        "script": script,
        "description": description,
        "run_dir": run_dir,
    }


def _build_body(run: dict, title: str, privacy: str,
                schedule_iso: str | None, extra_tags: list[str]) -> dict:
    dynamic = _derive_tags(run.get("script") or {})
    tags = []
    for t in list(DEFAULT_TAGS) + dynamic + list(extra_tags):
        if t and t not in tags:
            tags.append(t)
    # Shortsとして検出されやすくするため #Shorts を description に追加
    desc = run["description"] or ""
    if "#Shorts" not in desc and "#shorts" not in desc:
        desc = desc + "\n\n#Shorts #AIニュース #日本"

    body = {
        "snippet": {
            "title": title[:100],      # YouTubeタイトル上限100字
            "description": desc[:5000],
            "tags": tags[:500],
            "categoryId": CATEGORY_SCIENCE_TECH,
            "defaultLanguage": "ja",
            "defaultAudioLanguage": "ja",
        },
        "status": {
            "privacyStatus": privacy,   # private / unlisted / public
            "selfDeclaredMadeForKids": False,
            "madeForKids": False,
        },
    }
    if schedule_iso and privacy == "private":
        # 予約公開: status.publishAt を RFC3339 形式でセット。privacyはprivateのまま
        body["status"]["publishAt"] = schedule_iso
    return body


def upload(run: dict, title: str, privacy: str, schedule_iso: str | None = None,
           extra_tags: list[str] | None = None) -> dict:
    """動画アップロード + サムネ設定"""
    yt = get_authenticated_service()
    body = _build_body(run, title, privacy, schedule_iso, extra_tags or [])

    print(f"📤 動画アップロード開始: {run['video'].name}")
    media = MediaFileUpload(str(run["video"]),
                             chunksize=-1, resumable=True,
                             mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        try:
            status, response = req.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"   uploading... {pct}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504):
                print(f"   transient error {e.resp.status}, retrying in 5s...")
                time.sleep(5)
                continue
            raise
    video_id = response["id"]
    print(f"✅ アップ完了: https://youtu.be/{video_id}")

    # サムネ設定（失敗してもメインは成功扱いにする）
    # サムネファイルが存在する場合のみ実行（生成スキップ時はNone）
    if run["thumb"] and run["thumb"].exists():
        print(f"🖼️  サムネ設定中: {run['thumb'].name}")
        try:
            thumb_path = run["thumb"]
            # YouTube サムネは 2MB上限。超過なら自動圧縮
            max_bytes = 2 * 1024 * 1024
            if thumb_path.stat().st_size > max_bytes:
                from PIL import Image
                compressed = thumb_path.with_suffix(".compressed.jpg")
                img = Image.open(thumb_path).convert("RGB")
                quality = 85
                while quality >= 30:
                    img.save(compressed, "JPEG", quality=quality, optimize=True)
                    if compressed.stat().st_size <= max_bytes:
                        break
                    quality -= 10
                print(f"   2MB超のため圧縮: {thumb_path.stat().st_size//1024}KB → {compressed.stat().st_size//1024}KB (q={quality})")
                thumb_path = compressed
            yt.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumb_path)),
            ).execute()
            print("   サムネ設定完了")
        except Exception as e:
            print(f"   ⚠️  サムネ設定スキップ: {e}")
            print("   （電話番号認証 https://www.youtube.com/verify が未実施の可能性）")

    return {"video_id": video_id, "url": f"https://youtu.be/{video_id}"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run_dir", help="output/videos/<timestamp> のディレクトリ")
    p.add_argument("--privacy", choices=["private", "unlisted", "public"],
                   default="private",
                   help="公開設定（デフォルト: private 安全のため）")
    p.add_argument("--title-index", type=int, default=0,
                   help="script.json の title_candidates の index（0=最初）")
    p.add_argument("--title", help="タイトルを直接指定（--title-indexより優先）")
    p.add_argument("--schedule",
                   help="予約公開時刻（RFC3339、例: 2026-04-22T19:00:00+09:00）")
    p.add_argument("--tags", nargs="*", default=[], help="追加タグ")
    args = p.parse_args()

    run_dir = Path(args.run_dir).resolve()
    run = _load_run(run_dir)

    if args.title:
        title = args.title
    else:
        cands = run["script"].get("title_candidates") or []
        if not cands:
            raise RuntimeError("タイトル候補なし。--title で明示してください")
        title = cands[min(args.title_index, len(cands) - 1)]

    print(f"📜 タイトル: {title}")
    print(f"🔒 公開設定: {args.privacy}")
    if args.schedule:
        print(f"⏰ 予約公開: {args.schedule}")

    result = upload(run, title, args.privacy, args.schedule, args.tags)
    print(f"\n🎉 完了: {result['url']}")


if __name__ == "__main__":
    main()
