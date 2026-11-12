# Video Agent Platform — Phase 1

Original request: Build a private, specification-driven video agent in three phases; Phase 1 generates a Hindi vertical Reel from a structured brief and the user's own voice recording, with review before approval.

## Requirement checklist
- [x] An operator can enter topic, audience, duration, tone, CTA, style guidance, must-include points, and exclusions
- [x] The operator can receive a Hindi Devanagari script from the brief
- [x] The operator can upload or record their own voice
- [x] The operator can automatically receive a downloadable 1080×1920 MP4 with captions and constrained CSS/shapes visuals
- [ ] The operator can upload and select music with rights confirmation — not built in Phase 1
- [x] The operator can see live job lifecycle and append-only event history
- [x] The operator can inspect the script, render preview, timeline status, generated caption, and approve a render
- [x] The operator can edit the script before recording
- [x] The system can validate static composition and media references
- [x] The operator can download the project as a ZIP file from the UI

## Status
- Phase 1 is the active build. Instagram OAuth, scheduling, publishing, and VPS hardening are Phase 3 scope and are not built here.
- NO TTS: the voice track is always the operator's uploaded or recorded audio.
- AI-generated photographic/video footage is not in this contract; visuals are constrained to offline text, shapes, CSS, and FFmpeg composition.

## Key decisions
- FastAPI + MongoDB + Vite/React, with string UUIDs and append-only `job_events`.
- Job state transitions are guarded by the backend and work is performed in a background task.
- LLM generation is behind one replaceable client; the configured managed LLM is used when available, with a deterministic Hindi contract fallback for local development.
- Render output is validated with ffprobe before the job becomes ready for approval.

## Backlog
- P0: Hindi transcription and script-match scoring using a real speech-to-text integration
- P0: private music upload/library with rights confirmation and voice/music mixing
- P1: private object storage and Supabase allowlisted auth
- P1: HyperFrames-compatible Docker render image and richer GSAP compositions
- P2: Instagram OAuth, safe scheduling, idempotent publishing