#!/usr/bin/env python3
import argparse
import json
import os
import tempfile
import time
from pathlib import Path

import requests


TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
DIRECT_POST_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
DRAFT_UPLOAD_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


def api_data(response, operation):
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = payload.get("error", {})
    if not response.ok or (error and error.get("code") not in (None, "ok")):
        raise RuntimeError(
            f"TikTok {operation} failed (HTTP {response.status_code}): "
            f"{error.get('code', 'unknown')}: {error.get('message', response.text[:500])} "
            f"(log_id={error.get('log_id', 'unknown')})"
        )
    return payload.get("data", {})


def access_token(required_scope):
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("TIKTOK_REFRESH_TOKEN", "").strip()
    if client_key and client_secret and refresh_token:
        response = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise RuntimeError(
                f"TikTok token refresh failed: {payload.get('error')}: "
                f"{payload.get('error_description', '')}"
            )
        token = str(payload.get("access_token", "")).strip()
        if not token:
            raise RuntimeError("TikTok token refresh returned no access_token")
        scopes = {scope.strip() for scope in str(payload.get("scope", "")).split(",")}
        if required_scope not in scopes:
            raise RuntimeError(
                f"The connected TikTok account did not authorize {required_scope}. "
                "Authorize the account again with the required scope and replace the GitHub tokens."
            )
        rotated = str(payload.get("refresh_token", "")).strip()
        if rotated and rotated != refresh_token:
            print(
                "::warning::TikTok rotated the refresh token. Update the "
                "TIKTOK_REFRESH_TOKEN repository secret before the next run."
            )
        print("Refreshed the TikTok access token")
        return token

    token = os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Missing TikTok credentials. Configure TIKTOK_CLIENT_KEY, "
            "TIKTOK_CLIENT_SECRET and TIKTOK_REFRESH_TOKEN."
        )
    print("Using the fallback TIKTOK_ACCESS_TOKEN")
    return token


def auth_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def creator_info(token, privacy):
    response = requests.post(CREATOR_INFO_URL, headers=auth_headers(token), timeout=30)
    data = api_data(response, "creator-info query")
    allowed = data.get("privacy_level_options", [])
    if privacy not in allowed:
        raise RuntimeError(
            f"Privacy level {privacy} is unavailable for @{data.get('creator_username', 'unknown')}; "
            f"allowed values: {', '.join(allowed) or 'none'}"
        )
    print(
        f"Connected TikTok creator: @{data.get('creator_username', 'unknown')} "
        f"({data.get('creator_nickname', 'unknown')}); privacy={privacy}"
    )
    return data


def wait_for_publish(token, publish_id, success_status):
    timeout = int(os.environ.get("TIKTOK_STATUS_TIMEOUT_SECONDS", "300"))
    deadline = time.monotonic() + timeout
    last_status = "unknown"
    while time.monotonic() < deadline:
        response = requests.post(
            STATUS_URL,
            headers=auth_headers(token),
            json={"publish_id": publish_id},
            timeout=30,
        )
        data = api_data(response, "status query")
        last_status = data.get("status", "unknown")
        print(f"TikTok publish status for {publish_id}: {last_status}")
        if last_status == success_status:
            return
        if last_status == "FAILED":
            raise RuntimeError(
                f"TikTok rejected {publish_id}: {data.get('fail_reason', 'unknown reason')}"
            )
        time.sleep(5)
    raise TimeoutError(
        f"TikTok did not finish processing {publish_id} within {timeout}s; "
        f"last status={last_status}. The story was not marked processed."
    )


def mark_processed(state_path, story_id):
    processed = set()
    if state_path.exists():
        processed = set(json.loads(state_path.read_text(encoding="utf-8")))
    processed.add(story_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(sorted(processed), indent=2) + "\n", encoding="utf-8"
    )


