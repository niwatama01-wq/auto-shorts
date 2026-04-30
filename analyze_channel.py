"""チャンネル分析。週次でGitHub Actionsから実行され docs/analysis/latest.md を更新する。

使い方:
  ローカル:        python analyze_channel.py
  GitHub Actions:  .github/workflows/analyze-channel.yml が cron + workflow_dispatch で起動

出力:
  docs/analysis/latest.md            最新レポート
  docs/analysis/YYYY-MM-DD.md        日付別アーカイブ
  docs/analysis/charts/*.png         グラフ画像
  docs/analysis/videos_data.csv      生データ

要件:
  既存 token.json は upload スコープのみで動かないため、setup_analytics_auth.py で
  yt-analytics.readonly スコープを追加した token.json に差し替えること。
"""
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

CLIENT_SECRET = config.ROOT / "client_secret.json"
TOKEN_PATH = config.ROOT / "token.json"

OUT_DIR = config.ROOT / "docs" / "analysis"
CHART_DIR = OUT_DIR / "charts"
COMPETITOR_HISTORY_PATH = OUT_DIR / "competitor_history.json"

JST = timezone(timedelta(hours=9))


# ===== 競合チャンネル監視リスト (v7) =====
# COMPETITOR_ANALYSIS.md の調査で特定した直接競合
COMPETITOR_CHANNELS = {
    "UC9Mc5eo6BWBNUqyIyaDH_Gw": "ヒマつぶしニュース速報",        # 直接ベンチマーク (毎日20:00、AI生成)
    "UCZ414k6R-We2qmASjRoIkxA": "AI笑話",                          # 同声 (青山龍星) 競合
    "UC-H2m0nZt6k0SJ5o04gS0nA": "ガグル",                           # 規模天井 (45.9万)
    "UCyfE-f5M29pR6aPjVwtg1ZA": "女の実は…",                       # VOICEVOX×女性向け
    "UClApr0DGRMjN-JIOGnxsfZQ": "ゆっくり霊夢のニュース速報",      # ゆっくり量産型
    "UC4SsirxZueE4OouHUeqBBbQ": "気になるニュース速報まとめ",      # まとめ系
}


