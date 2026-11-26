"""Prompt recordings on disk (task 1.4).

Uploads are checked and re-written as a clean WAV (PCM 16-bit mono, 8 or 16 kHz: what
Asterisk plays without transcoding; other metadata chunks are dropped). Files go to the
prompts volume, which Asterisk mounts read-only as /var/lib/asterisk/sounds/mira:

    <prompts_dir>/<tenant hex>/<language>/<prompt hex>.wav     8 kHz  ("wav")
    <prompts_dir>/<tenant hex>/<language>/<prompt hex>.wav16   16 kHz ("wav16")

The engine plays the exact file, `sound:mira/<tenant hex>/<language>/<prompt hex>`, choosing
the language itself from the recordings that exist (prompt_audio). Files are 0640, group
mira-config.
"""

import hashlib
import io
import os
import tempfile
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path

MAX_BYTES = 12 * 1024 * 1024
MAX_SECONDS = 300
RATES = {8000: ".wav", 16000: ".wav16"}


class BadAudio(ValueError):
    """The upload is not a WAV file Mira can play."""


@dataclass
class CleanAudio:
    data: bytes
    sample_rate: int
    duration_ms: int
    sha256: str


def clean_wav(raw: bytes) -> CleanAudio:
    if len(raw) > MAX_BYTES:
        raise BadAudio(f"the file is larger than {MAX_BYTES // (1024 * 1024)} MB")
    try:
        with wave.open(io.BytesIO(raw)) as w:
            channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            if w.getcomptype() != "NONE":
                raise BadAudio("compressed WAV is not supported: use PCM")
            frames = w.readframes(w.getnframes())
    # a broken header makes the wave module raise RuntimeError (chunk sizes past the end)
    except (wave.Error, EOFError, RuntimeError) as exc:
        raise BadAudio(f"not a WAV file ({exc})") from None
    if channels != 1 or width != 2 or rate not in RATES:
        raise BadAudio(
            f"needs mono, 16-bit, 8000 or 16000 Hz (got {channels} channel(s), "
            f"{width * 8}-bit, {rate} Hz)"
        )
    duration_ms = len(frames) * 1000 // (2 * rate)
    if duration_ms <= 0:
        raise BadAudio("the recording is empty")
    if duration_ms > MAX_SECONDS * 1000:
        raise BadAudio(f"longer than {MAX_SECONDS // 60} minutes")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    data = out.getvalue()
    return CleanAudio(data, rate, duration_ms, hashlib.sha256(data).hexdigest())


def audio_path(
    root: Path, tenant_id: uuid.UUID, language: str, prompt_id: uuid.UUID, rate: int
) -> Path:
    if language not in ("ar", "en", "fr"):
        raise ValueError("language")
    return root / tenant_id.hex / language / (prompt_id.hex + RATES[rate])


def sound_uri(tenant_id: uuid.UUID, prompt_id: uuid.UUID, language: str) -> str:
    """What the engine plays: the exact recording (Asterisk adds only the file extension).

    The language is in the path on purpose: Asterisk 22 looks sounds up as <lang>/<path>
    only (not <dir>/<lang>/<file>), and the engine already knows which recordings exist."""
    if language not in ("ar", "en", "fr"):
        raise ValueError("language")
    return f"sound:mira/{tenant_id.hex}/{language}/{prompt_id.hex}"


def store(
    root: Path,
    tenant_id: uuid.UUID,
    language: str,
    prompt_id: uuid.UUID,
    audio: CleanAudio,
    gid: int | None = None,
) -> Path:
    """Write atomically, and drop the other sample rate's file so only one version plays."""
    target = audio_path(root, tenant_id, language, prompt_id, audio.sample_rate)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o2750)
    for directory in (target.parent, target.parent.parent):
        if gid is not None:
            os.chown(directory, -1, gid)
        directory.chmod(0o2750)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".upload.")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(audio.data)
        if gid is not None:
            os.chown(tmp, -1, gid)
        os.chmod(tmp, 0o640)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    for rate in RATES:
        if rate != audio.sample_rate:
            audio_path(root, tenant_id, language, prompt_id, rate).unlink(missing_ok=True)
    return target


def remove(
    root: Path, tenant_id: uuid.UUID, prompt_id: uuid.UUID, language: str | None = None
) -> None:
    for lang in [language] if language else ["ar", "en", "fr"]:
        for rate in RATES:
            audio_path(root, tenant_id, lang, prompt_id, rate).unlink(missing_ok=True)
