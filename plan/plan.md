# Video Agent Platform — Three-Phase Build Proposal

## What it is
This is a private tool that turns a structured brief and your own Hindi voice recording into a 15–30 second vertical Reel.
It automatically writes the Hindi script, creates an offline HTML/CSS/GSAP composition, renders an MP4, waits for your approval, and can later publish it to Instagram.

## Who it's for
You only, protected by invite-only or allowlisted Supabase Auth. The first version is an operator dashboard rather than a public creator product.

## Core features and experience
- **Phase 1 — Generate:** enter topic, audience, duration, tone, CTA, optional style guidance, must-include points, and exclusions; receive a Hindi Devanagari script, upload or record your voice, and automatically receive a downloadable 1080×1920 MP4 with captions, CSS/shapes/GSAP visuals, and your selected music.
- **Phase 2 — Review and refine:** inspect script, timeline status, render preview, event history, and generated caption; edit the script before recording, reject a render with visual feedback, and allow a bounded two-fix loop without changing spoken words.
- **Phase 3 — Publish and operate:** connect one Instagram Professional account, approve a Reel, publish now or schedule it, retry safely after worker failures, and prevent duplicate posts with idempotent state transitions.
- The architecture is specification-driven: versioned prompt contracts and rules, typed job states, compare-and-set transitions, append-only job events, isolated agent/worker/render responsibilities, reproducible HTML/audio hashes, and explicit acceptance checks.
- Video generation is realistic because the visual layer is deliberately constrained to text, shapes, CSS, and GSAP rendered offline by HyperFrames. It is not a general text-to-video system: it will not generate photographic or AI video footage in this contract.
- Automation is real but not fully unattended: you must provide your own voice recording and approve the render. There is **NO TTS in v1**; “your own voice” means your uploaded recording. Instagram publishing additionally depends on Meta account permissions and app approval.

## Phase 1: what gets built now
- A private dashboard for the structured brief and one-owner job history.
- A real script-generation pipeline using Groq through one replaceable LLM client, with validated Hindi output, word-budget checks, model fallback, retry/backoff, and recorded decisions.
- Voice upload/recording intake with duration validation, processing, Hindi transcription, script-match scoring, caption timing, and a private music upload/library with rights confirmation.
- An isolated HyperFrames render foundation that produces a real MP4: 9:16, 1080×1920, 30 fps, H.264 video, AAC audio, mixed voice/music, Devanagari fonts, captions, thumbnail, and ffprobe validation.
- Offline/static composition validation that blocks remote assets, network calls, unsafe HTML, unapproved fonts/palettes, invented visible text, and invalid media references; one generation plus at most two corrective attempts.
- A live job lifecycle and polling view showing queued, scripting, voice required, composing, validating, rendering, failed, and ready-for-approval states, with resumable event history.
- Downloadable rendered video and preview approval checkpoint. Instagram OAuth, publishing, scheduling, and VPS hardening remain specified for later phases, not claimed as Phase 1 functionality.
- **Realism decision:** yes, the three phases are technically achievable; the highest-risk Phase 1 proof is Hindi transcription quality and the availability/version behavior of HyperFrames in a reproducible Docker render image, which will be settled by a real golden render before expanding the platform.