"""ローカルで1回だけ実行: yt-analytics スコープを含む token.json を再生成。

既存の token.json は YouTube upload 用スコープのみで、
Analytics API (`yt-analytics.readonly`) は呼べない。
このスクリプトで再認証し、新しい token.json を生成する。

使い方:
  1. python setup_analytics_auth.py を実行
  2. ブラウザが開いたら Google アカウントで権限承認
  3. 出力された token.json の中身をコピーして
     GitHub → Settings → Secrets → YOUTUBE_TOKEN_JSON を Update
"""
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from google_auth_oauthlib.flow import InstalledAppFlow

import config

# upload を残しているのは、本スクリプト実行後に既存のアップロードフローも
# 引き続き同じ token.json で動かすため（上位互換）。
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

CLIENT_SECRET = config.ROOT / "client_secret.json"
TOKEN_PATH = config.ROOT / "token.json"


def main() -> None:
    if not CLIENT_SECRET.exists():
        print(f"❌ {CLIENT_SECRET} が存在しません。")
        print("   GitHub Secrets の YOUTUBE_CLIENT_SECRET_JSON の中身を")
        print(f"   {CLIENT_SECRET} に保存してから再実行してください。")
        sys.exit(1)

    print("🔐 Analytics スコープを含めて OAuth 再認証します")
    print("   要求スコープ:")
    for s in SCOPES:
        print(f"     - {s}")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    print(f"\n✅ token.json 更新: {TOKEN_PATH}")
    print()
    print("📋 次の手順:")
    print("   1. https://github.com/niwatama01-wq/auto-shorts/settings/secrets/actions")
    print("      にアクセス")
    print("   2. YOUTUBE_TOKEN_JSON の右の鉛筆アイコンを押して Update")
    print("   3. 以下の token.json の中身を貼り付けて Save:")
    print()
    print("=" * 60)
    print(TOKEN_PATH.read_text(encoding="utf-8"))
    print("=" * 60)


if __name__ == "__main__":
    main()