# ---------- フォント設定 ----------
def setup_jp_font() -> None:
    """matplotlib に日本語フォントを設定。GitHub Actions では fonts-noto-cjk が入る前提。"""
    candidates = [
        "Noto Sans CJK JP",
        "Noto Sans JP",
        "IPAexGothic",
        "TakaoGothic",
        "Hiragino Sans",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = name
            print(f"   font: {name}")
            return
    print("   ⚠️ 日本語フォントなし。ラベルが化ける可能性あり")


# ---------- パーサー類 ----------
def parse_iso8601_duration(iso: str) -> float:
    """PT1M30S → 90.0 秒。Shorts用なので時/分/秒のみで十分"""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", iso or "")
    if not m:
        return 0.0
    h, mm, s = m.groups()
    return int(h or 0) * 3600 + int(mm or 0) * 60 + float(s or 0)


def classify_title(title: str) -> str:
    """HANDOFF のタイトル5型 + その他 に分類"""
    t = title or ""
    # 1. 速報/号外/緊急 で始まる
    if re.search(r"^[【\[]?\s*(速報|号外|緊急|警告)\s*[】\]]?", t):
        return "1_速報定型"
    # 2. 引き伸ばし型: 〜した結果 / してみたら / だった件 / 衝撃の結末
    if re.search(r"した結果|してみたら|だった件|衝撃の結末|の真相|\.\.\.$|…$", t):
        return "2_引き伸ばし"
    # 3. 数字インパクト: 先頭が数字 or 大きな数字+単位
    if re.search(r"^\W{0,3}\d", t) or re.search(r"\d{2,}\s*[％%倍億万兆人円]", t):
        return "3_数字インパクト"
    # 4. 対立/疑問
    if re.search(r"vs|VS|対|なぜ.*[？\?]|どっち|？$|\?$", t):
        return "4_対立疑問"
    # 5. 損失回避
    if re.search(r"危険|崩壊|終了|消失|警告|注意|失う|危機|ヤバい|やばい|終わり|消える", t):
        return "5_損失回避"
    return "0_その他"


def hour_bucket(jst_dt: datetime) -> str:
    """投稿時刻を5枠 (07/12/17/19:30/22) に丸める"""
    h = jst_dt.hour + jst_dt.minute / 60
    if 5.5 <= h < 9.5:
        return "07:00枠"
    if 9.5 <= h < 14.5:
        return "12:00枠"
    if 14.5 <= h < 18.5:
        return "17:00枠"
    if 18.5 <= h < 20.5:
        return "19:30枠"
    if 20.5 <= h < 24:
        return "22:00枠"
    return "その他"


# ---------- Google API認証 ----------
def get_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except ValueError as e:
            print(f"❌ token.json scope mismatch: {e}")
            print("   ローカルで `python setup_analytics_auth.py` を実行し、")
            print("   GitHub Secret YOUTUBE_TOKEN_JSON を更新してください。")
            sys.exit(1)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET.exists():
                raise RuntimeError(
                    f"client_secret.json not found at {CLIENT_SECRET}. "
                    "GitHub Actions secret YOUTUBE_CLIENT_SECRET_JSON が空？"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent")
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


# ---------- データ取得 ----------
def fetch_channel_videos(yt) -> tuple[list[dict], str, dict]:
    """自分のチャンネルの全動画をDataAPI v3で取得"""
    ch = yt.channels().list(
        part="contentDetails,snippet,statistics", mine=True
    ).execute()
    if not ch.get("items"):
        raise RuntimeError("自分のチャンネルが見つかりません（OAuth対象アカウント要確認）")
    channel = ch["items"][0]
    channel_id = channel["id"]
    uploads_pl = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"📺 Channel: {channel['snippet']['title']} ({channel_id})")
    print(f"   登録者: {channel['statistics'].get('subscriberCount', 'N/A')}")
    print(f"   累計再生: {channel['statistics'].get('viewCount', 'N/A')}")

    video_ids: list[str] = []
    page_token = None
    while True:
        resp = yt.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_pl,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        for it in resp["items"]:
            video_ids.append(it["contentDetails"]["videoId"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    print(f"   動画数: {len(video_ids)}")

    videos: list[dict] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = yt.videos().list(
            part="snippet,statistics,contentDetails,status",
            id=",".join(batch),
        ).execute()
        for v in resp["items"]:
            published = datetime.fromisoformat(
                v["snippet"]["publishedAt"].replace("Z", "+00:00")
            )
            stats = v.get("statistics", {})
            videos.append({
                "video_id": v["id"],
                "title": v["snippet"]["title"],
                "published_utc": published,
                "published_jst": published.astimezone(JST),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration_sec": parse_iso8601_duration(
                    v["contentDetails"].get("duration", "")
                ),
                "privacy": v["status"]["privacyStatus"],
                "description_len": len(v["snippet"].get("description", "")),
            })
    return videos, channel_id, channel


def fetch_retention(
    analytics, channel_id: str, video_id: str, days_back: int = 365
) -> list[tuple[float, float]]:
    """elapsedVideoTimeRatio dimension で audienceWatchRatio 取得"""
    end = datetime.now(JST).date().isoformat()
    start = (datetime.now(JST) - timedelta(days=days_back)).date().isoformat()
    try:
        resp = analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start,
            endDate=end,
            metrics="audienceWatchRatio",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}",
        ).execute()
        rows = resp.get("rows") or []
        return [(float(r[0]), float(r[1])) for r in rows]
    except HttpError as e:
        print(f"   ⚠️ retention {video_id[:11]}: {e.resp.status}")
        return []
    except Exception as e:
        print(f"   ⚠️ retention {video_id[:11]}: {e}")
        return []


