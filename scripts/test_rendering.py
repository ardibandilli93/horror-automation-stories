"""Offline regression tests: no API calls, uploads or processed-state changes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import captions
import render
import synthesize_whisper


class CaptionTests(unittest.TestCase):
    def test_centered_short_lines_and_scaled_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.srt"
            target = Path(directory) / "output.ass"
            source.write_text("1\n00:00:02,000 --> 00:00:08,000\n"
                              r"{\an8\pos(0,0)}<b>Someone stood outside my bedroom window.</b>" + "\n")
            captions.write_centered_ass(source, target, 0.5)
            result = target.read_text()
            self.assertIn("PlayResX: 1080", result)
            self.assertIn("PlayResY: 1920", result)
            self.assertNotIn(r"\an8", result)
            events = [line for line in result.splitlines() if line.startswith("Dialogue:")]
            self.assertTrue(events)
            self.assertIn("0:00:01.00", events[0])
            self.assertIn("0:00:04.00", events[-1])
            for event in events:
                self.assertIn(r"{\an5\pos(540,960)}", event)
                lines = event.split("}", 1)[1].split(r"\N")
                self.assertLessEqual(len(lines), 2)
                self.assertTrue(all(len(line) <= 18 for line in lines))

    def test_no_captions_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.srt"
            source.write_text("")
            with self.assertRaises(ValueError):
                captions.write_centered_ass(source, Path(directory) / "out.ass")

    def test_timestamp_carry(self):
        self.assertEqual(captions.ass_time(59.999), "0:01:00.00")
        self.assertEqual(synthesize_whisper.srt_time(59.9999), "00:01:00,000")

    def test_paid_mode_needs_explicit_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "paid opt-in"):
                synthesize_whisper.synthesize_openai(None)

    def test_complete_offline_render(self):
        # Exercise production filters, subtitle burning, audio fitting and metadata.
        # Synthesized test tone replaces ONLY the external TTS service.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            background = root / "background.mp4"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            "color=c=black:s=1080x1920:r=30:d=1", "-c:v", "libx264",
                            "-preset", "ultrafast", str(background)], check=True)
            story = root / "story.json"
            story.write_text(json.dumps({"id": "test", "title": "Test",
                "narration": "Someone was outside. " * 30, "description": "Test",
                "voice": "en-GB-SoniaNeural", "background": str(background)}))
            original_run = render.run
            calls = []

            def stub_tts(command):
                if len(command) > 1 and str(command[1]).endswith("synthesize_whisper.py"):
                    calls.append(command)
                    audio = command[command.index("--audio") + 1]
                    subtitle = command[command.index("--subtitles") + 1]
                    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
                                    "-i", "sine=frequency=200:duration=1", str(audio)], check=True)
                    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nSomeone stood outside\n")
                else:
                    original_run(command)

            with patch.object(render, "ROOT", root), patch.object(render, "run", stub_tts), \
                    patch.dict(os.environ, {}, clear=True):
                render.render(story, root / "output")
            self.assertIn("en-GB-RyanNeural", calls[0])
            self.assertIn("--rate=-10%", calls[0])
            metadata = json.loads((root / "output/test.json").read_text())
            self.assertEqual(metadata["caption_position"], [540, 960])
            self.assertEqual(metadata["renderer_version"], "centered-v2")
            frame = subprocess.check_output(["ffmpeg", "-loglevel", "error", "-ss", "0.5", "-i",
                str(root / "output/test.mp4"), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"])
            points = [(i % 1080, i // 1080) for i, value in enumerate(frame) if value > 180]
            self.assertTrue(points)
            left, right = min(x for x, y in points), max(x for x, y in points)
            top, bottom = min(y for x, y in points), max(y for x, y in points)
            self.assertGreater(left, 108)
            self.assertLess(right, 972)
            self.assertAlmostEqual((left + right) / 2, 540, delta=15)
            self.assertAlmostEqual((top + bottom) / 2, 960, delta=15)
            print(f"Verified actual burned captions: x={left}..{right}, y={top}..{bottom}")
            if os.environ.get("TEST_PREVIEW_FRAME"):
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "0.5", "-i",
                    str(root / "output/test.mp4"), "-frames:v", "1",
                    os.environ["TEST_PREVIEW_FRAME"]], check=True)


if __name__ == "__main__":
    unittest.main()
