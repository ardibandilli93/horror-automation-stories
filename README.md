# Faceless Horror Video Automation

Creates 9:16 narrated horror videos in GitHub Actions, without using your
computer's memory. A story JSON file becomes a captioned MP4 with a looping
background, optional music, and metadata ready for TikTok and YouTube.

## What is automated

1. Read every JSON file in `content/queue/`.
2. Create narration with Microsoft Edge TTS.
3. Create timed subtitles from the narration.
4. Loop and crop a background to 1080 x 1920.
5. Mix optional background music at low volume.
6. Export an H.264/AAC MP4.
7. Upload to YouTube when its secrets are configured.
8. Direct-post to TikTok when TikTok credentials and app audit are configured.
9. Save every result as a downloadable GitHub Actions artifact.

## First test

1. Create a **private GitHub repository**.
2. Upload this project's files.
3. Add at least one MP4 to `assets/backgrounds/` (vertical is best, but any
   orientation works). Use only footage you created or are licensed to reuse.
4. Open **Actions > Build horror reels > Run workflow**.
5. Download `rendered-horror-reels` from the completed run.

The included sample story is ready to render.

## Story format

Add one file per video to `content/queue/`:

```json
{
  "id": "chapter-006",
  "title": "The First Face",
  "narration": "Narration only, ideally 130 to 155 words.",
  "description": "Short caption followed by hashtags.",
  "voice": "en-GB-SoniaNeural",
  "background": "",
  "music": ""
}
```

Leaving `background` or `music` empty selects a file automatically. Music is
optional. The renderer refuses narration over 175 words or videos over 60
seconds.

## Repository secrets

YouTube upload uses:

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

TikTok Direct Post uses:

- `TIKTOK_ACCESS_TOKEN`
- repository variable `ENABLE_TIKTOK=true`

TikTok unaudited applications can only publish privately. Keep
`TIKTOK_PRIVACY_LEVEL=SELF_ONLY` until TikTok approves the application.

Optional repository variables:

- `ENABLE_YOUTUBE=true`
- `ENABLE_TIKTOK=true`
- `TIKTOK_PRIVACY_LEVEL=SELF_ONLY`
- `YOUTUBE_PRIVACY_STATUS=private`
- `DEFAULT_VOICE=en-GB-SoniaNeural`

Start with both platforms set to private. Change visibility only after checking
the complete generated video and satisfying each platform's API rules.

## Scheduled processing

The workflow runs once daily and can also be started manually. GitHub cron uses
UTC, so adjust `.github/workflows/build-reels.yml` if you want a different time.

## Next integration

The current queue is deliberately file-based so rendering can be verified
before account credentials are introduced. The next step is a Google Drive
inbox: the story automation writes JSON there and this project downloads all
unprocessed files. That requires a Google service-account credential and a
Drive folder ID.
