import asyncio
import json
import os
import re
import subprocess
import wave
import numpy as np
import edge_tts
import imageio_ffmpeg

WORKSPACE = "/home/orca/orca/workspaces/ki videos/ki-videos"
BUILD_DIR = os.path.join(WORKSPACE, "build")
os.makedirs(BUILD_DIR, exist_ok=True)

# High-retention ~60s script modeled on @das.letzte.camp + Moon Sweepers (no spoilers for cleaning car or aliens!)
SEGMENTS = [
    {
        "id": "hook_closeup",
        "text": "Tag eins auf dem völlig verdreckten Mond! Willkommen in unserer allerersten Mond-Basis!"
    },
    {
        "id": "overview_goal",
        "text": "Ab heute fegen wir diesen Planeten Stück für Stück frei und bauen aus einer winzigen Kapsel eine riesige Stadt! Jeder neue Follower zieht als Astronaut hier ein!"
    },
    {
        "id": "stages_grid",
        "text": "Aus Staub wird Zukunft: Zwölf Stufen – vom einfachen Schrubber und Zelt bis zur gigantischen Mond-Krone! Ausbauen können wir die Basis gemeinsam in jedem Video!"
    },
    {
        "id": "dust_counter",
        "text": "Wir fegen den Mondstaub und verkaufen ihn direkt am Terminal! Der erste Ring vor der Schleuse ist sauber – das bringt uns direkt fünfhundert Euro Startbudget! Und ab sofort gilt: Pro Kommentar bekommst du einen Ausbau-Punkt für deine eigene Kapsel!"
    },
    {
        "id": "id_card",
        "text": "Jeder von euch bekommt seinen eigenen Mond-Ausweis! Schreib deinen Berufswunsch, Nachbarwunsch und Gebäudewunsch jetzt in die Kommentare!"
    },
    {
        "id": "vote_abc",
        "text": "Was bauen wir von unseren fünfhundert Euro zuerst? A: Das große Power-Sauger-Lager, B: Den zweiten Kapsel-Ring für neue Follower, oder C: Den ersten Mond-Dönerladen? Schreib A, B oder C in die Kommentare!"
    },
    {
        "id": "mystery_outro",
        "text": "Doch wartet mal: Beim Fegen haben wir unter dem Staub etwas gefunden. Einen gesperrten Ausweis: Sektor Sieben – Zutritt nur für Personal! Irgendjemand war schon vor uns auf dem Mond... Fortsetzung folgt!"
    }
]

VOICE = "de-DE-KillianNeural"
RATE = "+38%"

