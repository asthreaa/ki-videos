import base64
import json
import os
import subprocess
import wave
import numpy as np
import requests
import imageio_ffmpeg

WORKSPACE = "/home/orca/orca/workspaces/ki videos/ki-videos"
BUILD_DIR = os.path.join(WORKSPACE, "build")
os.makedirs(BUILD_DIR, exist_ok=True)

def load_env():
    env_path = os.path.join(WORKSPACE, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

# Calm, soothing ~60s script (spoken unhurriedly by Christian - Warm & Captivating):
SEGMENTS = [
    {
        "id": "hook_closeup",
        "text": "Tag eins auf dem verdreckten Mond. Willkommen in unserer ersten Basis."
    },
    {
        "id": "overview_goal",
        "text": "Noch bin ich ganz allein. Aber in Teil zwei fliegt jeder neue Follower mit auf den Mond, bekommt eine eigene Kapsel und hilft beim Saubermachen."
    },
    {
        "id": "stages_grid",
        "text": "Deine Kapsel kannst du in zwölf Stufen ausbauen – vom Zelt bis zur Mond-Krone."
    },
    {
        "id": "dust_counter",
        "text": "Ich fege jetzt vor der Schleuse und verkaufe den Staub am Terminal. Das bringt fünfhundert Euro. Und pro Kommentar gibt es einen Punkt für deine Kapsel."
    },
    {
        "id": "id_card",
        "text": "Jeder Follower erhält auch seinen Mond-Ausweis. Schreib deinen Berufswunsch in die Kommentare."
    },
    {
        "id": "vote_abc",
        "text": "Was bauen wir von den fünfhundert Euro zuerst? A: Das Power-Sauger-Lager, B: Die Staub-Raffinerie, oder C: Den Mond-Dönerladen? Schreib A, B oder C."
    },
    {
        "id": "mystery_outro",
        "text": "Doch schaut mal: Unter dem Staub lag dieser Ausweis. Sektor Sieben – nur für Personal. Wir sind nicht allein... Folg rein für Teil zwei."
    }
]

# Warm, calm, soothing German storyteller voice ("Christian - Warm and Captivating")
VOICE_ID = "NBqeXKdZHweef6y0B67V"
MODEL_ID = "eleven_multilingual_v2"

def generate_elevenlabs_tts():
    load_env()
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ELEVENLABS_API_KEY in .env")

    full_text = " ".join(seg["text"] for seg in SEGMENTS)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/with-timestamps"
    payload = {
        "text": full_text,
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": 0.68,
            "similarity_boost": 0.80,
            "style": 0.12,
            "use_speaker_boost": True,
            "speed": 1.05
        }
    }
    print("Requesting ElevenLabs TTS (Christian - Warm & Calm) with character-level timestamps...")
    r = requests.post(
        url,
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=60
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs API error {r.status_code}: {r.text}")

    data = r.json()
    mp3_bytes = base64.b64decode(data["audio_base64"])
    mp3_path = os.path.join(BUILD_DIR, "voice_raw.mp3")
    with open(mp3_path, "wb") as f:
        f.write(mp3_bytes)

    align = data["alignment"]
    chars = align["characters"]
    starts = align["character_start_times_seconds"]
    ends = align["character_end_times_seconds"]

    words = []
    cur_chars = []
    w_start = None
    w_end = None

    for ch, s_t, e_t in zip(chars, starts, ends):
        if ch.isspace():
            if cur_chars:
                word_str = "".join(cur_chars)
                if word_str not in ("–", "—", "-"):
                    words.append({
                        "word": word_str,
                        "start": round(float(w_start), 3),
                        "end": round(float(w_end), 3)
                    })
                cur_chars = []
                w_start = None
                w_end = None
        else:
            if w_start is None:
                w_start = s_t
            w_end = e_t
            cur_chars.append(ch)

    if cur_chars:
        word_str = "".join(cur_chars)
        if word_str not in ("–", "—", "-"):
            words.append({
                "word": word_str,
                "start": round(float(w_start), 3),
                "end": round(float(w_end), 3)
            })

    with open(os.path.join(BUILD_DIR, "words.json"), "w", encoding="utf-8") as wf:
        json.dump(words, wf, ensure_ascii=False, indent=2)

    print(f"ElevenLabs TTS complete: {len(words)} words, exact speech end = {words[-1]['end']:.2f}s")
    return mp3_path, words

def make_sfx_track(duration_sec, words, sample_rate=44100):
    n_samples = int(duration_sec * sample_rate)
    audio = np.zeros(n_samples, dtype=np.float32)

    def add_tone(start_s, dur_s, f_start, f_end, vol=0.10, wave_type="sine"):
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
        env = np.exp(-3.8 * t / dur_s) * np.minimum(1.0, t / 0.01)
        audio[i0:i0+n] += vol * sig * env

    def add_whoosh(start_s, dur_s=0.42, vol=0.13):
        i0 = int(start_s * sample_rate)
        n = int(dur_s * sample_rate)
        if i0 >= n_samples or n <= 0:
            return
        n = min(n, n_samples - i0)
        t = np.linspace(0, dur_s, n, endpoint=False)
        rng = np.random.default_rng(int(start_s * 100) + 7)
        noise = rng.normal(0, 1, n)
        kernel = np.ones(55) / 55.0
        filtered = np.convolve(noise, kernel, mode="same")
        sweep = np.sin(2 * np.pi * np.linspace(120, 420, n) * t) * 0.35
        env = np.sin(np.pi * t / dur_s) ** 1.4
        audio[i0:i0+n] += vol * (filtered + sweep) * env

    def add_mystery_boom(start_s, dur_s=2.2, vol=0.16):
        i0 = int(start_s * sample_rate)
        n = int(dur_s * sample_rate)
        if i0 >= n_samples or n <= 0:
            return
        n = min(n, n_samples - i0)
        t = np.linspace(0, dur_s, n, endpoint=False)
        freqs = np.linspace(88, 36, n)
        phase = 2 * np.pi * np.cumsum(freqs) / sample_rate
        sig = np.sin(phase) + 0.3 * np.sin(phase * 1.5)
        env = np.exp(-2.2 * t / dur_s) * np.minimum(1.0, t / 0.02)
        audio[i0:i0+n] += vol * sig * env

    # Soft, calming ambient space pad
    t_all = np.linspace(0, duration_sec, n_samples, endpoint=False)
    pad = (
        0.010 * np.sin(2 * np.pi * 110.0 * t_all)
        + 0.007 * np.sin(2 * np.pi * 164.81 * t_all)
    )
    audio += pad

    def find_word_time(substr, min_t=0.0):
        for w in words:
            if substr.lower() in w["word"].lower() and w["start"] >= min_t:
                return w["start"]
        return None

    t_overview = find_word_time("Noch", 2.5) or 5.5
    t_stages = find_word_time("Deine", 10.0) or 15.0
    t_terminal = find_word_time("fege", 15.0) or 21.0
    t_budget = find_word_time("fünfhundert", 18.0) or 26.5
    t_punkt = find_word_time("Punkt", 22.0) or 29.5
    t_ausweis = find_word_time("Mond-Ausweis", 26.0) or 34.0
    t_vote = find_word_time("Was", 30.0) or 39.0
    t_opt_a = find_word_time("Power-Sauger", 33.0) or 42.5
    t_opt_b = find_word_time("Staub-Raffinerie", 35.0) or 45.0
    t_opt_c = find_word_time("Mond-Dönerladen", 37.0) or 47.5
    t_mystery = find_word_time("schaut", 42.0) or 51.0
    t_sektor7 = find_word_time("Sektor", 45.0) or 54.5
    t_outro = find_word_time("Folg", 48.0) or (duration_sec - 2.5)

    add_tone(0.05, 0.22, 440, 660, vol=0.10, wave_type="triangle")
    add_whoosh(t_overview - 0.2, 0.42, vol=0.13)

    add_whoosh(t_stages - 0.25, 0.35, vol=0.11)
    for i in range(12):
        freq = 360 + i * 42
        add_tone(t_stages + 0.1 + i * 0.28, 0.11, freq, freq * 1.2, vol=0.09, wave_type="triangle")

    add_whoosh(t_terminal - 0.2, 0.35, vol=0.11)
    for i in range(3):
        add_tone(t_budget - 0.2 + i * 0.32, 0.15, 780 + i * 180, 980 + i * 180, vol=0.10, wave_type="sine")
    add_tone(t_punkt, 0.2, 523.25, 1046.5, vol=0.10, wave_type="triangle")

    add_whoosh(t_ausweis - 0.25, 0.35, vol=0.11)
    add_tone(t_ausweis, 0.2, 523.25, 659.25, vol=0.10, wave_type="triangle")

    add_whoosh(t_vote - 0.2, 0.35, vol=0.11)
    for ct, freq in [(t_opt_a, 523.25), (t_opt_b, 659.25), (t_opt_c, 783.99)]:
        add_tone(ct - 0.08, 0.2, freq * 0.85, freq, vol=0.11, wave_type="triangle")

    add_whoosh(t_mystery - 0.2, 0.4, vol=0.13)
    add_mystery_boom(t_mystery, 2.2, vol=0.16)
    add_mystery_boom(t_sektor7 - 0.1, 1.8, vol=0.15)
    add_whoosh(t_outro - 0.2, 0.36, vol=0.13)

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

def main():
    mp3_path, words = generate_elevenlabs_tts()
    raw_end = words[-1]["end"] if words else 58.5
    target_duration = round(raw_end + 0.8, 2)
    sfx_wav, markers = make_sfx_track(target_duration, words)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    final_audio = os.path.join(BUILD_DIR, "audio_mix.aac")
    cmd = [
        ffmpeg, "-y",
        "-i", mp3_path,
        "-i", sfx_wav,
        "-filter_complex",
        f"[0:a]apad=whole_dur={target_duration}[v];[1:a]volume=0.75[s];[v][s]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[out]",
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
    main()
