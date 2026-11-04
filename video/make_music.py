"""Generate the demo video's music bed (original, made for this video).

A warm ambient loop synthesized with numpy: pad chords (Am9, Fmaj7, C,
Gsus), a soft sine bass, a quiet plucked arpeggio, a light pulse, and a
simple echo. No samples or third-party audio, so there are no rights
issues. The video mixes it under the narration and ducks it while speech
plays.

  python video/make_music.py OUT.wav [seconds]
"""

import sys

import numpy as np

SR = 44100
BPM = 84
BEAT = 60.0 / BPM
BAR = 4 * BEAT


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12.0)


CHORDS = [  # (bass, chord tones) in MIDI notes
    (45, [57, 60, 64, 67, 71]),   # Am9
    (41, [57, 60, 64, 65, 69]),   # Fmaj7
    (48, [55, 60, 64, 67, 72]),   # C
    (43, [55, 59, 62, 67, 69]),   # Gsus-ish
]


def env(n, attack, release):
    e = np.ones(n)
    a = max(1, int(attack * SR))
    r = max(1, int(release * SR))
    e[:a] = np.linspace(0, 1, a)
    e[-r:] *= np.linspace(1, 0, r)
    return e


def pad_voice(freq, n, t0):
    t = (np.arange(n) + t0) / SR
    out = np.zeros(n)
    for det in (-0.12, 0.0, 0.11):           # three detuned voices
        f = freq * 2 ** (det / 12)
        for h, amp in ((1, 1.0), (2, 0.35), (3, 0.16), (4, 0.07)):
            out += amp * np.sin(2 * np.pi * f * h * t)
    lfo = 0.85 + 0.15 * np.sin(2 * np.pi * 0.11 * t)
    return out * lfo


def pluck(freq, n):
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * 2 * freq * t)
    return tone * np.exp(-t * 5.5)


def make(seconds):
    n = int(seconds * SR)
    out = np.zeros(n + SR * 4)
    rng = np.random.default_rng(7)
    bars = int(np.ceil(seconds / BAR)) + 1
    for b in range(bars):
        bass, tones = CHORDS[b % len(CHORDS)]
        start = int(b * BAR * SR)
        length = min(int(BAR * SR * 1.15), len(out) - start)   # slight overlap between chords
        if length < SR:
            break
        seg = slice(start, start + length)
        e = env(length, 0.9, 1.2)
        chord = sum(pad_voice(midi(m), length, start) for m in tones)
        out[seg] += 0.028 * chord * e
        t = np.arange(length) / SR
        out[seg] += 0.10 * np.sin(2 * np.pi * midi(bass) * t) * env(length, 0.3, 1.0)
        # Plucked arpeggio on eighth notes, from bar 2 on.
        if b >= 2:
            pattern = [tones[i % len(tones)] + 12 for i in (0, 2, 4, 1, 3, 2, 4, 1)]
            for k, m in enumerate(pattern):
                s0 = start + int(k * BEAT / 2 * SR)
                ln = int(0.9 * SR)
                if s0 + ln < len(out):
                    out[s0:s0 + ln] += 0.035 * pluck(midi(m), ln)
        # Light pulse: filtered noise on beats 2 and 4, from bar 4 on.
        if b >= 4:
            for k in (1, 3):
                s0 = start + int(k * BEAT * SR)
                ln = int(0.08 * SR)
                if s0 + ln < len(out):
                    burst = rng.standard_normal(ln) * np.exp(-np.arange(ln) / SR * 60)
                    out[s0:s0 + ln] += 0.012 * np.convolve(burst, np.ones(6) / 6, "same")
    # Echo, then a gentle low-pass.
    d = int(BEAT * 0.75 * SR)
    wet = np.zeros_like(out)
    for k, g in ((1, 0.32), (2, 0.16), (3, 0.08)):
        wet[d * k:] += g * out[:-d * k]
    out = out + wet
    out = np.convolve(out, np.ones(5) / 5, "same")
    out = out[:n]
    fade_in, fade_out = int(2.5 * SR), int(4.0 * SR)
    out[:fade_in] *= np.linspace(0, 1, fade_in)
    out[-fade_out:] *= np.linspace(1, 0, fade_out)
    out = out / (np.max(np.abs(out)) + 1e-9) * 0.6
    return np.stack([out, out], axis=1).astype(np.float32)


def main():
    import soundfile as sf
    out = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 180
    sf.write(out, make(seconds), SR)
    print("wrote", out, seconds, "s")


if __name__ == "__main__":
    main()
