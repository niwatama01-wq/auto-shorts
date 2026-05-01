"""RSS で当日のヘッドラインを集めて、Claude API で「最もバズ理想な1本」を選定する。

使い方:
  python news_fetcher.py            # トップネタを表示
  python news_fetcher.py --json     # JSON出力（main.py に渡す形）
  python news_fetcher.py --top 3    # 上位3本
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import feedparser
import anthropic
from dotenv import load_dotenv

import config

load_dotenv(config.ROOT / ".env")


# ===== RSS フィード（多ジャンル、無料、APIキー不要） =====
# ジャンルバランス: 総合/国際/政治/経済/IT/エンタメ/科学/スポーツ/ライフ
RSS_FEEDS = {
    # === 総合（日本主要） ===
    "NHK 主要": "https://www.nhk.or.jp/rss/news/cat0.xml",
    "Yahoo!主要": "https://news.yahoo.co.jp/rss/topics/top-picks.xml",

    # === 国際 ===
    "NHK 国際": "https://www.nhk.or.jp/rss/news/cat6.xml",
    "Yahoo!国際": "https://news.yahoo.co.jp/rss/topics/world.xml",
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Reuters World": "https://feeds.reuters.com/reuters/worldNews",

    # === 経済・ビジネス ===
    "NHK 経済": "https://www.nhk.or.jp/rss/news/cat5.xml",
    "Yahoo!経済": "https://news.yahoo.co.jp/rss/topics/business.xml",
    "Bloomberg JP": "https://feeds.bloomberg.co.jp/rss/news.xml",

    # === 政治・社会 ===
    "NHK 政治": "https://www.nhk.or.jp/rss/news/cat4.xml",
    "NHK 社会": "https://www.nhk.or.jp/rss/news/cat1.xml",
    "Yahoo!国内": "https://news.yahoo.co.jp/rss/topics/domestic.xml",

    # === IT・テック ===
    "Yahoo!IT": "https://news.yahoo.co.jp/rss/topics/it.xml",
    "ITmedia": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml",
    "ASCII": "https://ascii.jp/rss.xml",
    "TechCrunch JP": "https://jp.techcrunch.com/feed/",
    "The Verge": "https://www.theverge.com/rss/index.xml",

    # === エンタメ ===
    "Yahoo!エンタメ": "https://news.yahoo.co.jp/rss/topics/entertainment.xml",
    "オリコン": "https://www.oricon.co.jp/rss/news/total.xml",

    # === 科学・サイエンス ===
    "NHK 科学・文化": "https://www.nhk.or.jp/rss/news/cat3.xml",
    "Nature ニュース": "https://www.nature.com/nature.rss",

    # === スポーツ ===
    "Yahoo!スポーツ": "https://news.yahoo.co.jp/rss/topics/sports.xml",
    "NHK スポーツ": "https://www.nhk.or.jp/rss/news/cat7.xml",

    # === ライフ・トレンド ===
    "Yahoo!ライフ": "https://news.yahoo.co.jp/rss/topics/life.xml",
    "Yahoo!地域": "https://news.yahoo.co.jp/rss/topics/local.xml",
}


def fetch_recent_headlines(hours: int = 24, max_per_feed: int = 5) -> list[dict]:
    """各フィードから直近X時間のヘッドラインを集める"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"  [warn] {source} 取得失敗: {e}", file=sys.stderr)
            continue
        for entry in feed.entries[:max_per_feed]:
            published = None
            for k in ("published_parsed", "updated_parsed"):
                if getattr(entry, k, None):
                    import time
                    published = datetime.fromtimestamp(
                        time.mktime(getattr(entry, k)), tz=timezone.utc
                    )
                    break
            if published and published < cutoff:
                continue
            items.append({
                "source": source,
                "title": getattr(entry, "title", "").strip(),
                "summary": re.sub(r"<[^>]+>", "",
                                   getattr(entry, "summary", ""))[:300].strip(),
                "url": getattr(entry, "link", ""),
                "published": published.isoformat() if published else None,
            })
    return items