# ---------- チャート ----------
def chart_top_pattern(df: pd.DataFrame, out: Path) -> bool:
    public = df[df["privacy"] == "public"].copy()
    if len(public) < 4:
        print("   public動画が4本未満。共通パターン分析スキップ")
        return False
    median_views = public["views"].median()
    public["category"] = public["views"].apply(
        lambda v: "上位50%" if v >= median_views else "下位50%"
    )

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    cols = [
        ("title_len", "タイトル文字数"),
        ("duration_sec", "動画長 (秒)"),
        ("hour_jst", "投稿時刻 JST"),
    ]
    for ax, (col, label) in zip(axes, cols):
        for cat, color in [("上位50%", "#1f77b4"), ("下位50%", "#ff7f0e")]:
            data = public[public["category"] == cat][col]
            if len(data):
                ax.hist(data, bins=8, alpha=0.6, label=cat, color=color)
        ax.set_xlabel(label)
        ax.set_ylabel("動画数")
        ax.legend()
        ax.set_title(label)
        ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return True


def chart_views_by_hour(df: pd.DataFrame, out: Path) -> pd.DataFrame | None:
    public = df[df["privacy"] == "public"]
    if len(public) == 0:
        return None
    grouped = public.groupby("bucket")["views"].agg(["mean", "median", "count"])
    order = ["07:00枠", "12:00枠", "17:00枠", "19:30枠", "22:00枠", "その他"]
    grouped = grouped.reindex([o for o in order if o in grouped.index])

    fig, ax = plt.subplots(figsize=(10, 5))
    x = range(len(grouped))
    ax.bar(x, grouped["mean"], label="平均", alpha=0.7, color="#2ca02c")
    ax.plot(x, grouped["median"], "o-", color="#d62728", label="中央値", linewidth=2)
    ax.set_xticks(list(x))
    ax.set_xticklabels(list(grouped.index), rotation=15)
    ax.set_ylabel("再生数")
    ax.set_title("投稿時間枠ごとの再生数")
    for i, n in enumerate(grouped["count"]):
        if grouped["mean"].iloc[i]:
            ax.text(
                i,
                grouped["mean"].iloc[i],
                f"n={int(n)}",
                ha="center",
                va="bottom",
                fontsize=9,
            )
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return grouped


def chart_title_types(df: pd.DataFrame, out: Path) -> pd.DataFrame | None:
    public = df[df["privacy"] == "public"]
    if len(public) == 0:
        return None
    grouped = public.groupby("title_type")["views"].agg(["mean", "median", "count"])
    grouped = grouped.sort_values("mean", ascending=False)

    fig, ax = plt.subplots(figsize=(10, 5))
    x = range(len(grouped))
    ax.bar(x, grouped["mean"], alpha=0.7, color="#9467bd")
    ax.set_xticks(list(x))
    ax.set_xticklabels(list(grouped.index), rotation=15)
    ax.set_ylabel("平均再生数")
    ax.set_title("タイトル5型 平均再生数")
    for i, n in enumerate(grouped["count"]):
        if grouped["mean"].iloc[i]:
            ax.text(
                i,
                grouped["mean"].iloc[i],
                f"n={int(n)}",
                ha="center",
                va="bottom",
                fontsize=9,
            )
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return grouped


def chart_retention(retention_data: dict, df: pd.DataFrame, out: Path) -> None:
    public = df[df["privacy"] == "public"].sort_values("views", ascending=False)
    top = public.head(3)
    bot = public.tail(3) if len(public) >= 6 else pd.DataFrame()

    fig, ax = plt.subplots(figsize=(10, 5))
    plotted = False
    for _, row in top.iterrows():
        curve = retention_data.get(row["video_id"]) or []
        if curve:
            xs = [p[0] * 100 for p in curve]
            ys = [p[1] * 100 for p in curve]
            ax.plot(
                xs, ys, "-", label=f"上位: {row['title'][:18]}", alpha=0.85, linewidth=2
            )
            plotted = True
    for _, row in bot.iterrows():
        curve = retention_data.get(row["video_id"]) or []
        if curve:
            xs = [p[0] * 100 for p in curve]
            ys = [p[1] * 100 for p in curve]
            ax.plot(xs, ys, "--", label=f"下位: {row['title'][:18]}", alpha=0.6)
            plotted = True
    ax.set_xlabel("動画進行率 (%)")
    ax.set_ylabel("視聴者維持率 (%)")
    ax.set_title("視聴維持率カーブ（上位 vs 下位）")
    if plotted:
        ax.legend(fontsize=8, loc="upper right")
    else:
        ax.text(
            0.5,
            0.5,
            "データ不足",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=14,
        )
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 110)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