def add_draft_caption_to_summary(metadata):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write(f"\n### TikTok draft caption: {metadata['title']}\n\n")
        summary.write("```text\n")
        summary.write(metadata["description"].strip())
        summary.write("\n```\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", type=Path, default=Path("output"))
    parser.add_argument("--state", type=Path)
    parser.add_argument("--generation-state", type=Path)
    parser.add_argument("--pending-generation", type=Path)
    parser.add_argument(
        "--limit", type=int,
        default=int(os.environ.get("TIKTOK_UPLOAD_LIMIT", "0")),
        help="Maximum videos to post in this run; 0 posts every rendered video",
    )
    args = parser.parse_args()
    post_mode = os.environ.get("TIKTOK_POST_MODE", "draft").strip().lower()
    if post_mode not in {"draft", "direct"}:
        raise RuntimeError("TIKTOK_POST_MODE must be either draft or direct")
    required_scope = "video.upload" if post_mode == "draft" else "video.publish"
    token = access_token(required_scope)
    privacy = os.environ.get("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY")
    creator = creator_info(token, privacy) if post_mode == "direct" else {}
    headers = auth_headers(token)
    if post_mode == "draft":
        print("TikTok mode: upload draft to creator inbox for manual public publishing")

    uploaded_count = 0
    for metadata_path in sorted(args.output.glob("*.json")):
        if args.limit and uploaded_count >= args.limit:
            print(f"TikTok upload limit reached ({args.limit}); leaving remaining videos unprocessed")
            break
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        video_path = args.output / metadata["video"]
        size = video_path.stat().st_size
        duration = float(metadata.get("duration_seconds", 0))
        maximum = int(creator.get("max_video_post_duration_sec", 0))
        if maximum and duration > maximum:
            raise RuntimeError(
                f"{video_path.name} is {duration:.1f}s but this creator may post at most {maximum}s"
            )
        source_info = {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": size,
            "total_chunk_count": 1,
        }
        if post_mode == "direct":
            payload = {
                "post_info": {
                    "title": metadata["description"][:2200],
                    "privacy_level": privacy,
                    "disable_duet": bool(creator.get("duet_disabled", False)),
                    "disable_comment": bool(creator.get("comment_disabled", False)),
                    "disable_stitch": bool(creator.get("stitch_disabled", False)),
                    "video_cover_timestamp_ms": 1000,
                    "brand_content_toggle": False,
                    "brand_organic_toggle": False,
                    "is_aigc": True,
                },
                "source_info": source_info,
            }
            init_url = DIRECT_POST_INIT_URL
            success_status = "PUBLISH_COMPLETE"
        else:
            payload = {"source_info": source_info}
            init_url = DRAFT_UPLOAD_INIT_URL
            success_status = "SEND_TO_USER_INBOX"
        response = requests.post(init_url, headers=headers, json=payload, timeout=30)
        data = api_data(response, "publish initialization")
        publish_id = data.get("publish_id")
        upload_url = data.get("upload_url")
        if not publish_id or not upload_url:
            raise RuntimeError("TikTok publish initialization returned incomplete data")
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
        print(f"Uploaded {video_path.name}; publish_id={publish_id}")
        wait_for_publish(token, publish_id, success_status)
        if post_mode == "draft":
            print(f"Delivered {video_path.name} to the TikTok inbox successfully")
            add_draft_caption_to_summary(metadata)
        else:
            print(f"Published {video_path.name} successfully")
        if args.state:
            mark_processed(args.state, metadata["id"])
        uploaded_count += 1

    if args.generation_state and args.pending_generation and args.pending_generation.exists():
        pending = json.loads(args.pending_generation.read_text(encoding="utf-8"))
        processed = (
            set(json.loads(args.state.read_text(encoding="utf-8")))
            if args.state and args.state.exists()
            else set()
        )
        required = set(pending.get("generated_ids", []))
        if required and required.issubset(processed):
            args.generation_state.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=args.generation_state.parent, delete=False
            ) as handle:
                json.dump(pending["next_state"], handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                temporary = Path(handle.name)
            temporary.replace(args.generation_state)
            args.pending_generation.unlink()
            print(f"Advanced series state to Chapter {pending['next_state']['next_chapter']}")


if __name__ == "__main__":
    main()
