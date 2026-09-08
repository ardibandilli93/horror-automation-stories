# Centred captions and narration

New renders use explicit 1080x1920 subtitle coordinates. Captions are anchored
at (540, 960), at most two short lines, with side margins. Output JSON records
`renderer_version: centered-v2`, the selected voice, and any speed adjustment.
Old downloaded videos do not change: start a **new** workflow run on main;
re-running an old run uses its old code. Do not clear processed/published state.

The default free narration is Ryan (`en-GB-RyanNeural`), at -10% rate,
-10Hz pitch and -18% volume. Old voice settings inside story JSON no longer
override the channel voice. Edge does not support custom whisper SSML; a low
spoken voice is not a true whisper. There is no fallback to a female voice.

For a whisper-capable mode, opt in by setting repository **variable**
`NARRATION_BACKEND=openai`. It uses the existing **secret** `OPENAI_API_KEY`,
`gpt-4o-mini-tts` with whisper instructions, and the `onyx` voice. Optionally
set `OPENAI_TTS_VOICE`. This sends narration text and generated audio to OpenAI
and incurs **additional speech generation and transcription charges** against
your API balance. It is disabled by default; no new spending is enabled by
this patch. Listen to a sample before publishing. Keep the AI-voice disclosure.
Documentation: https://developers.openai.com/api/docs/guides/text-to-speech

Both modes time captions from the audio. To fit under a minute, the renderer
can accelerate up to 20%, scaling captions together. Longer audio stops with a
clear request to shorten the script, rather than cutting off the ending. Slow
delivery and 155 words cannot always both fit within 60 seconds.

## Downloads

Repository → Actions → Build horror reels → latest successful **new** run →
Summary → Download your videos. The `rendered-horror-reels` artifact contains
MP4 files and metadata JSON and is retained for 14 days for new runs.
`ENABLE_TIKTOK=false` disables upload, not rendering or artifact saving.
GitHub's hosted runner cannot write directly into your computer's Downloads
folder. Download the ZIP and unzip it locally. Local downloading requires no
TikTok credentials. Nothing in this fix changes chapter selection or posted state.
