"""VOICEVOX でシーンごとに wav 生成（ジャンル別話者対応）

v7変更点:
- pre/post_phoneme_length と pause_length_scale をジャンル設定から読むように
  (デフォルトは旧値と同じ)
"""
import json
import re
import wave
from pathlib import Path

import requests

import config


def _strip_emphasis(text: str) -> str:
    """ナレーションから **word** マークと周辺空白を除去（音声合成用）。"""
    text = re.sub(r"\s*\*\*\s*([^*]+?)\s*\*\*\s*", r"\1", text)
    return text


def _audio_query(text: str, speaker_id: int) -> dict:
    r = requests.post(
        f"{config.VOICEVOX_HOST}/audio_query",
        params={"text": text, "speaker": speaker_id},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _synthesis(query: dict, speaker_id: int) -> bytes:
    r = requests.post(
        f"{config.VOICEVOX_HOST}/synthesis",
        params={"speaker": speaker_id},
        data=json.dumps(query),
        headers={"Content-Type": "application/json"},
        timeout=120,
    )
    r.raise_for_status()
    return r.content


def _wav_duration_from_bytes(wav_bytes: bytes) -> float:
    import io
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def _wav_duration_from_path(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def synthesize_scene(text: str, out_path: Path, genre, silence_sec: float = 1.5) -> float:
    """1シーン分のwavを生成。生成後の実時間（秒）を返す。"""
    text = _strip_emphasis(text)
    if not text.strip():
        import struct
        sr = 24000
        n = int(silence_sec * sr)
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(struct.pack("<" + "h" * n, *([0] * n)))
        return silence_sec

    speaker_id = genre.VOICEVOX_SPEAKER_ID
    query = _audio_query(text, speaker_id)
    query["speedScale"] = genre.VOICEVOX_SPEED
    query["pitchScale"] = genre.VOICEVOX_PITCH
    query["intonationScale"] = genre.VOICEVOX_INTONATION
    # v7: ジャンル設定があれば使う、なければ従来値
    query["postPhonemeLength"] = getattr(genre, "VOICEVOX_POST_PHONEME", 0.05)
    query["prePhonemeLength"] = getattr(genre, "VOICEVOX_PRE_PHONEME", 0.05)
    if "pauseLengthScale" in query:
        query["pauseLengthScale"] = getattr(genre, "VOICEVOX_PAUSE_LENGTH_SCALE", 0.7)

    wav = _synthesis(query, speaker_id)
    out_path.write_bytes(wav)
    return _wav_duration_from_bytes(wav)


def synthesize_all(script: dict, run_dir: Path, genre) -> dict:
    """script内の全シーンを音声化。
    返り値: {scene_id: {"audio_path": Path, "actual_sec": float}}"""
    audio_dir = run_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    result = {}
    for scene in script["scenes"]:
        sid = scene["scene_id"]
        path = audio_dir / f"scene_{sid:02d}.wav"
        silence_sec = max(1.0, min(2.5, float(scene.get("duration_sec", 1.5))))
        if path.exists() and path.stat().st_size > 100:
            actual = _wav_duration_from_path(path)
        else:
            actual = synthesize_scene(scene.get("narration", ""), path, genre, silence_sec=silence_sec)
        result[sid] = {"audio_path": path, "actual_sec": actual}
        scene["actual_audio_sec"] = actual
    return result


def voicevox_alive() -> bool:
    try:
        r = requests.get(f"{config.VOICEVOX_HOST}/version", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


if __name__ == "__main__":
    import sys
    from genres import load_genre
    if not voicevox_alive():
        print(f"VOICEVOX not running at {config.VOICEVOX_HOST}")
        raise SystemExit(1)
    g = load_genre(sys.argv[1] if len(sys.argv) > 1 else "horror")
    out = Path("test_voice.wav")
    sec = synthesize_scene("これは絶対に見てはいけない動画です。", out, g)
    print(f"Generated {out} ({sec:.2f}s) [genre={g.NAME}, speaker={g.VOICEVOX_SPEAKER_ID}]")