CLAUDE_SCORE_PROMPT = """あなたはYouTube Shortsニュースチャンネルのプロデューサーです。
以下の本日のニュースヘッドラインリストから、**最もバズる確率が高い** トップ{top_n}本を100点満点でスコアリングして選んでください。

【スコアリング基準（100点満点）】
- 数字インパクト (25点): 具体的な数字（金額・人数・倍率・%）が含まれるか。大きいほど高得点。例「1600万件」「3兆円」「過去最大」
- 固有名詞の知名度 (20点): 一般人が即座に認知できる企業/人物/国名か。例「OpenAI」「トヨタ」「中国」は◎
- 感情訴求 (20点): 怒り・驚き・恐怖・希望・嫉妬のいずれかを刺激するか
- 議論性 (15点): コメント欄で意見が割れる構造があるか（賛否両論トピック）
- 速報性 (10点): 発生から24時間以内か
- 視覚化しやすさ (10点): 画像/グラフで一目で伝わるトピックか

【🚨絶対禁止: 過去に投稿済みのネタ（最優先ルール）】
以下の投稿済みリスト（タイトル＋theme要約）に **同じ主要キーワード・同じ企業名・同じ事案・同じ数字・同じトピック軸** が出ているネタは、
**どんなにバズスコアが高くても絶対に選ばない**。スコアリング以前の問題として弾く。
- 別の角度からの続報も避ける（ファンが混乱するため）
- 「次の値」続報（例: 5万9585円→6万円）も重複扱い
- 同一企業の別事案でも、直近で使っていたら避ける

{posted_block}

このリストにある主要キーワードが新しい候補ニュースに **少しでも** 含まれていたら、
そのニュースは選ばずに、**別ジャンルの2位以下のネタを選ぶ** こと。
バズスコア最高でも、重複なら選定不可。

【🚫 ユーザー手動ブロックリスト（絶対遵守）】
以下はユーザーが手動で「もう選ぶな」と指定したキーワード群。
各行は「AND条件」（スペース区切りの全単語がタイトルまたはthemeに含まれる時だけマッチ）。
マッチしたら、バズスコアに関係なく絶対に選ばない。

{excluded_block}

【ジャンル分散ルール（重要）】
直近の投稿履歴から、以下を判断し、**過去5本と異なるジャンル** から優先的に選ぶ:
- 連続でテック/AI系が続いていたら → 経済 or 政治 or 国際 or エンタメ or 科学 から選ぶ
- 同じ企業（Apple/OpenAI/Tesla/SpaceX等）が3回以上続いていたら → 別企業/業界へ
- 過去履歴がテック・AI偏重なら、 **今回は強制的に非テックを選ぶ**
- ジャンルカテゴリ目安: テック・経済・政治・国際・エンタメ・科学・スポーツ・社会・トレンド
- 「今週はAI週間にする」のような特化はせず、毎日違うジャンルを意識

【絶対除外（収益化・規約リスク）】
- 個人の死亡・自殺・事件被害者
- 国内政党・候補者の選挙関連（衆院選/参院選/候補者）
- 訴訟・刑事事件の被疑者・被告（公人除く）
- 性的・暴力的・自傷関連
- 医療・健康の確定的断言（誤情報ポリシー違反）
- 株価予測・投資推奨の確定的表現
- 災害・事故の犠牲者報道（広告適合性で-）
- 上記投稿済みリストと **同じトピック・同じ事案** （別の角度や続報なら可）

【優先トピックジャンル】
- AI・テック大手の動向（OpenAI / Anthropic / Google / NVIDIA / Apple / Microsoft / Meta）
- 海外発で日本未報道のテック・経済ニュース（日本語化ニーズ大）
- 業界の「初」「最大」「過去最高」が含まれる事象
- 数字で語れる経済指標（金利・為替・GDP・決算）
- 大企業の不祥事/リコール/買収（議論性高、ただし公人・公開情報のみ）

【出力形式】
必ず以下のJSON形式のみで出力。前後の説明文・コードフェンス禁止。

{{
  "selected": [
    {{
      "rank": 1,
      "score": 87,
      "score_breakdown": {{
        "numbers": 22,
        "famous_entities": 18,
        "emotion": 17,
        "controversy": 12,
        "recency": 9,
        "visual": 9
      }},
      "title": "選んだヘッドライン",
      "source": "ソース名",
      "url": "URL",
      "buzz_reason": "なぜバズるか1行説明",
      "risk_check": "収益化リスク評価（OK / 軽微 / 高リスク等）",
      "theme_for_video": "動画台本生成に渡すための、5W1Hを含む詳細なテーマ文（200-400字）。日本語、報道調、固有名詞・数字を必ず含める。"
    }}
  ]
}}

【ヘッドラインリスト】
{headlines}
"""


