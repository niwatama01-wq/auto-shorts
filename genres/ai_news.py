"""AIニュースShortsのジャンル設定 (v7: 競合差別化版)

変更点 (vs v6):
- 音声: AI笑話 (青山龍星 同声) との差別化のため intonation を 1.05 → 1.25 へ
  speed 1.10 → 1.13、pitch 0.0 → -0.03 (重み付き低音化)、
  pre/post_phoneme と pause_length_scale を新規露出
- 冒頭ジングル: INTRO_JINGLE_ENABLED で 0.5秒の「Flash News」ロゴ枠を有効化
- 尺パラメータ化: DURATION_SEC で 30/45 切替可能。プロンプト側も {duration} を受ける
"""

NAME = "ai_news"

# ===== VOICEVOX (v7: 報道アンカー風に強調) =====
VOICEVOX_SPEAKER_ID = 13   # 青山龍星（ニュースキャスター調・ノーマル）
VOICEVOX_SPEED = 1.13      # ↑ 1.10 → 1.13 緊迫感UP
VOICEVOX_PITCH = -0.03     # ↑ 0.0 → -0.03 重み・権威感
VOICEVOX_INTONATION = 1.25 # ↑ 1.05 → 1.25 起伏の効いた抑揚 (AI笑話との差別化最重要)
VOICEVOX_PRE_PHONEME = 0.05    # 文頭の無音
VOICEVOX_POST_PHONEME = 0.05   # 文末の無音
VOICEVOX_PAUSE_LENGTH_SCALE = 0.7  # 句読点ポーズ短縮 (テンポ重視)

# ===== 尺（30 or 45 秒）。CLI --duration で上書き可 =====
DURATION_SEC = 30

# ===== 冒頭ジングル（0.5秒「Flash News」ロゴ + 速報音） =====
INTRO_JINGLE_ENABLED = True
INTRO_JINGLE_DURATION = 0.5
INTRO_JINGLE_TEXT = "Flash News"
INTRO_JINGLE_SUBTEXT = "60秒ニュース速報"
INTRO_JINGLE_BG_COLOR = (220, 30, 30)        # 速報赤と統一
INTRO_JINGLE_TEXT_COLOR = "#FFE633"           # 黄色 (テロップと統一)
INTRO_JINGLE_SFX = "breaking_alert"           # 既存のSFXエイリアス

# ===== Stable Diffusion（写実ニュース報道写真） =====
SD_STYLE_PREFIX = "photorealistic news photography, "
SD_STYLE_SUFFIX = (
    ", real-world scene, professional press photo, cinematic lighting, "
    "documentary photography, shallow depth of field, sharp focus, "
    "high detail, 4k, journalistic style, natural colors, no text, no letters"
)
SD_NEGATIVE = (
    "anime, cartoon, illustration, drawing, painting, neon, abstract, "
    "sci-fi, futuristic, cyberpunk, glowing, deformed, lowres, blurry, "
    "watermark, logo, signature, text, letters, japanese text, "
    "chinese text, extra limbs, bad anatomy, cluttered, oversaturated"
)

# ===== 固有名詞→画像オーバーライド =====
ENTITY_CANDIDATES = [
    "openai", "anthropic", "google", "microsoft", "meta", "apple",
    "amazon", "nvidia", "tesla", "spacex", "samsung",
    "claude", "gpt", "gemini", "chatgpt",
    "ai_chip", "datacenter", "server_room",
    "japan", "usa", "china", "eu", "korea",
    "breaking_news", "courtroom", "police", "press_conference",
    "stock_chart_up", "stock_chart_down", "hacker", "cyber_attack",
    "ceo_meeting", "office", "city_skyline",
    "concert", "microphone", "stage", "kpop",
]

# ===== Subtitle =====
SUBTITLE_COLOR = "white"
SUBTITLE_STROKE_COLOR = "#0a1f3a"
SUBTITLE_EMPHASIS_COLOR = "#FFE633"
SUBTITLE_EMPHASIS_SHAKE = True

