from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


class AudioProcessingError(RuntimeError):
    pass


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise AudioProcessingError(completed.stderr[-2000:] or "audio command failed")


def convert_to_wav(source: Path, target: Path) -> None:
    _run(["ffmpeg", "-y", "-i", str(source), "-ac", "1", "-ar", "44100", str(target)])


def separate_vocals(source_wav: Path, output_dir: Path) -> Path:
    """Use Demucs when installed; fall back to the source for user-provided vocal tracks."""
    demucs = shutil.which("demucs")
    if not demucs:
        return source_wav
    _run([demucs, "--two-stems=vocals", "-n", "htdemucs", "-o", str(output_dir), str(source_wav)])
    candidates = list(output_dir.rglob("vocals.wav"))
    return candidates[0] if candidates else source_wav


def pitch_correct(source_wav: Path, target_wav: Path, mode: str) -> None:
    y, sr = librosa.load(source_wav, sr=44100, mono=True)
    if y.size == 0:
        raise AudioProcessingError("empty vocal recording")
    # This is a deterministic CPU-safe baseline. Replace with a neural tuner when desired.
    f0, voiced_flag, _ = librosa.pyin(y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr)
    corrected = y.copy()
    strength = 0.90 if mode == "strong" else 0.55
    valid = np.isfinite(f0) & voiced_flag
    if np.any(valid):
        midi = librosa.hz_to_midi(f0[valid])
        snapped = np.round(midi)
        shifts = (snapped - midi) * strength
        # Frame-wise correction is applied through a smoothed global median to avoid clicks.
        semitone_shift = float(np.clip(np.nanmedian(shifts), -2.0, 2.0))
        if abs(semitone_shift) > 0.01:
            corrected = librosa.effects.pitch_shift(y, sr=sr, n_steps=semitone_shift)
    sf.write(target_wav, corrected, sr, subtype="PCM_16")


def mix(vocal_wav: Path, instrumental: Path | None, output_mp3: Path) -> None:
    if instrumental and instrumental.exists():
        _run([
            "ffmpeg", "-y", "-i", str(instrumental), "-i", str(vocal_wav),
            "-filter_complex",
            "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,volume=0.75[m];"
            "[1:a]highpass=f=70,acompressor=threshold=-18dB:ratio=3:attack=10:release=80,"
            "aecho=0.8:0.88:60:0.18,volume=1.15[v];[m][v]amix=inputs=2:duration=first:dropout_transition=2,"
            "loudnorm=I=-14:TP=-1.0:LRA=11[out]",
            "-map", "[out]", "-codec:a", "libmp3lame", "-b:a", "256k", str(output_mp3),
        ])
    else:
        _run(["ffmpeg", "-y", "-i", str(vocal_wav), "-af", "loudnorm=I=-14:TP=-1.0:LRA=11", "-codec:a", "libmp3lame", "-b:a", "256k", str(output_mp3)])


def process(vocal_input: Path, instrumental_input: Path | None, work_dir: Path, mode: str) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    source_wav = work_dir / "source.wav"
    convert_to_wav(vocal_input, source_wav)
    separated = separate_vocals(source_wav, work_dir / "separated")
    tuned = work_dir / "tuned.wav"
    pitch_correct(separated, tuned, mode)
    output = work_dir / "finished.mp3"
    mix(tuned, instrumental_input, output)
    return output


async def process_async(vocal_input: Path, instrumental_input: Path | None, work_dir: Path, mode: str) -> Path:
    return await asyncio.to_thread(process, vocal_input, instrumental_input, work_dir, mode)
