# Claude セッション引き継ぎ

このファイルを **新しい Claude Code セッション（claude.ai/code）で最初に読ませる** とこれまでの全文脈を引き継げます。

## プロジェクト概要

- **チャンネル**: 60秒ニュース速報 / Flash News（YouTube Shorts、ニュース系）
- **目的**: AI で 30秒のニュース動画を全自動生成・投稿
- **運用**: GitHub Actions cron が 1日5回（07:00/12:00/17:00/19:30/22:00 JST）動画を生成し、private で YouTube にアップ → 30分後に自動公開
- **コスト感**: 月$25前後（Anthropic + Replicate + その他）

## 技術スタック

- **Python 3.12 + MoviePy 2.x + Pillow** （動画組立）
- **VOICEVOX** （TTS、speaker=13 青山龍星、speed=1.10）
- **Replicate FLUX 1.1 Pro Ultra** （画像生成、$0.06/枚、フォールバック用）
- **Unsplash + Pexels** （無料写真、最優先）
- **Anthropic Claude Opus 4.7** （台本生成・ニュース選定・重複判定）
- **YouTube Data API v3** + OAuth （アップロード）
- **feedparser** （22 RSS フィード、多ジャンル）

## ファイル構成のキーパーツ

- `main.py` — オーケストレーター。`--genre ai_news "テーマ"` または `--script <path>` で再生成
- `news_fetcher.py` — RSSから最もバズる1本をClaude選定。3層重複防止（履歴/ブロックリスト/二重チェック）
- `script_gen.py` — Claude API で30秒台本を JSON 生成
- `tts.py` — VOICEVOX 音声合成、ファイルキャッシュ
- `image_gen.py` — Unsplash/Pexels → FLUX の4段階画像取得
- `video_assemble.py` — MoviePy で動画組立、字幕、BGM、SE
- `youtube_upload.py` — OAuth + MediaFileUpload でアップ、`publishAt` で予約公開
- `genres/ai_news.py` — ジャンル設定 + Claude プロンプト全文
- `config.py` — グローバル設定（フォント・音量・解像度・Ken Burns）
- `excluded_topics.txt` — 手動ブロックリスト（重複防止2層目）
- `posted_history.json` — 投稿履歴（重複防止1層目、cron で自動push）
- `.github/workflows/daily-news.yml` — cron 5 schedules + workflow_dispatch
- `assets/bgm/ai_news/_meta.json` — BGM ムードタグ
- `notebooks/channel_analysis.ipynb` — Colab分析用

## 現在の v6 フォーマット仕様

### テロップ
- **本文フォント**: Noto Sans JP Variable（`assets/fonts/NotoSansJP-Variable.ttf`、weight 900）
- **フックフォント**: 851チカラヅヨク かなA（`assets/fonts/851CHIKARA-DZUYOKU_kanaA.ttf`、漢字フルカバー、商用可）
- **本文色**: 白 + 濃紺縁取り
- **フック色**: ビビッドイエロー (#FFE633) + 濃赤縁取り (#B30000)、`**強調**` は白
- **本文サイズ**: 70px / フック 130px

### 速報赤バナー（hookシーンのみ）
- 上部 10% 位置に赤帯（#DC1E1E）
- 文字は「速報」のみ（絵文字なし）、白抜き太字
- 最初の0.4秒で上からスライドイン

### BGM
- `BGM_VOLUME = 0.10`
- プール: 16曲（urapora ニュース系厳選 + Replicate MusicGen 4曲）
- ムードタグで絞込: `breaking | tech | investigation | scandal | lifestyle | general`
- 各曲のタグは `assets/bgm/ai_news/_meta.json` に記載
- 映画的すぎる Poseidon / orchestral_mission / zanshinen は news 用から除外

### SE
- プール: 35ファイル（urapora中心、Replicate生成も4ファイル）
- スキーマ名: `impact_drum / breaking_alert / dramatic_riser / reveal_chime / camera_shutter / suspense_drone / typing_keyboard / swoosh_transition / glitch_news / warning_beep` 等
- `_SFX_ALIAS` で実ファイルにマップ、毎回ランダムでバリエーション化

### 台本フォーマット
- **30秒**、scenes 7-9個、合計 150-200字
- 1シーン20-30字（hook/shock は 12-20字、3-4秒）
- 体言止め＋「です・ます」混在、報道調
- キャラクター語尾（〜のだ等）禁止、CTA禁止
- 「**強調**」マーカーで重要1ワードを黄色化

### タイトル形式（5型分散）
1. 【速報】定型: `【速報】[数字 or 固有名詞]、[結論]`
2. 引き伸ばし型: `【○○】〜が△△した結果...`
3. 数字インパクト: `[絵文字][数字][固有名詞][動詞]`
4. 対立/疑問: `[A]vs[B]、[結論]` or `なぜ[主語]は[行動]？`
5. 損失回避: `[負キーワード]、[対象]に何が起きる`

### 重複防止3層
1. 即時履歴記録（`main.py` で台本生成直後に `posted_history.json` 追記）
2. `excluded_topics.txt` 手動ブロック（AND条件、部分一致）
3. Claude 二重チェック（候補の意味論的重複判定、被ったら次点繰上げ）

## リポジトリ

- **新（運用中）**: https://github.com/niwatama01-wq/auto-shorts
- 旧（infoniwatama/auto-shorts）は GitHub Actions 月間上限超過で移転、Actions無効化済み

## Secrets（GitHub Actions）

- `ANTHROPIC_API_KEY`
- `REPLICATE_API_TOKEN`
- `PEXELS_API_KEY`
- `UNSPLASH_ACCESS_KEY`
- `YOUTUBE_CLIENT_SECRET_JSON` （client_secret.json の中身）
- `YOUTUBE_TOKEN_JSON` （token.json の中身）

ローカルでは `.env` + `client_secret.json` + `token.json` で動く（`.gitignore` 済み）。

## 投稿済み比較動画（限定公開、最新版）

- v6（最新）: https://youtu.be/VaEtfddakko
- 自動cron 1本目: https://youtu.be/5z7ACpMj5VE （15:41 JST 自動公開）

## 直近の決定事項

- 2026-04-30: GitHub アカウント `infoniwatama` → `niwatama01-wq` に移転
- v6 フォーマット（851フォント・黄色テロップ・速報赤バナー・BGM 0.10・SE豊富）を本番固定
- Colab に分析作業を移行する流れ（チャンネル分析は `notebooks/channel_analysis.ipynb` 参照）

## ユーザーの好み

- 簡潔で実行的な提案を好む
- 漢字化け、絵文字非対応を強く嫌う（フォントは漢字フルカバー必須）
- BGM は「ニュースっぽい」緊張感重視、映画的・オーケストラ系は不採用
- バズ理論より具体実装（フォント名・色・URLパターン）を重視
- 自律実行を期待（許可プロンプト最小化のため `~/.claude/hooks/pipe-stage-permissions.py` 設定済み）

## 次にやることの候補

- 残り5本（172605/173452/174330/175150/180044）の v6 再レンダー＋アップ
- チャンネル分析（Colabノートブックで再生数の伸び要因抽出）
- サムネ自動生成の復活（現在 `if False:` で停止中）
- A/Bテスト：タイトル5案の中でどれが伸びるか比較

---

このドキュメントを最初に読んだ後、ユーザーから新しい指示を待ってください。