def _load_posted_history() -> list[dict]:
    p = config.ROOT / "posted_history.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("posted", [])
    except Exception:
        return []


def _load_excluded_topics() -> list[list[str]]:
    """excluded_topics.txt を読み、各行を AND キーワード群に分解"""
    p = config.ROOT / "excluded_topics.txt"
    if not p.exists():
        return []
    rules = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = [t for t in line.split() if t]
        if tokens:
            rules.append(tokens)
    return rules


def _matches_excluded(text: str, rules: list[list[str]]) -> list[str] | None:
    """テキストにマッチする除外ルールを返す（マッチ無しならNone）"""
    lower = text.lower()
    for tokens in rules:
        if all(t.lower() in lower for t in tokens):
            return tokens
    return None


VERIFY_DEDUP_PROMPT = """以下の候補ニュースが、過去投稿リストまたは手動ブロックリストと重複していないか厳密に判定せよ。

【判定基準（いずれか1つでも当てはまれば重複扱い）】
- 同じ企業の同じ事案
- 同じ数字・同じ金額の話題
- 同じトピック軸（例: Tesla自動運転問題、日経高値更新 など）
- 別角度の続報でも、話題の主軸が同じ
- 手動ブロックリストのキーワード群（AND条件）が候補に含まれる

【候補】
タイトル: {title}
テーマ: {theme}

【過去投稿リスト（直近30件、タイトル＋theme要約）】
{posted_block}

【手動ブロックリスト】
{excluded_block}

以下のJSONのみで出力。説明文・コードフェンス禁止。
{{
  "duplicate": true または false,
  "reason": "理由を1-2文で。どの過去投稿または手動ルールと被ったか具体的に。重複でなければ『なし』"
}}
"""


def _verify_not_duplicate(client, candidate: dict, posted_block: str,
                           excluded_block: str) -> dict:
    """Claude に選定結果を再評価させ、重複していないか二重チェック"""
    prompt = VERIFY_DEDUP_PROMPT.format(
        title=candidate.get("title", ""),
        theme=candidate.get("theme_for_video", "")[:500],
        posted_block=posted_block,
        excluded_block=excluded_block,
    )
    msg = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    return json.loads(raw[start:end + 1])


