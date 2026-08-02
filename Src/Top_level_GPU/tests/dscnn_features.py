"""
Real-audio feature extraction for the DS-CNN voice-command classifier,
matching the exact pipeline the model was trained/exported with (external
project `voice-fan-controller`: `training/scripts/04_augment_and_extract_features.py`
and `training/configs/audio_params.yaml`, both read directly, not guessed
or re-derived).

`crop_or_pad()` and `extract_log_mel()` below are copied verbatim from that
script's functions (`26_logmel_parity_test.py`, in that repo, checks
`extract_log_mel` against a compiled C frontend to <0.002dB -- it's the
real parity-tested reference, not an approximation) rather than
reimplemented, so this carries zero independent parity risk. That script's
own `audiomentations` import (an augmentation library, unrelated to feature
extraction itself, needed only for its training-time augmentation code
paths) is deliberately not pulled in here.

`librosa`/`soundfile` are verification-only dependencies, same as
ai-edge-litert (see dscnn_reference.py's module docstring): install with
`pip install librosa soundfile` to (re-)extract features from a WAV file,
uninstall once the resulting int8 feature array is cached to disk -- the
GPU/RTL side never needs librosa installed, only the small cached .npy
output (a 81x32 int8 array is ~2.6KB).
"""
import os

import numpy as np


AUDIO_PARAMS = {
    "sample_rate_hz": 20000,
    "capture_window_ms": 1600,
    "window_ms": 25.6,
    "stride_ms": 20,
    "mel_bins": 32,
    "mel_lower_edge_hz": 125,
    "mel_upper_edge_hz": 7500,
    "log_mel_top_db": 80.0,
}
# Transcribed directly from configs/audio_params.yaml in the training repo,
# not re-derived. log_mel_ref is not included here -- only "max" (the
# shipping default) is implemented below, see extract_log_mel's docstring.

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "dscnn_fixtures")


def crop_or_pad(audio, window_samples):
    """Verbatim from 04_augment_and_extract_features.py: zero-pad clips
    shorter than the capture window, or for longer ones (every real WAV
    file in the dataset has ~300ms of recording margin around the actual
    phrase, per 01_record_dataset.py) pick the loudest contiguous
    window_samples-length slice -- crude endpointing, not full VAD, but
    it's what the model was trained against."""
    if len(audio) <= window_samples:
        return np.pad(audio, (0, window_samples - len(audio)))
    energy = audio.astype(np.float64) ** 2
    window_sum = np.convolve(energy, np.ones(window_samples), mode="valid")
    start = int(np.argmax(window_sum))
    return audio[start:start + window_samples]


def extract_log_mel(audio, sample_rate, window_ms, stride_ms, mel_bins, fmin, fmax,
                     top_db=80.0):
    """Verbatim (the log_ref="max" path only -- the shipping default; the
    "legacy" np.log(x+1e-6) A/B path and the spec_smooth>0 pitch-distortion
    mitigation are both intentionally omitted, neither is used by the
    shipped model) from extract_log_mel() in
    04_augment_and_extract_features.py. Requires `librosa` installed.
    Returns (num_frames, mel_bins) float32 dB values in [-top_db, 0].
    """
    import librosa

    n_fft = int(sample_rate * window_ms / 1000)
    hop_length = int(sample_rate * stride_ms / 1000)
    mel_spec = librosa.feature.melspectrogram(
        y=audio, sr=sample_rate, n_fft=n_fft, hop_length=hop_length,
        win_length=n_fft, n_mels=mel_bins, fmin=fmin, fmax=fmax, power=2.0,
    )
    spec = librosa.power_to_db(mel_spec, ref=np.max, top_db=top_db)
    return spec.T.astype(np.float32)  # (num_frames, mel_bins)


def load_and_extract(wav_path, params=AUDIO_PARAMS):
    """WAV file on disk -> (num_frames, mel_bins) float32 log-mel dB array,
    ready for quantize_to_int8(). Requires `librosa`/`soundfile` installed.
    """
    import soundfile as sf

    audio, sr = sf.read(wav_path, dtype="float32")
    assert sr == params["sample_rate_hz"], (
        f"{wav_path}: sample rate {sr} != {params['sample_rate_hz']}"
    )
    if audio.ndim > 1:
        audio = audio.mean(axis=1)  # defensive; every real clip here is already mono

    window_samples = int(params["sample_rate_hz"] * params["capture_window_ms"] / 1000)
    audio = crop_or_pad(audio, window_samples)

    return extract_log_mel(
        audio, params["sample_rate_hz"], params["window_ms"], params["stride_ms"],
        params["mel_bins"], params["mel_lower_edge_hz"], params["mel_upper_edge_hz"],
        top_db=params["log_mel_top_db"],
    )


def _round_half_away_from_zero_np(x):
    """Same convention as tflite_fixedpoint.py's `_round_half_away_from_zero`
    (C++'s std::round, not numpy's round-half-to-even), vectorized."""
    return np.where(x >= 0, np.floor(x + 0.5), np.ceil(x - 0.5))


def quantize_to_int8(spec_db, scale, zero_point):
    """Real dB value -> int8, using the model's OWN input tensor's
    scale/zero_point -- read from the .tflite file itself via
    `dscnn_reference.tensor_quant(sg, 0)`, not re-derived from the training
    repo's yaml (though they agree: 1/0.3137254901960784 matches the real
    tflite tensor's scale exactly)."""
    q = _round_half_away_from_zero_np(spec_db / scale) + zero_point
    return np.clip(q, -128, 127).astype(np.int8)


if __name__ == "__main__":
    import glob
    import sys

    from dscnn_reference import load_model, tensor_quant

    wav_glob = sys.argv[1] if len(sys.argv) > 1 else None
    if wav_glob is None:
        wav_glob = (
            "/mnt/c/Users/austi/OneDrive/Desktop/Project/Personal/"
            "voice-fan-controller/training/data/raw/power_on/*.wav"
        )
    candidates = sorted(glob.glob(wav_glob))
    assert candidates, f"no WAV files matched {wav_glob}"
    wav_path = candidates[0]
    print(f"Extracting features from {wav_path}")

    spec_db = load_and_extract(wav_path)
    print(f"log-mel shape: {spec_db.shape} (expect (81, 32)), range [{spec_db.min():.2f}, {spec_db.max():.2f}] dB")
    assert spec_db.shape == (81, 32), f"unexpected shape {spec_db.shape}"
    assert spec_db.max() == 0.0, "log_mel_ref='max' must put the loudest cell at exactly 0 dB"
    assert spec_db.min() >= -80.0

    model, sg = load_model()
    scale, zp = tensor_quant(sg, 0)  # tensor 0 = the model's real input tensor
    features_int8 = quantize_to_int8(spec_db, scale[0], zp[0])
    print(f"quantized int8 shape: {features_int8.shape}, range [{features_int8.min()}, {features_int8.max()}]")
    assert features_int8.max() == zp[0], "the max-dB (0 dB) cell must quantize to exactly zero_point"

    os.makedirs(FIXTURE_DIR, exist_ok=True)
    out_path = os.path.join(FIXTURE_DIR, "power_on_sample.npy")
    np.save(out_path, features_int8)
    print(f"\nCached int8 features to {out_path} ({features_int8.nbytes} bytes)")
    print("All dscnn_features.py standalone checks PASSED")