async def generate_tts():
    full_text = " ".join(seg["text"] for seg in SEGMENTS)
    communicate = edge_tts.Communicate(full_text, VOICE, rate=RATE, boundary="WordBoundary")
    
    mp3_path = os.path.join(BUILD_DIR, "voice_raw.mp3")
    words = []
    
    with open(mp3_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start_s = chunk["offset"] / 10_000_000.0
                dur_s = chunk["duration"] / 10_000_000.0
                words.append({
                    "word": chunk["text"],
                    "start": round(start_s, 3),
                    "end": round(start_s + dur_s, 3)
                })
    
    tokens = [t for t in full_text.split() if t not in ("–", "—", "-")]
    ti = 0
    for w in words:
        clean_w = re.sub(r"[^\wÄÖÜäöüß]", "", w["word"])
        for look in range(ti, min(ti + 4, len(tokens))):
            clean_t = re.sub(r"[^\wÄÖÜäöüß]", "", tokens[look])
            if clean_w.lower() == clean_t.lower() or clean_w.lower() in clean_t.lower():
                w["word"] = tokens[look]
                ti = look + 1
                break

    with open(os.path.join(BUILD_DIR, "words.json"), "w", encoding="utf-8") as wf:
        json.dump(words, wf, ensure_ascii=False, indent=2)
        
    print(f"Generated TTS with {len(words)} words. Last word ends at {words[-1]['end'] if words else 0:.2f}s")
    return mp3_path, words

def make_sfx_track(duration_sec, words, sample_rate=44100):
    n_samples = int(duration_sec * sample_rate)
    audio = np.zeros(n_samples, dtype=np.float32)

    def add_tone(start_s, dur_s, f_start, f_end, vol=0.14, wave_type="sine"):
        i0 = int(start_s * sample_rate)
        n = int(dur_s * sample_rate)
        if i0 >= n_samples or n <= 0:
            return
        n = min(n, n_samples - i0)
        t = np.linspace(0, dur_s, n, endpoint=False)
        freqs = np.linspace(f_start, f_end, n)
        phase = 2 * np.pi * np.cumsum(freqs) / sample_rate
        if wave_type == "sine":
            sig = np.sin(phase)
        elif wave_type == "triangle":
            sig = 2 * np.abs(2 * (phase / (2 * np.pi) - np.floor(phase / (2 * np.pi) + 0.5))) - 1
        else:
            sig = np.sin(phase)
        env = np.exp(-3.8 * t / dur_s) * np.minimum(1.0, t / 0.008)
        audio[i0:i0+n] += vol * sig * env

    def add_whoosh(start_s, dur_s=0.42, vol=0.18):
        i0 = int(start_s * sample_rate)
        n = int(dur_s * sample_rate)
        if i0 >= n_samples or n <= 0:
            return
        n = min(n, n_samples - i0)
        t = np.linspace(0, dur_s, n, endpoint=False)
        rng = np.random.default_rng(int(start_s * 100) + 7)
        noise = rng.normal(0, 1, n)
        kernel = np.ones(45) / 45.0
        filtered = np.convolve(noise, kernel, mode="same")
        sweep = np.sin(2 * np.pi * np.linspace(140, 520, n) * t) * 0.4
        env = np.sin(np.pi * t / dur_s) ** 1.4
        audio[i0:i0+n] += vol * (filtered + sweep) * env

    def add_mystery_boom(start_s, dur_s=2.2, vol=0.22):
        i0 = int(start_s * sample_rate)
        n = int(dur_s * sample_rate)
        if i0 >= n_samples or n <= 0:
            return
        n = min(n, n_samples - i0)
        t = np.linspace(0, dur_s, n, endpoint=False)
        freqs = np.linspace(95, 38, n)
        phase = 2 * np.pi * np.cumsum(freqs) / sample_rate
        sig = np.sin(phase) + 0.35 * np.sin(phase * 1.5)
        env = np.exp(-2.2 * t / dur_s) * np.minimum(1.0, t / 0.02)
        audio[i0:i0+n] += vol * sig * env

    # Subtle energetic pulse background
    t_all = np.linspace(0, duration_sec, n_samples, endpoint=False)
    pad = (
        0.014 * np.sin(2 * np.pi * 110.0 * t_all)
        + 0.010 * np.sin(2 * np.pi * 164.81 * t_all)
    )
    audio += pad

    def find_word_time(substr, min_t=0.0):
        for w in words:
            if substr.lower() in w["word"].lower() and w["start"] >= min_t:
                return w["start"]
        return None

    t_overview = find_word_time("fegen", 2.5) or 4.2
    t_stages = find_word_time("Zwölf", 8.0) or 13.0
    t_terminal = find_word_time("verkaufen", 18.0) or 22.0
    t_budget = find_word_time("fünfhundert", 22.0) or 27.0
    t_punkt = find_word_time("Ausbau-Punkt", 26.0) or 31.5
    t_ausweis = find_word_time("Mond-Ausweis", 30.0) or 35.5
    t_vote = find_word_time("bauen", 38.0) or 42.5
    t_opt_a = find_word_time("Power-Sauger", 40.0) or 45.0
    t_opt_b = find_word_time("Kapsel-Ring", 42.0) or 47.2
    t_opt_c = find_word_time("Mond-Dönerladen", 44.0) or 49.5
    t_mystery = find_word_time("wartet", 48.0) or 52.5
    t_sektor7 = find_word_time("Sektor", 50.0) or 55.5
    t_outro = find_word_time("Fortsetzung", 54.0) or 58.8

    # Intro pop + Camera Whip-Zoom Whoosh
    add_tone(0.05, 0.22, 440, 880, vol=0.16, wave_type="triangle")
    add_whoosh(t_overview - 0.25, 0.45, vol=0.20)

    # 12-Stages Grid Rapid Pop-in Arpeggio (like @das.letzte.camp!)
    add_whoosh(t_stages - 0.3, 0.35, vol=0.16)
    for i in range(12):
        freq = 380 + i * 48
        add_tone(t_stages + 0.1 + i * 0.28, 0.12, freq, freq * 1.25, vol=0.13, wave_type="triangle")

    # Dust Counter Card & +1 Point pops
    add_whoosh(t_terminal - 0.25, 0.35, vol=0.16)
    for i in range(3):
        add_tone(t_budget - 0.4 + i * 0.35, 0.16, 880 + i * 220, 1100 + i * 220, vol=0.15, wave_type="sine")
    add_tone(t_punkt, 0.22, 587.33, 1174.66, vol=0.16, wave_type="triangle")

    # ID Card Pop
    add_whoosh(t_ausweis - 0.3, 0.35, vol=0.17)
    add_tone(t_ausweis, 0.2, 523.25, 783.99, vol=0.14, wave_type="triangle")

    # Vote Cards A, B, C
    add_whoosh(t_vote - 0.25, 0.35, vol=0.16)
    for ct, freq in [(t_opt_a, 523.25), (t_opt_b, 659.25), (t_opt_c, 783.99)]:
        add_tone(ct - 0.1, 0.22, freq * 0.85, freq, vol=0.16, wave_type="triangle")

    # Mystery Discovery Sub-Bass Boom + Secret Stamp Hit
    add_whoosh(t_mystery - 0.2, 0.4, vol=0.18)
    add_mystery_boom(t_mystery, 2.4, vol=0.24)
    add_mystery_boom(t_sektor7 - 0.1, 2.0, vol=0.22)
    add_whoosh(t_outro - 0.2, 0.38, vol=0.20)

    audio = np.clip(audio, -0.95, 0.95)
    sfx_wav = os.path.join(BUILD_DIR, "sfx.wav")
    with wave.open(sfx_wav, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes((audio * 32767).astype(np.int16).tobytes())
    return sfx_wav, {
        "t_overview": t_overview,
        "t_stages": t_stages,
        "t_terminal": t_terminal,
        "t_budget": t_budget,
        "t_punkt": t_punkt,
        "t_ausweis": t_ausweis,
        "t_vote": t_vote,
        "t_opt_a": t_opt_a,
        "t_opt_b": t_opt_b,
        "t_opt_c": t_opt_c,
        "t_mystery": t_mystery,
        "t_sektor7": t_sektor7,
        "t_outro": t_outro,
    }

async def main():
    mp3_path, words = await generate_tts()
    raw_end = words[-1]["end"] if words else 58.5
    target_duration = max(59.5, round(raw_end + 0.8, 2))
    sfx_wav, markers = make_sfx_track(target_duration, words)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    final_audio = os.path.join(BUILD_DIR, "audio_mix.aac")
    cmd = [
        ffmpeg, "-y",
        "-i", mp3_path,
        "-i", sfx_wav,
        "-filter_complex",
        f"[0:a]apad=whole_dur={target_duration}[v];[1:a]volume=1.0[s];[v][s]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[out]",
        "-map", "[out]",
        "-t", f"{target_duration:.2f}",
        "-c:a", "aac", "-b:a", "192k",
        final_audio
    ]
    subprocess.run(cmd, check=True)
    meta = {
        "duration": target_duration,
        "raw_speech_end": raw_end,
        "markers": markers,
        "word_count": len(words)
    }
    with open(os.path.join(BUILD_DIR, "timeline.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("Audio mix complete:", meta)

if __name__ == "__main__":
    asyncio.run(main())
