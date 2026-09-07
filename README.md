# Faceless Horror Video Automation

Creates 9:16 narrated horror videos in GitHub Actions, without using your
computer's memory. A story JSON file becomes a captioned MP4 with a looping
background, optional music, and a TikTok-ready caption.

## What is automated

1. Ask OpenAI for the next Spare Key chapter and four unrelated original stories.
2. Create narration with Microsoft Edge TTS.
3. Create timed subtitles from the narration.
4. Loop and crop a background to 1080 x 1920.
5. Mix optional background music at low volume.
6. Export an H.264/AAC MP4.
7. Direct-post all five videos to TikTok after rendering succeeds.
8. Advance the series chapter only after TikTok accepts the complete batch.
9. Save the result as a downloadable GitHub Actions artifact.

## First test

1. Create a **private GitHub repository**.
2. Upload this project's files.
3. Add at least one MP4 to `assets/backgrounds/` (vertical is best, but any
   orientation works). Use only footage you created or are licensed to reuse.
4. Open **Actions > Build horror reels > Run workflow**.
5. Download `rendered-horror-reels` from the completed run.

The included sample story is ready to render.

Automated generation starts at **Spare Key — Chapter 8**, because Chapters 1
and 2 are already on TikTok. The old Chapters 3 through 7 remain in
`content/queue/` as a manual archive and are ignored while AI generation is on.
The package also contains 28 completed standalone stories in `content/backlog/`.
Four unposted backlog stories are selected per run. After the backlog is empty,
the four newly generated standalone stories are used automatically.

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

Daily story generation uses:

- secret `OPENAI_API_KEY`
- optional repository variable `OPENAI_STORY_MODEL=gpt-5-mini`
- optional repository variable `ENABLE_AI_GENERATION=true`

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

The workflow runs once daily and can also be started manually. Each successful
run creates and renders one chapter plus four standalone stories. A failed or
partially uploaded batch is saved and retried without another OpenAI call or a
chapter-number jump. GitHub cron uses UTC.

## Switching back to manual JSON later

Set the repository variable `ENABLE_AI_GENERATION=false`. The workflow will
stop calling OpenAI and return to processing one file from `content/queue/` per
run. Set it back to `true` to resume automatic generation at the safely stored
next chapter number.
