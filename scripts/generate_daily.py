#!/usr/bin/env python3
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
HASHTAG = re.compile(r"^#[A-Za-z0-9]+$")


def words(text):
    return len(re.findall(r"\b[\w’'-]+\b", text))


def load_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_entry(entry, label, require_continuity=False):
    required = ["narration", "caption", "hashtags"]
    if label != "chapter":
        required += ["title", "premise_key"]
    if require_continuity:
        required.append("continuity_note")
    missing = [key for key in required if not entry.get(key)]
    if missing:
        raise ValueError(f"{label}: missing {', '.join(missing)}")
    count = words(entry["narration"])
    if not 130 <= count <= 155:
        raise ValueError(f"{label}: narration has {count} words; expected 130-155")
    tags = entry["hashtags"]
    if len(tags) != 10 or len(set(tags)) != 10 or not all(HASHTAG.fullmatch(tag) for tag in tags):
        raise ValueError(f"{label}: hashtags must be exactly 10 unique #Tags without spaces")


def prompt_for(chapter_number, bible, state):
    later_notes = state.get("chapter_notes", [])
    used = bible["previous_standalone_titles"] + state.get("standalone_titles", [])
    used_premises = state.get("standalone_premises", [])
    continuity = bible["established_continuity"] + [
        f"Chapter {item['chapter']}: {item['note']}" for item in later_notes
    ]
    return f"""Create today's original short-form horror package as strict JSON only.

Return this exact shape:
{{
  "chapter": {{"narration":"...","caption":"...","hashtags":["#..."],"continuity_note":"..."}},
  "standalone": [
    {{"title":"...","narration":"...","caption":"...","hashtags":["#..."],"premise_key":"brief premise and twist"}}
  ]
}}

Requirements:
- Write exactly one ongoing Spare Key Chapter {chapter_number} and exactly four unrelated, complete standalone stories.
- Every narration must be 130-155 spoken words, accessible first-person, narration-ready, and under one minute at brisk delivery.
- Every story needs an immediate first-sentence hook, coherent escalating threat, and surprising but logically earned ending.
- The chapter continues directly from Chapter {chapter_number - 1}, uses domestic psychological suspense and unreliable perception, and ends on a concise cliffhanger. Do not resolve the central mysteries early. Do not put the title inside narration.
- Each standalone premise and twist must differ meaningfully from every other story and all prior titles/premises listed below. Avoid face swaps, forgotten identities, future recordings, hidden rooms, predictive media, missing spouses, and planted evidence unless used in a genuinely new way.
- Each entry has exactly 10 unique relevant hashtags including broad horror/thriller discovery, story-specific tags, and short-form discovery. No unrelated trending tags.
- Captions are one short sentence with no hashtags. The program adds the title and hashtags.
- Entirely original. Do not reproduce, paraphrase, or adapt Reddit posts or copyrighted stories. Do not imitate any living author's style.
- premise_key is a concise description used only to prevent future repetition.
- continuity_note is one sentence preserving new clues for the next chapter.

Established Spare Key continuity:
{json.dumps(continuity, ensure_ascii=False, indent=2)}

Prior standalone titles to avoid:
{json.dumps(used, ensure_ascii=False)}

Prior standalone premise-and-twist summaries to avoid:
{json.dumps(used_premises, ensure_ascii=False)}
"""


def parse_response(text):
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    return json.loads(value)


def build_stories(package, chapter_number, date_slug):
    chapter = package.get("chapter", {})
    standalone = package.get("standalone", [])
    validate_entry(chapter, "chapter", require_continuity=True)
    if len(standalone) != 4:
        raise ValueError(f"Expected 4 standalone stories, received {len(standalone)}")
    for index, entry in enumerate(standalone, 1):
        validate_entry(entry, f"standalone {index}")
    titles = [entry["title"].strip().casefold() for entry in standalone]
    premises = [entry["premise_key"].strip().casefold() for entry in standalone]
    if len(set(titles)) != 4 or len(set(premises)) != 4:
        raise ValueError("Standalone titles and premise keys must be unique")

    common = {
        "voice": "en-GB-SoniaNeural",
        "speech_rate": "+14%",
        "speech_volume": "-14%",
        "speech_pitch": "-8Hz",
        "background": "",
        "music": ""
    }
    chapter_title = f"Spare Key — Chapter {chapter_number}"
    chapter_story = {
        "id": f"spare-key-chapter-{chapter_number:03d}",
        "title": chapter_title,
        "narration": chapter["narration"].strip(),
        "description": f"{chapter_title}. {chapter['caption'].strip()} {' '.join(chapter['hashtags'])}",
        **common,
    }
    stories = [chapter_story]
    for index, entry in enumerate(standalone, 1):
        title = entry["title"].strip()
        stories.append({
            "id": f"daily-{date_slug}-{index:02d}",
            "title": title,
            "narration": entry["narration"].strip(),
            "description": f"{title}. {entry['caption'].strip()} {' '.join(entry['hashtags'])}",
            **common,
        })
    return stories


def write_outputs(output, stories):
    output.mkdir(parents=True, exist_ok=True)
    for old in output.glob("*.json"):
        old.unlink()
    for story in stories:
        atomic_json(output / f"{story['id']}.json", story)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "content/generated")
    parser.add_argument("--state", type=Path, default=ROOT / ".automation-state/generation.json")
    parser.add_argument("--pending", type=Path, default=ROOT / ".automation-state/pending-generation.json")
    args = parser.parse_args()

    pending = load_json(args.pending)
    if pending:
        write_outputs(args.output, pending["stories"])
        print(f"Restored pending batch with {len(pending['stories'])} stories; no API call made")
        return

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY GitHub Actions secret")
    bible = load_json(ROOT / "content/series/spare-key-bible.json")
    state = load_json(args.state, {}) or {}
    chapter_number = int(state.get("next_chapter", bible["next_chapter"]))
    model = os.environ.get("OPENAI_STORY_MODEL", "gpt-5-mini").strip()
    date_slug = datetime.now(timezone.utc).date().isoformat()
    client = OpenAI(api_key=api_key)
    original_prompt = prompt_for(chapter_number, bible, state)
    last_error = None
    raw_output = ""
    for attempt in range(2):
        request = original_prompt
        if attempt:
            request += f"""

Your previous JSON failed validation: {last_error}
Correct only those problems while preserving quality. Return the complete corrected JSON only.
Previous output:
{raw_output}
"""
        response = client.responses.create(model=model, input=request, max_output_tokens=5000)
        raw_output = response.output_text
        try:
            package = parse_response(raw_output)
            stories = build_stories(package, chapter_number, date_slug)
            break
        except (ValueError, json.JSONDecodeError) as error:
            last_error = str(error)
            if attempt:
                raise
            print(f"First generation needed one correction: {last_error}")
    next_state = {
        "next_chapter": chapter_number + 1,
        "chapter_notes": (state.get("chapter_notes", []) + [{
            "chapter": chapter_number,
            "note": package["chapter"]["continuity_note"].strip(),
        }])[-30:],
        "standalone_titles": (state.get("standalone_titles", []) + [
            entry["title"].strip() for entry in package["standalone"]
        ])[-100:],
        "standalone_premises": (state.get("standalone_premises", []) + [
            entry["premise_key"].strip() for entry in package["standalone"]
        ])[-100:],
    }
    pending_value = {
        "generated_ids": [story["id"] for story in stories],
        "stories": stories,
        "next_state": next_state,
    }
    atomic_json(args.pending, pending_value)
    write_outputs(args.output, stories)
    print(f"Generated Chapter {chapter_number} and four standalone stories with {model}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}")
        raise
