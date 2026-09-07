# Faceless Horror Video Automation

Creates 9:16 narrated horror videos in GitHub Actions, without using your
computer's memory. A story JSON file becomes a captioned MP4 with a looping
background, optional music, and a TikTok-ready caption.

## What is automated

1. Read the next unprocessed JSON file in `content/queue/`.
2. Create narration with Microsoft Edge TTS.
3. Create timed subtitles from the narration.
4. Loop and crop a background to 1080 x 1920.
5. Mix optional background music at low volume.
6. Export an H.264/AAC MP4.
7. Direct-post one chapter to TikTok after rendering succeeds.
8. Mark it processed only after TikTok accepts the upload.
9. Save the result as a downloadable GitHub Actions artifact.

## First test

1. Create a **private GitHub repository**.
2. Upload this project's files.
3. Add at least one MP4 to `assets/backgrounds/` (vertical is best, but any
   orientation works). Use only footage you created or are licensed to reuse.
4. Open **Actions > Build horror reels > Run workflow**.
5. Download `rendered-horror-reels` from the completed run.

The included sample story is ready to render.

The included queue contains **Spare Key — Chapters 3 through 7**. Chapter 3 is
processed first, then exactly one later chapter is posted on each subsequent
successful run.

## Story format

Add one file per video to `content/queue/`:

```json
{
  "id": "spare-key-chapter-006",
  "title": "Spare Key — Chapter 6",
  "narration": "Narration only, ideally 130 to 155 words.",
  "description": "Spare Key — Chapter 6. Short caption followed by hashtags.",
  "voice": "en-GB-SoniaNeural",
  "speech_rate": "+12%",
  "speech_volume": "-12%",
  "speech_pitch": "-6Hz",
  "background": "",
  "music": ""
}
```

Leaving `background` or `music` empty selects a file automatically. Music is
optional. The renderer refuses narration over 175 words or videos over 60
seconds. `speech_rate` can be adjusted per story; `+12%` is the default chosen
to keep 130-155 word narration below one minute. The default `speech_volume`
and `speech_pitch` form a softer suspense preset. Use `0%` and `+0Hz` for the
original neutral delivery.

## Repository secrets

TikTok Direct Post uses:

- `TIKTOK_ACCESS_TOKEN`
- repository variable `ENABLE_TIKTOK=true`

The TikTok caption always begins `Spare Key — Chapter N`, followed by the
chapter caption and its ten hashtags. The uploader also declares the rendered
video as AI-generated content through TikTok's API.

TikTok unaudited applications can only publish privately. Keep
`TIKTOK_PRIVACY_LEVEL=SELF_ONLY` until TikTok approves the application.

Optional repository variables:

- `ENABLE_TIKTOK=true`
- `TIKTOK_PRIVACY_LEVEL=SELF_ONLY`

Start with TikTok set to private. Change visibility only after checking the
complete generated video and satisfying TikTok's API rules.

## Scheduled processing

The workflow runs once daily and can also be started manually. Each run handles
only the next chapter, starting at Chapter 3. GitHub cron uses UTC, so adjust
`.github/workflows/build-reels.yml` if you want a different time.

## Next integration

The current queue is deliberately file-based so rendering can be verified
before account credentials are introduced. The next step is a Google Drive
inbox: the story automation writes JSON there and this project downloads all
unprocessed files. That requires a Google service-account credential and a
Drive folder ID.
