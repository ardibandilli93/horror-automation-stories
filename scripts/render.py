#!/usr/bin/env python3
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command):
    print("+", " ".join(str(part) for part in command))
    subprocess.run([str(part) for part in command], check=True)


def require_binary(name):
    if not shutil.which(name):
        raise RuntimeError(f"Required executable not found: {name}")


def media_files(directory, extensions):
    if not directory.exists():
        return []
    return sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in extensions
    )


def choose_asset(configured, directory, extensions, required):
    if configured:
        candidate = ROOT / configured
        if not candidate.exists():
            raise FileNotFoundError(f"Configured asset does not exist: {candidate}")
        return candidate
    candidates = media_files(directory, extensions)
    if not candidates:
        if required:
            raise FileNotFoundError(f"Add at least one supported media file to {directory}")
        return None
    return random.choice(candidates)


def duration_seconds(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def render(story_path, output_dir):
    story = json.loads(story_path.read_text(encoding="utf-8"))
    required = ("id", "title", "narration", "description")
    missing = [key for key in required if not str(story.get(key, "")).strip()]
    if missing:
        raise ValueError(f"{story_path}: missing {', '.join(missing)}")

    words = len(story["narration"].split())
    if not 80 <= words <= 175:
        raise ValueError(f"{story_path}: narration has {words} words; expected 80-175")

    background = choose_asset(
        story.get("background", ""), ROOT / "assets/backgrounds",
        {".mp4", ".mov", ".mkv", ".webm"}, True,
    )
    music = choose_asset(
        story.get("music", ""), ROOT / "assets/music",
        {".mp3", ".wav", ".m4a", ".aac"}, False,
    )

    work_dir = ROOT / "work" / story["id"]
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    narration = work_dir / "narration.mp3"
    subtitles = work_dir / "captions-centered.srt"
    ass_subtitles = work_dir / "captions-centered.ass"
    output = output_dir / f"{story['id']}.mp4"
    voice = os.environ.get("NARRATION_VOICE", "en-GB-RyanNeural")
    speech_rate = os.environ.get("NARRATION_RATE", "+6%")
    speech_volume = os.environ.get("NARRATION_VOLUME", "-18%")
    speech_pitch = os.environ.get("NARRATION_PITCH", "-10Hz")

    run([
        sys.executable, ROOT / "scripts/synthesize_whisper.py",
        "--voice", voice, f"--rate={speech_rate}", f"--volume={speech_volume}",
        f"--pitch={speech_pitch}", "--text", story["narration"],
        "--audio", narration, "--subtitles", subtitles,
    ])

    run(["ffmpeg", "-y", "-i", subtitles, ass_subtitles])
    ass_text = ass_subtitles.read_text(encoding="utf-8")
    centered_style = (
        "Style: Default,Arial,18,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,3,1,5,55,55,0,1"
    )
    ass_text = re.sub(r"(?m)^Style: Default,.*$", centered_style, ass_text)
    ass_text = re.sub(r"\\{\\(?:an|pos|move)[^}]*\\}", "", ass_text)
    ass_subtitles.write_text(ass_text, encoding="utf-8")

    duration = duration_seconds(narration) + 0.35
    if duration > 60:
        raise ValueError(
            f"{story_path}: generated narration is {duration:.1f}s; shorten it below 60s"
        )

    escaped_subtitles = str(ass_subtitles).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    video_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "eq=brightness=-0.10:saturation=0.75,"
        f"subtitles='{escaped_subtitles}':force_style='FontName=Arial,FontSize=18,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,"
        "Outline=3,Shadow=1,Alignment=5,MarginL=55,MarginR=55,MarginV=0,WrapStyle=0'"
    )

    command = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", background, "-i", narration]
    if music:
        command += ["-stream_loop", "-1", "-i", music]
        command += [
            "-filter_complex",
            f"[0:v]{video_filter}[v];[2:a]volume=0.055[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=1[a]",
            "-map", "[v]", "-map", "[a]",
        ]
    else:
        command += ["-vf", video_filter, "-map", "0:v:0", "-map", "1:a:0"]

    command += [
        "-t", f"{duration:.3f}", "-r", "30", "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", output,
    ]
    run(command)

    metadata = {
        "id": story["id"],
        "title": story["title"],
        "description": story["description"],
        "duration_seconds": round(duration_seconds(output), 2),
        "video": output.name,
    }
    (output_dir / f"{story['id']}.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Rendered {output} ({metadata['duration_seconds']}s)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=ROOT / "content/queue")
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    for binary in ("ffmpeg", "ffprobe"):
        require_binary(binary)
    stories = sorted(args.queue.glob("*.json"))
    if not stories:
        print("No queued stories found")
        return
    processed = set()
    if args.state and args.state.exists():
        processed = set(json.loads(args.state.read_text(encoding="utf-8")))
    rendered = 0
    for story in stories:
        story_id = json.loads(story.read_text(encoding="utf-8")).get("id")
        if story_id in processed:
            print(f"Skipping previously processed story: {story_id}")
            continue
        render(story, args.output)
        rendered += 1
        if args.limit and rendered >= args.limit:
            break


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
