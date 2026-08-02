"""
Task #26: breadth check across all 18 real voice-command classes. Host-only
(dscnn_reference.run_dscnn_host, no RTL -- see project memory
project_accel_ctrl_address_ceiling.md for why real-size RTL is currently
blocked) vs. the real TFLite interpreter (dscnn_reference.run_tflite_reference),
one real WAV file per class.

Purpose: measure how far the two known, already-documented precision
caveats (single-stage vs. gemmlowp two-stage rescale; softmax's shift-only
exp8-LUT coarseness -- see dscnn_reference.py's module docstring) actually
diverge on real audio, and whether argmax-level agreement holds even though
bit-exact int8-probability agreement is not expected.

Verification-only dependencies (librosa, soundfile, ai-edge-litert): install
right before running this script, uninstall right after -- see
feedback_verification_deps_ephemeral.md.

Usage: python3 dscnn_breadth_check.py
(run from Src/Top_level_GPU/tests/, or anywhere with that dir on PYTHONPATH)
"""
import glob
import os

from dscnn_reference import (
    load_model, tensor_quant, _build_all_layers, run_dscnn_host,
    run_tflite_reference,
)
from dscnn_features import load_and_extract, quantize_to_int8


RAW_DATA_DIR = (
    "/mnt/c/Users/austi/OneDrive/Desktop/Project/Personal/"
    "voice-fan-controller/training/data/raw"
)

CLASSES = [
    "_silence_", "_unknown_",
    "mode_boost", "mode_nature", "mode_reverse", "mode_smart",
    "power_off", "power_on",
    "speed_1", "speed_2", "speed_3", "speed_4", "speed_5", "speed_6",
    "timer_2h", "timer_4h", "timer_8h", "timer_off",
]


def pick_one_wav(class_name):
    candidates = sorted(glob.glob(os.path.join(RAW_DATA_DIR, class_name, "*.wav")))
    assert candidates, f"no WAV files found for class {class_name!r} in {RAW_DATA_DIR}"
    return candidates[0]


def main():
    model, sg = load_model()
    in_scale, in_zp = tensor_quant(sg, 0)
    layers = _build_all_layers(model, sg)

    print(f"{'class':12s} {'wav file':28s} {'host argmax':>11s} {'tflite argmax':>13s} {'match':>5s}  max|delta|  mean|delta|")
    print("-" * 100)

    n_match = 0
    all_deltas = []
    per_class_results = []

    for class_idx, class_name in enumerate(CLASSES):
        wav_path = pick_one_wav(class_name)
        wav_name = os.path.basename(wav_path)

        spec_db = load_and_extract(wav_path)
        features_int8 = quantize_to_int8(spec_db, in_scale[0], in_zp[0])
        features_flat = features_int8.flatten().tolist()

        host_out = run_dscnn_host(model, sg, features_flat, layers=layers)
        host_argmax = host_out.index(max(host_out))

        tflite_out, _ = run_tflite_reference(features_int8.reshape(1, 81, 32, 1))
        tflite_out = tflite_out.flatten().tolist()
        tflite_argmax = tflite_out.index(max(tflite_out))

        deltas = [abs(h - t) for h, t in zip(host_out, tflite_out)]
        max_delta = max(deltas)
        mean_delta = sum(deltas) / len(deltas)
        all_deltas.extend(deltas)

        match = host_argmax == tflite_argmax
        n_match += match
        per_class_results.append({
            "class": class_name, "wav": wav_name,
            "host_argmax": host_argmax, "tflite_argmax": tflite_argmax,
            "match": match, "host_out": host_out, "tflite_out": tflite_out,
        })

        print(
            f"{class_name:12s} {wav_name:28s} {host_argmax:>11d} {tflite_argmax:>13d} "
            f"{'YES' if match else 'no':>5s}  {max_delta:>10d}  {mean_delta:>10.2f}"
        )

    print("-" * 100)
    print(f"argmax agreement: {n_match}/{len(CLASSES)} classes")
    print(f"overall per-element |delta|: max={max(all_deltas)}, mean={sum(all_deltas) / len(all_deltas):.2f}")
    print(
        "\nExpected per the two documented precision caveats: NOT bit-exact "
        "(single-stage vs gemmlowp two-stage rescale rounding; softmax's "
        "shift-only exp8-LUT undershoot -- see dscnn_reference.py docstring). "
        "argmax agreement is the meaningful signal here, not per-element delta."
    )

    return per_class_results


if __name__ == "__main__":
    main()
