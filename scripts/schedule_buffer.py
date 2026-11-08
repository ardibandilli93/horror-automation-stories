#!/usr/bin/env python3
"""Schedule rendered videos on a connected TikTok channel through Buffer."""

import argparse
import json
import os
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests


BUFFER_URL = "https://api.buffer.com"
STANDALONE_TIMES = ("11:00", "13:00", "15:00", "20:00", "22:00")
CHAPTER_TIME = "18:00"


def graphql(token, query, variables=None):
    response = requests.post(
        BUFFER_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"query": query, "variables": variables or {}},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        messages = "; ".join(str(error.get("message", error)) for error in payload["errors"])
        raise RuntimeError(f"Buffer API error: {messages}")
    return payload.get("data", {})


def find_tiktok_channel(token, requested_name):
    account = graphql(
        token,
        "query GetOrganizations { account { organizations { id } } }",
    )
    organizations = account.get("account", {}).get("organizations", [])
    matches = []
    for organization in organizations:
        organization_id = json.dumps(str(organization["id"]))
        query = f"""
        query GetChannels {{
          channels(input: {{organizationId: {organization_id}}}) {{
            id name displayName service
          }}
        }}
        """
        data = graphql(token, query)
        for channel in data.get("channels", []):
            if str(channel.get("service", "")).lower() == "tiktok":
                matches.append(channel)
    if requested_name:
        wanted = requested_name.lstrip("@").lower()
        named = [
            channel for channel in matches
            if wanted in {
                str(channel.get("name", "")).lstrip("@").lower(),
                str(channel.get("displayName", "")).lstrip("@").lower(),
            }
        ]
        if len(named) == 1:
            return named[0]
    if len(matches) == 1:
        return matches[0]
    available = ", ".join(
        str(channel.get("displayName") or channel.get("name") or channel.get("id"))
        for channel in matches
    ) or "none"
    raise RuntimeError(
        f"Could not uniquely select the TikTok channel {requested_name!r}; available: {available}"
    )


def parse_clock(value):
    hour, minute = (int(part) for part in value.split(":", 1))
    return time(hour=hour, minute=minute)


def schedule_times(stories, zone_name):
    zone = ZoneInfo(zone_name)
    now = datetime.now(zone)
    chapter = [story for story in stories if story["is_chapter"]]
    standalones = [story for story in stories if not story["is_chapter"]]
    if len(chapter) > 1:
        raise RuntimeError("Expected at most one Spare Key chapter in a daily batch")
    if len(standalones) > len(STANDALONE_TIMES):
        raise RuntimeError(
            f"Daily batch contains {len(standalones)} standalone stories but only "
            f"{len(STANDALONE_TIMES)} publishing slots are configured"
        )

    # Keep every successful build together on one publishing day. If the build
    # finishes within 20 minutes of the first slot, move the whole batch to
    # tomorrow rather than splitting it across two dates.
    publish_date = now.date()
    first_slot = datetime.combine(
        publish_date, parse_clock(STANDALONE_TIMES[0]), tzinfo=zone
    )
    if now + timedelta(minutes=20) >= first_slot:
        publish_date += timedelta(days=1)

    assigned = {}
    if chapter:
        assigned[chapter[0]["id"]] = datetime.combine(
            publish_date, parse_clock(CHAPTER_TIME), tzinfo=zone
        )
    for index, story in enumerate(standalones):
        assigned[story["id"]] = datetime.combine(
            publish_date, parse_clock(STANDALONE_TIMES[index]), tzinfo=zone
        )
    print(f"Scheduling the complete batch for {publish_date} in {zone_name}")
    return assigned


def create_post(token, channel_id, story, due_at, video_url):
    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        __typename
        ... on PostActionSuccess { post { id dueAt status } }
        ... on MutationError { message }
      }
    }
    """
    data = graphql(
        token,
        mutation,
        {
            "input": {
                "text": story["description"].strip()[:2200],
                "channelId": channel_id,
                "schedulingType": "automatic",
                "mode": "customScheduled",
                "dueAt": due_at.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
                "aiAssisted": True,
                "metadata": {"tiktok": {"isAiGenerated": True}},
                "assets": [
                    {
                        "video": {
                            "url": video_url,
                            "metadata": {"thumbnailOffset": 2000},
                        }
                    }
                ],
            }
        },
    )
    result = data.get("createPost", {})
    if result.get("__typename") != "PostActionSuccess":
        raise RuntimeError(f"Buffer rejected {story['title']}: {result.get('message', result)}")
    return result["post"]


def read_json(path, default):
    if not path or not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def advance_generation(processed_path, generation_state, pending_generation):
    if not generation_state or not pending_generation or not pending_generation.exists():
        return
    pending = read_json(pending_generation, {})
    processed = set(read_json(processed_path, []))
    required = set(pending.get("generated_ids", []))
    if required and required.issubset(processed):
        write_json(generation_state, pending["next_state"])
        pending_generation.unlink()
        print(f"Advanced series state to Chapter {pending['next_state']['next_chapter']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, nargs="?", default=Path("output"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--generation-state", type=Path)
    parser.add_argument("--pending-generation", type=Path)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--release-tag", required=True)
    args = parser.parse_args()

    token = os.environ.get("BUFFER_API_KEY", "").strip()
    if not token:
        raise RuntimeError("Missing BUFFER_API_KEY")
    if not args.repository:
        raise RuntimeError("Missing GitHub repository name")

    requested_channel = os.environ.get("BUFFER_TIKTOK_CHANNEL", "hereforanxiety").strip()
    timezone = os.environ.get("BUFFER_TIMEZONE", "Europe/London").strip()
    channel = find_tiktok_channel(token, requested_channel)
    print(f"Buffer TikTok channel: {channel.get('displayName') or channel.get('name')} ({channel['id']})")

    processed = set(read_json(args.state, []))
    buffer_state_path = args.state.with_name("buffer-posts.json")
    buffer_state = read_json(buffer_state_path, {})
    stories = []
    for metadata_path in sorted(args.output.glob("*.json")):
        metadata = read_json(metadata_path, {})
        story_id = metadata["id"]
        stories.append(
            {
                **metadata,
                "metadata_path": metadata_path,
                "is_chapter": story_id.startswith("spare-key-")
                or "spare key" in metadata.get("title", "").lower(),
            }
        )
    if not stories:
        raise RuntimeError(f"No rendered story metadata found in {args.output}")

    due_times = schedule_times(stories, timezone)
    for story in stories:
        story_id = story["id"]
        if story_id in buffer_state:
            print(f"Skipping {story_id}; already scheduled as Buffer post {buffer_state[story_id]['post_id']}")
            processed.add(story_id)
            continue
        video_name = story["video"]
        video_url = (
            f"https://github.com/{args.repository}/releases/download/"
            f"{quote(args.release_tag, safe='')}/{quote(video_name, safe='')}"
        )
        post = create_post(token, channel["id"], story, due_times[story_id], video_url)
        buffer_state[story_id] = {
            "post_id": post["id"],
            "due_at": post.get("dueAt") or due_times[story_id].isoformat(),
            "release_tag": args.release_tag,
            "video_url": video_url,
        }
        processed.add(story_id)
        write_json(buffer_state_path, buffer_state)
        write_json(args.state, sorted(processed))
        print(f"Scheduled {story['title']} for {due_times[story_id].isoformat()}")

    advance_generation(args.state, args.generation_state, args.pending_generation)


if __name__ == "__main__":
    main()
