#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def main():
    output_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "output")
    credentials = Credentials(
        token=None,
        refresh_token=required("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=required("YOUTUBE_CLIENT_ID"),
        client_secret=required("YOUTUBE_CLIENT_SECRET"),
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    privacy = os.environ.get("YOUTUBE_PRIVACY_STATUS", "private")
    for metadata_path in sorted(output_dir.glob("*.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        video_path = output_dir / metadata["video"]
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": metadata["title"][:100],
                    "description": metadata["description"][:5000],
                    "categoryId": "24",
                },
                "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
            },
            media_body=MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True),
        )
        response = request.execute()
        print(f"Uploaded {video_path.name}: https://youtu.be/{response['id']}")


if __name__ == "__main__":
    main()