def select_top_topic(items: list[dict], top_n: int = 1) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=api_key)

    if not items:
        raise RuntimeError("ヘッドラインが0件。RSS取得を確認してください。")

    posted = _load_posted_history()
    if posted:
        # 直近30件まで除外対象として渡す（title + theme要約）
        posted_block = "\n".join(
            f"- [{p.get('posted_at','')[:10]}] {p.get('title','')}\n"
            f"    theme: {(p.get('theme','') or '')[:150]}"
            for p in posted[-30:]
        )
    else:
        posted_block = "（まだ投稿実績なし）"

    excluded_rules = _load_excluded_topics()
    if excluded_rules:
        excluded_block = "\n".join(
            f"- {' + '.join(tokens)}" for tokens in excluded_rules
        )
    else:
        excluded_block = "（手動ブロックなし）"

    # 多ジャンルから均等にヘッドラインを拾う（ソース毎に上限を設けてバランス確保）
    by_source: dict[str, list] = {}
    for it in items:
        by_source.setdefault(it["source"], []).append(it)
    balanced = []
    for src, lst in by_source.items():
        balanced.extend(lst[:6])  # 各ソース最大6件

    # 手動ブロックに引っかかるヘッドラインはプロンプト投入前に弾く（Claudeコスト節約）
    before_filter = len(balanced)
    filtered = []
    for it in balanced:
        hay = f"{it.get('title','')} {it.get('summary','')}"
        hit = _matches_excluded(hay, excluded_rules)
        if hit:
            print(f"  [excluded] {it['title'][:40]}... ← {'+'.join(hit)}",
                  file=sys.stderr)
            continue
        filtered.append(it)
    if excluded_rules:
        print(f"   手動ブロック通過: {len(filtered)}/{before_filter}",
              file=sys.stderr)

    headlines_text = "\n".join(
        f"- [{i['source']}] {i['title']} ({i['url']})\n  {i['summary']}"
        for i in filtered[:120]
    )
    # Claudeには余裕を持って多めに選定させる（二重チェックで弾かれた時のバックアップ用）
    claude_top_n = max(top_n, 5)
    prompt = CLAUDE_SCORE_PROMPT.format(
        top_n=claude_top_n,
        headlines=headlines_text,
        posted_block=posted_block,
        excluded_block=excluded_block,
    )

    msg = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    result = json.loads(raw[start:end + 1])

    # === 二重チェック: 各候補を順にClaudeで重複判定、非重複のみ採用 ===
    verified = []
    for cand in result.get("selected", []):
        # 手動ブロックのローカル再チェック（念のため）
        hay = f"{cand.get('title','')} {cand.get('theme_for_video','')}"
        hit = _matches_excluded(hay, excluded_rules)
        if hit:
            print(f"  [verify-excluded] rank{cand.get('rank')} "
                  f"{cand.get('title','')[:30]} ← {'+'.join(hit)}",
                  file=sys.stderr)
            continue
        # Claudeで意味論的重複判定
        verdict = _verify_not_duplicate(client, cand, posted_block, excluded_block)
        if verdict.get("duplicate"):
            print(f"  [verify-dup] rank{cand.get('rank')} "
                  f"{cand.get('title','')[:30]} ← {verdict.get('reason','')[:80]}",
                  file=sys.stderr)
            continue
        print(f"  [verify-ok ] rank{cand.get('rank')} "
              f"{cand.get('title','')[:40]}", file=sys.stderr)
        verified.append(cand)
        if len(verified) >= top_n:
            break

    if not verified:
        raise RuntimeError(
            "二重チェックを通過したネタが0件。"
            "excluded_topics.txt を見直すか、時間をおいて再実行してください。"
        )

    # rank を振り直す
    for i, c in enumerate(verified, 1):
        c["rank"] = i
    return {"selected": verified}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=1, help="選定する本数")
    p.add_argument("--hours", type=int, default=24, help="何時間遡るか")
    p.add_argument("--json", action="store_true", help="JSON出力")
    args = p.parse_args()

    print(f"📰 RSS から直近 {args.hours}時間のヘッドライン取得中...", file=sys.stderr)
    items = fetch_recent_headlines(hours=args.hours)
    print(f"   → {len(items)} 件取得", file=sys.stderr)

    print(f"🤖 Claude で TOP{args.top} 選定中...", file=sys.stderr)
    result = select_top_topic(items, top_n=args.top)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for sel in result["selected"]:
            print(f"\n=== Rank {sel['rank']} ===")
            print(f"📌 {sel['title']}")
            print(f"   出典: {sel['source']}")
            print(f"   URL : {sel['url']}")
            print(f"💥 バズ理由: {sel['buzz_reason']}")
            print(f"🎬 テーマ:\n{sel['theme_for_video']}")


if __name__ == "__main__":
    main()