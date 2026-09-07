#!/usr/bin/env python3
import argparse
import asyncio
from pathlib import Path

import edge_tts
import edge_tts.communicate as communicate_module


def whisper_ssml(config, escaped_text):
    if isinstance(escaped_text, bytes):
        escaped_text = escaped_text.decode("utf-8")
    return (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
        "xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-GB'>"
        f"<voice name='{config.voice}'>"
        "<mstts:express-as style='whispering' styledegree='1.35'>"
        f"<prosody pitch='{config.pitch}' rate='{config.rate}' volume='{config.volume}'>"
        f"{escaped_text}</prosody></mstts:express-as></voice></speak>"
    )


async def synthesize(args):
    communicate_module.mkssml = whisper_ssml
    speaker = edge_tts.Communicate(
        args.text, args.voice, rate=args.rate, volume=args.volume,
        pitch=args.pitch, boundary="SentenceBoundary"
    )
    subtitles = edge_tts.SubMaker()
    with Path(args.audio).open("wb") as audio:
        async for item in speaker.stream():
            if item["type"] == "audio":
                audio.write(item["data"])
            elif item["type"] in ("WordBoundary", "SentenceBoundary"):
                subtitles.feed(item)
    Path(args.subtitles).write_text(subtitles.get_srt(), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--voice", default="en-GB-RyanNeural")
    parser.add_argument("--rate", default="+6%")
    parser.add_argument("--volume", default="-18%")
    parser.add_argument("--pitch", default="-10Hz")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--subtitles", required=True)
    asyncio.run(synthesize(parser.parse_args()))


if __name__ == "__main__":
    main()