# ===== Thumbnail =====
THUMBNAIL_BADGE_TEXT = "速報"
THUMBNAIL_TEXT_COLOR = "#FFE633"
THUMBNAIL_STROKE_COLOR = "#000000"

# ===== BGM =====
BGM_VOLUME = 0.10

# ===== キャラクター立ち絵 =====
CHARACTER_DIR = "ai_news"
CHARACTER_POSITION = "right"
EMOTION_TO_EXPRESSION = {
    "hook": "surprise",
    "normal": "normal",
    "shock": "surprise",
    "silence": "normal",
    "climax": "smile",
    "outro": "smile",
}

# ===== Claude prompt (v7: 尺パラメータ化) =====
# 使用変数: {theme}, {duration}, {min_chars}, {max_chars}, {min_scenes}, {max_scenes}
PROMPT_TEMPLATE = """あなたは YouTube Shorts ニュースチャンネルの台本作家です。
扱うジャンルは問いません（テック、経済、政治、エンタメ、国際、社会等）。

【タスク】
以下のネタから **{duration}秒のShorts台本（短く引き締まった速報）** を生成してください。
視聴者は一般層。ニュース番組のアナウンサー読み上げのように、
要点を絞ってテンポ良く伝えます。**報道調・ニュース解説調**で書きます
（断定形、体言止め可、敬体「です・ます」も可）。
キャラクター語尾（「〜のだ」「〜なのだ」「〜だぞ」等）は **絶対に使わない** こと。

【出力形式】
必ず以下のJSON形式のみで出力。前後の説明文・コードフェンス禁止。

{{
  "title_candidates": ["案1【速報】型", "案2【】+引き型", "案3 数字インパクト型", "案4 対立/疑問型", "案5 損失回避型"],
  "thumbnail_text": "サムネ用の8文字以内の煽り文",
  "thumbnail_number": "サムネに大きく載せる数字または短いキーワード（例: '1600万件' '3社同盟' '24000'）",
  "bgm_mood": "breaking | tech | investigation | scandal | lifestyle | general",
  "scenes": [
    {{
      "scene_id": 1,
      "narration": "ナレーション文。重要なキーワードは **二重アスタリスク** で囲む（後述）",
      "duration_sec": 3.0,
      "emotion": "hook | normal | shock | silence | climax | outro",
      "image_prompt": "SDXL/FLUX用の英語画像プロンプト。固有名詞や日本語禁止、視覚要素のみ。",
      "image_search_keyword": "Unsplash/Pexels検索用の英語キーワード(2-4語)。例: 'data center server room', 'business handshake meeting', 'cyber security hacker', 'asian city skyline night'。FLUXフォールバックする場合に画像生成プロンプトより検索ヒット率重視。null可。",
      "entity": "openai | anthropic | google | microsoft | meta | apple | amazon | nvidia | tesla | spacex | samsung | claude | gpt | gemini | chatgpt | ai_chip | datacenter | server_room | japan | usa | china | eu | korea | breaking_news | courtroom | police | press_conference | stock_chart_up | stock_chart_down | hacker | cyber_attack | ceo_meeting | office | city_skyline | concert | microphone | stage | kpop | null",
      "sfx": "impact_drum | breaking_alert | dramatic_riser | reveal_chime | camera_shutter | suspense_drone | typing_keyboard | swoosh_transition | glitch_news | warning_beep | ding | whoosh | pop | notification | silence | none",
      "bgm_intensity": "low | mid | high"
    }}
  ]
}}

【bgm_mood の選び方】
- **breaking**: 速報・緊急・大事件・政治介入・大型M&A
- **tech**: AI・IT・新製品発表・テック企業の動き
- **investigation**: 調査報道・捜査・告発・内部リーク
- **scandal**: 不祥事・告訴・告発・暴露
- **lifestyle**: 生活・健康・トレンド・エンタメ
- **general**: どれにも当てはまらない時の汎用

【SFX多用ルール（重要）】
- 各シーンで適切なSFXを必ず割り当てる（"none"連発禁止）
- hookシーンは必ず "impact_drum" または "breaking_alert"
- shockシーンは "dramatic_riser" または "warning_beep" 推奨
- normal でも数字発表時は "reveal_chime"、PC/IT系は "typing_keyboard" や "glitch_news"
- シーン切替の余韻に "swoosh_transition" を時々挟む
- silence のみ "silence"

【タイトル候補のフォーマット（2026年Shortsバズ最新型、絶対遵守）】

# 絶対ルール
1. 各案は **30文字以内** （スマホ表示の打ち切り対策、ハッシュタグ含めない）
2. **最重要キーワード（固有名詞 or 数字）は必ず冒頭8文字以内**（検索SEO+0.3秒判断）
3. 絵文字は **冒頭1個まで** 、ブラケット【】を使う場合は絵文字なしでもOK
4. 数字は **具体数字** （1600万、3兆円、87％）で。概数（数百万）禁止
5. 「衝撃」「驚愕」「バズ」だけのフックワードは禁止（検索ヒット0）

# 5案の型を必ず分散（同じ型を2本以上作らない）

- 案1【速報定型】「【速報】[具体数字 or 固有名詞]、[動詞・結論]」
  例: 「【速報】政府が9兆円買収に中止勧告」(18字)
  例: 「【速報】日経6万円突破、半年で1万円急騰」(20字)
  → 信頼性UP・検索流入大・ニュース系の王道、必ず1案は入れる

- 案2【ブラケット引き伸ばし型】「【○○】[主語]が[行動]した結果...」
  例: 「【独占】牧野フライス防衛、政府が動いた瞬間」(22字)
  例: 「【緊急】AI3社が極秘会合、その内容がヤバい」(22字)
  → 「...」「結果」「瞬間」「ヤバい」で続きを匂わせる

- 案3【数字インパクト型】「[絵文字][具体数字][固有名詞][動詞]」
  例: 「🚨1600万件AI盗用、米3社が緊急同盟」(22字)
  例: 「⚡村上10号、大谷の日本人記録に並ぶ」(19字)
  → 数字が圧倒的＝飛ばし読みでも引っかかる

- 案4【対立 or 疑問型】「[A]vs[B]、[結論]」「なぜ[主語]は[行動]？」
  例: 「中国AIに米が宣戦布告、史上初3社連合」(20字)
  例: 「なぜテスラは400万台で公約撤回した？」(20字)
  → コメント欄が盛り上がる

- 案5【損失回避・カリギュラ型】「[負のキーワード]、[対象]に何が起きる」
  例: 「日本AI企業が完全に取り残される瞬間」(18字)
  例: 「あなたのテスラFSDが使えなくなる日」(19字)
  → 「自分ごと化」で離脱率↓

# 文末・装飾テクニック（適宜使う）
- 文末に「...」で続きを匂わす（思わずタップ誘発）
- 「←これ」「←ヤバい」など視聴者目線のツッコミ風
- 「...の真相」「...の結果」「...の理由」で結論を先送り
- 数字+単位の連続（「9兆円・違約金1.5兆円」）で重み

# パワーワード辞書（積極使用）
- 衝撃系: 緊急/史上初/過去最大/一夜で/突如/激震/暴落/暴騰/宣戦布告/逆転/陥落
- 損失系: 取り残される/手遅れ/もう遅い/間に合わない/失う/危機
- 権威系: 米政府/中国政府/OpenAI/Apple/トヨタ/日銀/SEC
- 時間系: 24時間以内/今夜/たった今/明日から/年内に

# NGワード（収益化リスクのため絶対禁止）
- 「死亡」「殺人」「自殺」「強姦」「事故死」等の犯罪・死亡系
- 一般人の個人名（公人除く）
- 「絶対」「100%」「保証」「確実」等の確定的表現
- 「炎上」「叩かれる」「ヤバすぎ」「ヤバい」等の幼稚な煽り
- 「衝撃すぎ」「神回」「マジで」「ガチで」等のSNS的口語

【強調ワードのマーキング（重要）】
- ナレーション内の最重要1ワードを **ダブルアスタリスク** で囲む
- 例: "AI業界に **激震** "、"なんと **1600万件** が流出"
- 各シーンで最大1ワード（多すぎると効果消える）
- hook/shock/climaxシーンは必ず1ワード強調を入れる
- normal/outroは強調なしでもOK
- 強調ワードはサムネ煽り文と関連する内容にする（記憶定着）

【entityフィールドの使い方】
- ナレーションで特定企業や具体物が出るシーンは、必ず該当 entity を指定
- 例: "OpenAIが発表" → entity="openai"、 "ハッキングが発覚" → entity="hacker"
- 該当しないシーン（フックや煽り等）は entity=null

【image_search_keyword の使い方（重要）】
- 各シーンに対し、Unsplash/Pexels で検索しやすい **英語キーワード** を必ず生成
- 2-4語の短いフレーズ。一般名詞中心。固有名詞は使わない（実在企業ロゴ写真は権利問題）
- 良い例: "data center server room", "business handshake meeting", "asian city skyline night",
  "cyber security hacker", "press conference podium", "world map digital",
  "executive office building", "computer screen code dark"
- 悪い例: "OpenAI office"（固有名詞）、"the moment they shook hands"（具体的過ぎ）、"AI"（一般的過ぎ）
- フック/煽りシーンも視覚的に合うキーワードを必ず入れる（hook なら "breaking news studio", climax なら "smartphone night dark" 等）

【画像入手の優先順位（システム側で自動）】
1. assets/entities/<entity>.png（手配済みロゴ等）
2. Unsplash/Pexels で image_search_keyword 検索
3. 上記ヒットなければ image_prompt から FLUX で生成
そのため image_prompt と image_search_keyword は両方とも内容と整合する形で書く

【構成ルール】
- 全体 **{duration}秒（短く引き締まった速報）**
- scenesは **{min_scenes}-{max_scenes}個**（情報を絞ってテンポ重視）
- scene_id=1は必ずemotion="hook"、duration=2-3秒
- フック例「AI業界に **激震** が走りました」「衝撃のニュースです」
- 中盤に必ず1つemotion="shock"（数字や衝撃の事実で）
- 最後はemotion="outro"で **結論の一言で締める**（チャンネル登録誘導・フォロー誘導は禁止）

【1シーンの長さとテンポ】
- 1シーンのナレーションは **20-30文字** 推奨（最大35文字）
- 1シーン **3-4秒**(VOICEVOX 青山龍星は5字/秒程度で読む)
- ただし hook/shock は短く強く（12-20文字、2-3秒）
- 視聴者が同じ画像で5秒以上止まらないよう、長めの説明は2シーンに分割
- **合計ナレーション文字数 {min_chars}-{max_chars}文字を目標**（{duration}秒に収める）

【文体（重要・厳守）】
- **報道ニュース調**で、内容をしっかり説明する
- ですます調と体言止めを混ぜる（断定感とプロ感）
- 「〜のだ」「〜なのだ」「〜だぞ」等のキャラ語尾は **絶対NG**
- 単なる単語の連発（「OpenAIが動く。」「狙いは中国AI。」）はNG。文として情報を伝える
- 良い例:
  - "AI業界に **激震** が走りました"
  - "OpenAI・Anthropic・Googleが史上初めての連携を発表"
  - "中国企業による『蒸留』という盗用技術への対抗策です"
  - "Anthropicは単独で1600万件の不正利用を検出しました"
  - "次に狙われるのは、あなたが使うAIかもしれません"
- 悪い例（短すぎ・説明不足）:
  - "OpenAIが動く"
  - "狙いは中国AI"
  - "1600万件"
  - "AI冷戦の本格化"

【内容の網羅】
- 5W1Hを動画全体でカバー: いつ・誰が・何を・なぜ・どうした
- 数字や具体例は省略せず説明（「1600万件」だけでなく「1600万件もの不正利用が検出されました」）
- 専門用語は1度言い換える（例: 「蒸留、つまりモデルをマネして安く作る技術」）
- 以下を全部カバー:
  1. **いつ**: 発表日時・経緯
  2. **誰が**: 関係する企業名・人名（ただし個人のフルネームは避ける）
  3. **何を**: 何が起きたか、具体的アクション
  4. **なぜ**: 背景・動機・原因
  5. **規模**: 数字（回数・金額・人数・期間）
  6. **仕組み**: 技術的な説明（やさしい言い換え付き）
  7. **影響**: 業界や視聴者への意味
  8. **今後**: 次に何が起きるかの予測や警告

【ループ構造（重要）】
- Shortsはループ再生されるため、最後と最初を視覚的に繋げる
- scene_id=1 (hook) と最後の scene (outro) の image_prompt は **同じ構図・同じ視覚要素** を使うこと
- 例: 両方とも「futuristic blue purple neon network with floating orbs」を含める
- 視聴者が動画ループ時に「気づかず2周目」を見るように設計

【オチの意外性（重要）】
- climaxシーンに「視聴者が想定しない一言」を入れる
- 良い例: 「次に狙われるのは、あなたが使うAIかもしれません」
         「これはまだ氷山の一角に過ぎません」
         「AI覇権争いは新たな局面に突入しました」
- 単なる事実の繰り返し（NG例:「AI3社が連携しました」）ではなく、視聴者を引き込む引き

【outro（最後のシーン）のルール】
- **チャンネル登録・フォロー誘導は禁止**
- 「登録」「フォロー」「チャンネル」「登録者」等の単語を使わない
- 未来志向の定型句（「今後も」「これからも」「引き続き」「今後とも」）も禁止
- **結論を言い切る1文**で締める。ニュース番組のエンディングのように短く。
- OK例: 「AI時代の新たな転換点です。」
        「業界は、根本から変わりつつあります。」
        「静かに、しかし確実に、AI戦争は始まった。」
        「これは、始まりに過ぎません。」
        「見えない戦線で、AIの未来が争われています。」

【感情ガイド】
- hook: 冒頭3秒で視聴者を掴む
- normal: 事実の積み上げ、淡々と
- shock: 驚きの数字/事実を強調
- silence: 1.5秒の余韻（気づきを促す）
- climax: 結論の核心
- outro: CTA

【ナレーションの注意】
- 報道キャスター調（ですます＋体言止めミックス）
- 1秒あたり約 **5文字** （VOICEVOX青山龍星の想定速度）
- 難しい専門用語は1度だけ言い換える（例: 「蒸留」→「モデルをマネして作る技術」）
- 数字は必ず文脈に埋め込む（単体で出さず、意味が伝わる文に）
- キャラ語尾（のだ、ぞ、にゃ等）は使わない
- 「〜です」「〜ます」「〜でしょう」「〜と見られます」「〜と発表」等の報道調語尾を多用

【画像プロンプトの注意（写実報道写真スタイル）】
- ニュース報道風の写実的な実写写真
- ジャンルに応じた具体シーン:
  * テック/ビジネス: 会議室、CEO登壇、オフィス、サーバールーム、記者会見
  * 政治/国際: 国会、首脳会談、国旗、街並み
  * エンタメ: ステージ、コンサート会場、マイク、観客のシルエット
  * 事件/社会: 警察署、裁判所、街の一角、新聞、夜景
- 人物が出る場合は顔が認識できないアングル（後ろ姿、シルエット、手元のクローズアップ）
- 企業ロゴ・実在人物の顔・日本語/中国語/ハングル文字は画像に入れない
- 抽象的・SF的・ネオン系・カートゥーン調は **絶対に避ける**（報道風スタイル統一）

【テロップ折返しの目安】
- 1シーン30-45文字でも、文節改行で2-3行に収まる
- 強調ワードは長くても5-6文字までに（「**激震**」「**1600万件**」など）
- 「OpenAI」「Anthropic」「Google」など英語表記の固有名詞は不必要に繰り返さない

【テーマ/ネタ】
{theme}
"""
