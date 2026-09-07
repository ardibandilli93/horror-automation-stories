#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

import requests


INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", type=Path, default=Path("output"))
    parser.add_argument("--state", type=Path)
    args = parser.parse_args()
    output_dir = args.output
    token = os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing TIKTOK_ACCESS_TOKEN")
    privacy = os.environ.get("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}

    for metadata_path in sorted(output_dir.glob("*.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        video_path = output_dir / metadata["video"]
        size = video_path.stat().st_size
        payload = {
            "post_info": {
                "title": metadata["description"][:2200],
                "privacy_level": privacy,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
                "is_aigc": True,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": size,
                "total_chunk_count": 1,
            },
        }
        response = requests.post(INIT_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json().get("data", {})
        upload_url = data["upload_url"]
        with video_path.open("rb") as video:
            upload = requests.put(
                upload_url,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(size),
                    "Content-Range": f"bytes 0-{size - 1}/{size}",
                },
                data=video,
                timeout=300,
            )
        upload.raise_for_status()
        print(f"Sent {video_path.name} to TikTok; publish_id={data.get('publish_id')}")
        if args.state:
            processed = set()
            if args.state.exists():
                processed = set(json.loads(args.state.read_text(encoding="utf-8")))
            processed.add(metadata["id"])
            args.state.parent.mkdir(parents=True, exist_ok=True)
            args.state.write_text(
                json.dumps(sorted(processed), indent=2) + "\n", encoding="utf-8"
            )


if __name__ == "__main__":
    main()
