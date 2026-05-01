"""auto-shorts のグローバル設定。ジャンル横断で使う値だけここに置く。"""
from pathlib import Path

ROOT = Path(__file__).parent

# ===== 出力パス =====
OUT_SCRIPTS = ROOT / "output" / "scripts"
OUT_VIDEOS = ROOT / "output" / "videos"

# ===== アセット（ジャンル共通） =====
ASSETS_BGM = ROOT / "assets" / "bgm"      # ジャンル別はサブフォルダで管理
ASSETS_SFX = ROOT / "assets" / "sfx"
ASSETS_FONTS = ROOT / "assets" / "fonts"
ASSETS_ENTITIES = ROOT / "assets" / "entities"   # 固有名詞→画像の差し替え用

# ===== Claude API =====
CLAUDE_MODEL = "claude-opus-4-7"
CLAUDE_MAX_TOKENS = 4000

# ===== VOICEVOX =====
VOICEVOX_HOST = "http://localhost:50021"

# ===== 画像生成バックエンド =====
# "comfyui": ローカル ComfyUI で SDXL（要 ComfyUI 起動）
# "flux_replicate": Replicate 経由 FLUX 1.1 Pro Ultra（要 REPLICATE_API_TOKEN、$0.06/枚）
IMAGE_BACKEND = "flux_replicate"

# ===== ComfyUI / SDXL（IMAGE_BACKEND=comfyui のとき使用） =====
COMFYUI_HOST = "http://localhost:8188"
SD_CHECKPOINT = "sd_xl_base_1.0.safetensors"
SD_WIDTH = 832
SD_HEIGHT = 1216
SD_STEPS = 25
SD_CFG = 7.0
SD_SAMPLER = "dpmpp_2m"
SD_SCHEDULER = "karras"

# ===== FLUX (Replicate) （IMAGE_BACKEND=flux_replicate のとき使用） =====
FLUX_MODEL = "black-forest-labs/flux-1.1-pro-ultra"  # $0.06/枚
# 縦動画用アスペクト: "9:16" でPro Ultraは1024x1820相当を出力
FLUX_ASPECT_RATIO = "9:16"
FLUX_OUTPUT_FORMAT = "jpg"
FLUX_RAW_MODE = False     # True にするとシネマティックLUTを外して素のリアル感
FLUX_SAFETY_TOLERANCE = 6  # 1-6, 高いほど寛容（ニュース系は誤検出されやすいので最大）

# ===== 動画（デフォルトはShorts縦9:16、ジャンルでoverride可） =====
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30


def video_dims(genre) -> tuple[int, int]:
    """ジャンル設定があればそれを優先（mystery等の長尺横画面用）"""
    w = getattr(genre, "VIDEO_WIDTH", VIDEO_WIDTH)
    h = getattr(genre, "VIDEO_HEIGHT", VIDEO_HEIGHT)
    return w, h

# ===== 立ち絵（キャラクターオーバーレイ） =====
CHARACTER_BASE = ROOT / "assets" / "characters"   # ジャンル別キャラ画像
CHARACTER_WIDTH_RATIO = 0.45      # 画面幅に対する立ち絵の幅
CHARACTER_Y_OFFSET_RATIO = 0.05   # 画面下端からのマージン

# ===== 音量比（ナレーションを大きく、BGMはかすかに） =====
NARRATION_VOLUME = 1.3
SFX_VOLUME = 0.6
# BGM_VOLUMEはジャンル側で定義（暗い系は低め、AI系は控えめ）

# shock直前の余韻（無音パッド秒）
SILENCE_PAD_BEFORE_SHOCK = 0.4
SUBTITLE_FONT = str(ROOT / "assets" / "fonts" / "NotoSansJP-Variable.ttf")
SUBTITLE_FONT_WEIGHT = 900       # Black（PIL variable font axisで指定）
SUBTITLE_FONT_SIZE = 70
SUBTITLE_STROKE_WIDTH = 5
SUBTITLE_Y_RATIO = 0.50  # 画面中央

# === フック専用テロップ（インパクト最大化用） ===
# 851チカラヅヨク かなA = TikTok/Shorts定番のインパクトフォント
# 太い・荒削り・手書き風で速報感MAX、漢字14963字フルカバー、商用可・改変可
SUBTITLE_FONT_HOOK = str(ROOT / "assets" / "fonts" / "851CHIKARA-DZUYOKU_kanaA.ttf")
SUBTITLE_FONT_SIZE_HOOK = 130    # 大きめ（130）でドカン
SUBTITLE_STROKE_WIDTH_HOOK = 10  # 太い縁取りで視認性 MAX
SUBTITLE_Y_RATIO_HOOK = 0.42     # 中央より上にしてバナーと干渉回避

# === BREAKING NEWS バナー（hookシーン上部に重ねる赤帯） ===
# 「速報」のみ表示（漢字フルカバーで文字化けゼロ）
HOOK_BANNER_ENABLED = True
HOOK_BANNER_TEXT = "速報"
HOOK_BANNER_COLOR = (220, 30, 30)         # 緊急感の濃い赤
HOOK_BANNER_TEXT_COLOR = "white"
HOOK_BANNER_HEIGHT_RATIO = 0.10           # 画面高の10%
HOOK_BANNER_Y_RATIO = 0.10                # 上から10%地点
HOOK_BANNER_FONT_SIZE = 95                # 「速報」だけなら大きめでドカン

# === フックテロップの色（hookだけ目立たせる） ===
# 通常テロップは白、hookは「警告イエロー」で視覚インパクト最大化
HOOK_SUBTITLE_COLOR = "#FFE633"           # ビビッドなネオンイエロー
HOOK_SUBTITLE_STROKE_COLOR = "#B30000"    # 濃赤の縁取りで「速報感」

# Ken Burns（より強めのズームで動き感UP）
KEN_BURNS_ZOOM_START = 1.0
KEN_BURNS_ZOOM_END = 1.18
TRANSITION_DURATION = 0.15   # 短めのクロスフェードでテンポUP


def ensure_dirs():
    for p in [OUT_SCRIPTS, OUT_VIDEOS, ASSETS_BGM, ASSETS_SFX, ASSETS_FONTS,
              ASSETS_ENTITIES, CHARACTER_BASE]:
        p.mkdir(parents=True, exist_ok=True)


def find_entity_image(entity: str | None):
    """assets/entities/<entity>.{png,jpg,webp} を探して返す。なければNone"""
    if not entity or entity == "null":
        return None
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = ASSETS_ENTITIES / f"{entity}.{ext}"
        if p.exists():
            return p
    return None


def genre_bgm_dir(genre_name: str) -> Path:
    """ジャンル別BGMフォルダ。なければASSETS_BGMをfallback"""
    p = ASSETS_BGM / genre_name
    if p.exists():
        return p
    return ASSETS_BGM


def genre_sfx_dir(genre_name: str) -> Path:
    p = ASSETS_SFX / genre_name
    if p.exists():
        return p
    return ASSETS_SFX
