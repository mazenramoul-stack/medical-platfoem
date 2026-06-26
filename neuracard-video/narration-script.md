# NEURACARD — Voiceover Script (for ElevenLabs)

Timed to `neuracard-presentation-v2.mp4` (3:21). English. ~420 words, calm/measured pace.
Each line is sized to fit its scene with breathing room, so it stays in sync.

> Tip: pronounce the brand **"NEURA-CARD"** (NOOR-ah-card). If ElevenLabs mispronounces it,
> type it as **"Neura-Card"** or **"Neura Card"** in that line only.

---

**[0:00 · Title]**
NeuraCard — a multimodal medical-AI platform for clinical decision support.

**[0:08 · Problem 1]**
Think about a single patient. They might need a brain MRI, an ECG, an echocardiogram, and an EEG — many different tests.

**[0:19 · Problem 2]**
Today, each one is read on its own — a different specialist, a different system, a different day. No one sees the whole patient at once.

**[0:30 · Problem 3]**
AI can help read them. But the models are scattered — each built for a single task, and most never leave the research lab.

**[0:42 · Problem 4]**
And they behave like black boxes, giving an answer with no reason. A doctor can't safely trust that with a patient's life.

**[0:53 · Problem 5]**
So the full picture never comes together — at the very moment the decision must be made.

**[1:02 · The solution]**
That's the gap NeuraCard closes. One platform, for every modality.

**[1:11 · How it works]**
It's a single, secure workspace. Open a patient, upload any test, and get an instant, AI-powered reading — all in one place.

**[1:24 · Brain MRI]**
Brain MRI is analysed for tumours — and the platform shows the evidence behind the result.

**[1:36 · ECG]**
A twelve-lead ECG is screened for arrhythmias, with heart rate and variability — and every finding is flagged.

**[1:48 · Echocardiogram]**
An echocardiogram measures the ejection fraction and outlines the heart's chambers, straight from the ultrasound.

**[1:59 · EEG]**
And an EEG is screened, second by second, for harmful brain activity.

**[2:10 · Explainability]**
Every answer is explained. Grad-CAM and SHAP show exactly where each model looked — so the clinician checks the reasoning, not just the result.

**[2:21 · Integration]**
And NeuraCard brings them together — combining brain and heart into one, readable interpretation.

**[2:31 · The payoff]**
Every test flows into a single, combined report — the complete picture, ready for the doctor to act on. This is the integration that was missing.

**[2:49 · What's next]**
From here, the vision grows: a fusion model that reveals links no single test can see; validation with a hospital partner; continuous monitoring at the bedside and on wearables; and secure integration with hospital systems — on the path to a certified clinical tool.

**[3:11 · Close]**
NeuraCard — every signal, together, for more confident decisions. Thank you.

---

## ElevenLabs settings (suggested)

- **Model:** *Eleven Multilingual v2* (most natural for narration).
- **Voice:** a calm, clear, professional voice — e.g. *Brian / Daniel / Adam* (male) or *Rachel / Alice / Matilda* (female). For a thesis defence, pick a measured, confident tone.
- **Settings:** Stability ~50% · Similarity/Clarity ~75% · Style 0–15% · Speaker Boost on. Slightly slower speed reads clearer.
- **Pauses:** the em-dashes (—) and full stops already cue natural pauses. For a longer beat-gap, add an ellipsis "…".

## How to get the real ElevenLabs voice into the video

Each scene already has an ID (`s01`–`s17`) in `audio_request.json`, and each line is sized to fit its beat — so the clips will drop straight in.

**Option A — elevenlabs.io (your plan), per scene = perfect sync:**
1. On elevenlabs.io, pick your voice + settings (above).
2. Paste each `[timecode]` line, generate, and **Download** it.
3. Name the files `s01.mp3 … s17.mp3` and put them in **`neuracard-video/assets/voice/`**.
4. Tell me they're in — I wire each clip to its scene, keep the captions, optionally add a soft music bed under the voice, and re-render the final synced video.

> One continuous MP3 works too (name it `narration.mp3`), but per-scene clips sync exactly.

**Option B — fully automated (no website):** set your key as an env var
(`$env:ELEVENLABS_API_KEY="..."`) and tell me — I'll run the audio engine on
`audio_request.json`, which generates all 17 lines **in your ElevenLabs voice**, then wire + render. (Pin a voice with `"provider":"elevenlabs","voice_id":"<id>"` in the request if you have a preferred one.)

> Local preview voice (Kokoro) is intentionally skipped here — it needs a Python ML
> package (`kokoro-onnx`) that could disturb this repo's pinned backend env.
