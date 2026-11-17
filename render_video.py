import asyncio
import json
import os
import subprocess
import sys
from playwright.async_api import async_playwright
import imageio_ffmpeg

WORKSPACE = "/home/orca/orca/workspaces/ki videos/ki-videos"
BUILD_DIR = os.path.join(WORKSPACE, "build")
SCENE_HTML = f"file://{os.path.join(BUILD_DIR, 'scene.html')}"

async def render_preview_frames():
    with open(os.path.join(BUILD_DIR, "timeline.json"), "r", encoding="utf-8") as f:
        timeline = json.load(f)
    with open(os.path.join(BUILD_DIR, "words.json"), "r", encoding="utf-8") as f:
        words = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
        )
        page = await browser.new_page(viewport={"width": 1080, "height": 1920, "device_scale_factor": 1})
        await page.goto(SCENE_HTML)

        await page.evaluate(
            """([tl, wds]) => {
                window.TIMELINE = tl;
                window.WORDS = wds;
                if (typeof buildSubChunks === 'function') {
                    window.SUB_CHUNKS = buildSubChunks(wds);
                }
            }""",
            [timeline, words]
        )

        test_times = [1.2, 3.5, 8.5, 17.5, 30.5, 47.0, 56.5, 60.0]
        for idx, t in enumerate(test_times):
            await page.evaluate(f"window.setTime({t})")
            out_path = os.path.join(BUILD_DIR, f"preview_{idx}_{t:.1f}s.jpg")
            await page.screenshot(path=out_path, type="jpeg", quality=92)
            print("Saved preview:", out_path)

        await browser.close()

async def render_full_video(fps=30):
    with open(os.path.join(BUILD_DIR, "timeline.json"), "r", encoding="utf-8") as f:
        timeline = json.load(f)
    with open(os.path.join(BUILD_DIR, "words.json"), "r", encoding="utf-8") as f:
        words = json.load(f)

    duration = timeline["duration"]
    total_frames = int(round(duration * fps))
    out_mp4 = os.path.join(WORKSPACE, "Mond_Projekt_Teil_1.mp4")
    audio_path = os.path.join(BUILD_DIR, "audio_mix.aac")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg, "-y",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-r", str(fps),
        "-i", "-",
        "-i", audio_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        out_mp4
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
        )
        page = await browser.new_page(viewport={"width": 1080, "height": 1920, "device_scale_factor": 1})
        await page.goto(SCENE_HTML)

        await page.evaluate(
            """([tl, wds]) => {
                window.TIMELINE = tl;
                window.WORDS = wds;
                if (typeof buildSubChunks === 'function') {
                    window.SUB_CHUNKS = buildSubChunks(wds);
                }
            }""",
            [timeline, words]
        )

        print(f"Rendering {total_frames} frames ({duration:.2f}s @ {fps} FPS)...")
        for frame_idx in range(total_frames):
            t = frame_idx / float(fps)
            await page.evaluate(f"window.setTime({t:.4f})")
            jpg_bytes = await page.screenshot(type="jpeg", quality=92)
            proc.stdin.write(jpg_bytes)
            if frame_idx % (fps * 5) == 0 or frame_idx == total_frames - 1:
                print(f"  Progress: {frame_idx}/{total_frames} frames ({t:.1f}s / {duration:.1f}s)")

        await browser.close()

    proc.stdin.close()
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"FFmpeg exited with code {ret}")
    print("Successfully rendered:", out_mp4)

    # Automatically commit and push rendered video to GitHub (asthreaa/ki-videos)
    try:
        subprocess.run(["git", "add", out_mp4, "generate_audio.py", "render_video.py", "build/scene.html", "build/timeline.json", "build/words.json", "build/audio_mix.aac"], cwd=WORKSPACE, check=False)
        subprocess.run(["git", "commit", "-m", "Auto-Upload: Aktualisiertes Video Mond_Projekt_Teil_1.mp4"], cwd=WORKSPACE, check=False)
        subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=WORKSPACE, check=False)
        subprocess.run(["git", "push", "origin", "ki-videos"], cwd=WORKSPACE, check=False)
        subprocess.run(["gh", "release", "upload", "teil-1", out_mp4, "--clobber", "--repo", "asthreaa/ki-videos"], cwd=WORKSPACE, check=False)
        print("Automatically pushed video to https://github.com/asthreaa/ki-videos")
    except Exception as e:
        print("Git auto-push warning:", e)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"
    if mode == "preview":
        asyncio.run(render_preview_frames())
    else:
        asyncio.run(render_full_video(fps=30))
