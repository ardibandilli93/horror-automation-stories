#!/usr/bin/env python3
"""Free low Ryan speech, or explicitly opted-in OpenAI whispered narration."""
import argparse
import asyncio
import os
from pathlib import Path


def srt_time(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


async def synthesize_edge(args):
    import edge_tts
    # This endpoint does not support custom express-as SSML.
    # Never switch voices or label ordinary speech a true whisper.
    for attempt in range(3):
        try:
            speaker = edge_tts.Communicate(
                args.text, args.voice, rate=args.rate, volume=args.volume,
                pitch=args.pitch, boundary="WordBoundary",
            )
            subtitles = edge_tts.SubMaker()
            with Path(args.audio).open("wb") as audio:
                async for item in speaker.stream():
                    if item["type"] == "audio":
                        audio.write(item["data"])
                    elif item["type"] == "WordBoundary":
                        subtitles.feed(item)
            content = subtitles.get_srt()
            if not Path(args.audio).stat().st_size or not content.strip():
                raise RuntimeError("TTS returned empty audio or subtitles")
            Path(args.subtitles).write_text(content, encoding="utf-8")
            return
        except (edge_tts.exceptions.NoAudioReceived, TimeoutError, ConnectionError):
            if attempt == 2:
                raise
            print(f"Temporary TTS failure; retrying the same voice ({attempt + 2}/3)")
            await asyncio.sleep(2 ** attempt)


def synthesize_openai(args):
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OpenAI whisper mode requires OPENAI_API_KEY; it is a paid opt-in")
    from openai import OpenAI
    client = OpenAI(timeout=120, max_retries=2)
    print("Using paid OpenAI whispered narration and timestamp transcription")
    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice=os.environ.get("OPENAI_TTS_VOICE", "onyx"),
        input=args.text,
        instructions=("Read only the supplied story in a low, breathy, intimate whisper. "
                      "Use restrained British horror narration and a calm, deliberate pace. "
                      "Whisper throughout; do not use a projecting announcer voice. "
                      "Keep pauses short and preserve every word."),
        response_format="mp3",
    ) as response:
        response.stream_to_file(args.audio)
    with Path(args.audio).open("rb") as audio:
        transcript = client.audio.transcriptions.create(
            model="whisper-1", file=audio, language="en",
            response_format="verbose_json", timestamp_granularities=["word"],
            prompt=args.text,
        )
    words = transcript.words or []
    if not words:
        raise RuntimeError("OpenAI returned no word timestamps; refusing uncaptioned video")
    cues = [f"{i}\n{srt_time(word.start)} --> {srt_time(word.end)}\n{word.word}\n"
            for i, word in enumerate(words, 1) if word.end > word.start]
    Path(args.subtitles).write_text("\n".join(cues), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--voice", default="en-GB-RyanNeural")
    parser.add_argument("--rate", default="-10%")
    parser.add_argument("--volume", default="-18%")
    parser.add_argument("--pitch", default="-10Hz")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--subtitles", required=True)
    args = parser.parse_args()
    backend = os.environ.get("NARRATION_BACKEND", "edge")
    print(f"Narration backend: {backend}")
    if backend == "openai":
        synthesize_openai(args)
    elif backend == "edge":
        print(f"Voice: {args.voice} (low spoken voice, not true whisper)")
        asyncio.run(synthesize_edge(args))
    else:
        raise ValueError(f"Unknown narration backend: {backend}")


if __name__ == "__main__":
    main()