# ---------- 競合トラッキング (v7) ----------
def fetch_competitor_snapshot(yt) -> list[dict]:
    """COMPETITOR_CHANNELS の登録者数・動画数・累計再生を1ショットで取得"""
    ids = list(COMPETITOR_CHANNELS.keys())
    snapshots = []
    # YouTube Data API は channels.list で最大50件まで一括
    for i in range(0, len(ids), 50):
        batch = ids[i : i + 50]
        try:
            resp = yt.channels().list(
                part="snippet,statistics",
                id=",".join(batch),
            ).execute()
            for ch in resp.get("items", []):
                stats = ch.get("statistics", {})
                snapshots.append({
                    "channel_id": ch["id"],
                    "name": COMPETITOR_CHANNELS.get(ch["id"], ch["snippet"]["title"]),
                    "subscribers": int(stats.get("subscriberCount", 0)),
                    "video_count": int(stats.get("videoCount", 0)),
                    "view_count": int(stats.get("viewCount", 0)),
                })
        except Exception as e:
            print(f"   競合スナップショット取得失敗 (batch {i}): {e}")
    return snapshots


def track_competitors(yt) -> tuple[list[dict], list[dict]]:
    """競合スナップショットを取得し、履歴JSONに追記。
    返り値: (current_snapshots, deltas_vs_prev)"""
    print(f"\n📊 競合チャンネル {len(COMPETITOR_CHANNELS)} 件を監視中...")
    current = fetch_competitor_snapshot(yt)
    today = datetime.now(JST).date().isoformat()

    history: list = []
    if COMPETITOR_HISTORY_PATH.exists():
        try:
            import json
            history = json.loads(COMPETITOR_HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            history = []

    # 同日重複は上書き
    history = [h for h in history if h.get("date") != today]
    history.append({"date": today, "snapshots": current})
    history = history[-52:]  # 直近1年分のみ保持

    import json
    COMPETITOR_HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 前回比デルタ計算
    deltas = []
    prev_snapshot_map = {}
    if len(history) >= 2:
        prev = history[-2]
        prev_snapshot_map = {s["channel_id"]: s for s in prev["snapshots"]}
        prev_date = prev["date"]
    else:
        prev_date = None

    for cur in current:
        prev_s = prev_snapshot_map.get(cur["channel_id"])
        delta = {
            "name": cur["name"],
            "subscribers": cur["subscribers"],
            "video_count": cur["video_count"],
            "view_count": cur["view_count"],
            "subscribers_delta": (cur["subscribers"] - prev_s["subscribers"]) if prev_s else None,
            "video_count_delta": (cur["video_count"] - prev_s["video_count"]) if prev_s else None,
            "view_count_delta": (cur["view_count"] - prev_s["view_count"]) if prev_s else None,
            "prev_date": prev_date,
        }
        deltas.append(delta)
    return current, deltas


def render_competitor_section(deltas: list[dict]) -> list[str]:
    """競合トラッキング結果をMarkdown行リストで返す"""
    if not deltas:
        return ["", "## ⑤ 競合チャンネル監視", "", "_データ取得失敗_"]

    has_delta = any(d["subscribers_delta"] is not None for d in deltas)
    title = "## ⑤ 競合チャンネル監視 (前回比)" if has_delta else "## ⑤ 競合チャンネル監視 (初回スナップショット)"
    lines = ["", title, ""]

    if has_delta:
        prev_date = deltas[0].get("prev_date") or "前回"
        lines.append(f"_前回スナップショット: {prev_date}_")
        lines.append("")
        lines.append("| チャンネル | 登録者 | Δ登録 | 動画数 | Δ動画 | 累計再生 | Δ再生 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
    else:
        lines.append("| チャンネル | 登録者 | 動画数 | 累計再生 |")
        lines.append("|---|---:|---:|---:|")

    # 登録者数で降順
    for d in sorted(deltas, key=lambda x: -x["subscribers"]):
        if has_delta:
            ds = d["subscribers_delta"]
            dv = d["video_count_delta"]
            dc = d["view_count_delta"]
            ds_str = f"+{ds:,}" if ds and ds > 0 else (f"{ds:,}" if ds else "-")
            dv_str = f"+{dv}" if dv and dv > 0 else (f"{dv}" if dv else "-")
            dc_str = f"+{dc:,}" if dc and dc > 0 else (f"{dc:,}" if dc else "-")
            lines.append(
                f"| {d['name']} | {d['subscribers']:,} | {ds_str} | "
                f"{d['video_count']:,} | {dv_str} | "
                f"{d['view_count']:,} | {dc_str} |"
            )
        else:
            lines.append(
                f"| {d['name']} | {d['subscribers']:,} | "
                f"{d['video_count']:,} | {d['view_count']:,} |"
            )

    # 注目イベント検出
    if has_delta:
        notable = []
        for d in deltas:
            if d["subscribers_delta"] and d["subscribers_delta"] > 1000:
                notable.append(f"⚡ **{d['name']}** が登録者 +{d['subscribers_delta']:,} (急成長)")
            if d["video_count_delta"] and d["video_count_delta"] > 10:
                notable.append(f"📈 **{d['name']}** が +{d['video_count_delta']} 本投稿 (高頻度)")
        if notable:
            lines.append("")
            lines.append("### 注目すべき動き")
            lines.append("")
            for n in notable:
                lines.append(f"- {n}")
    return lines


# ---------- メイン ----------
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)

    setup_jp_font()
    creds = get_credentials()
    yt = build("youtube", "v3", credentials=creds)
    analytics = build("youtubeAnalytics", "v2", credentials=creds)

    videos, channel_id, channel_meta = fetch_channel_videos(yt)
    if not videos:
        print("⚠️ 動画なし。終了")
        return

    df = pd.DataFrame(videos)
    df["title_len"] = df["title"].str.len()
    df["title_type"] = df["title"].apply(classify_title)
    df["bucket"] = df["published_jst"].apply(hour_bucket)
    df["hour_jst"] = df["published_jst"].apply(lambda d: d.hour + d.minute / 60)

    # 維持率（public動画のみ。Analyticsクオータ節約）
    public_videos = df[df["privacy"] == "public"]
    print(f"\n📈 維持率取得 ({len(public_videos)}本)...")
    retention_data: dict = {}
    for _, row in public_videos.iterrows():
        retention_data[row["video_id"]] = fetch_retention(
            analytics, channel_id, row["video_id"]
        )

    # チャート
    print("\n🎨 チャート生成...")
    chart_top_pattern(df, CHART_DIR / "01_top_pattern.png")
    bucket_stats = chart_views_by_hour(df, CHART_DIR / "02_views_by_hour.png")
    title_stats = chart_title_types(df, CHART_DIR / "03_title_types.png")
    chart_retention(retention_data, df, CHART_DIR / "04_retention.png")

    # 維持率の谷検出（10pt以上の急落）
    drops: list[tuple[float, float, str]] = []
    for vid, curve in retention_data.items():
        for i in range(1, len(curve)):
            d = curve[i - 1][1] - curve[i][1]
            if d > 0.10:
                drops.append((curve[i][0] * 100, d * 100, vid))
    drops.sort(key=lambda x: -x[1])

    # ---------- Markdown生成 ----------
    public = df[df["privacy"] == "public"].sort_values("views", ascending=False)
    now_jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    lines = [
        "# 📊 チャンネル分析レポート",
        "",
        f"_自動生成: {now_jst} / チャンネル: {channel_meta['snippet']['title']}_",
        "",
        "## 基本情報",
        "",
        f"- 動画総数: **{len(df)}本** "
        f"(public {(df['privacy']=='public').sum()} / "
        f"unlisted {(df['privacy']=='unlisted').sum()} / "
        f"private {(df['privacy']=='private').sum()})",
    ]
    if len(public):
        lines += [
            f"- 公開動画 累計再生: **{int(public['views'].sum()):,} 回**",
            f"- 公開動画 平均再生: **{int(public['views'].mean()):,} 回** "
            f"/ 中央値 **{int(public['views'].median()):,} 回**",
            f"- 公開動画 平均いいね: **{public['likes'].mean():.1f}** "
         