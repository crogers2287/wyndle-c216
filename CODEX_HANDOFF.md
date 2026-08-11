# CODEX HANDOFF — Wyndle C216

## Mission

Build a working prototype that turns **one TP-Link Tapo C216** into an always-on, local-first AI companion endpoint named **Wyndle**.

Canonical pronunciation: **WIN-dull**.

The first prototype should feel like a small robot living inside one inexpensive pan/tilt camera:

- sees through the C216 camera
- hears through the C216 microphone
- wakes when someone says **"Wyndle"** or **"Hey Wyndle"**
- carries on a short natural conversation without requiring the wake word every sentence
- can answer questions about what it currently sees
- can speak back through the C216 speaker
- can pan/tilt when asked, if the available local camera controls permit it
- keeps short-term conversational/visual context
- can optionally maintain small amounts of parent-controlled persistent memory later

This is **not** a surveillance/NVR project and **not** a multi-camera project. Do not introduce Frigate, Home Assistant, MQTT, Kubernetes, distributed workers, a mobile app, or additional cameras unless a concrete blocker makes one unavoidable.

The goal of the first build is simple:

> Put one C216 on a desk, run Wyndle on a local Linux host, say “Wyndle,” ask “what am I holding?”, and hear a useful spoken answer from the camera itself.

---

# Product Direction

Wyndle should eventually be a single core runtime with multiple kid-oriented personalities/configurations rather than separate codebases.

Examples:

- **Wyndle** — general companion
- **Wyndle Junior** — simpler language for younger children
- **Wyndle Explorer** — science, nature, scavenger hunts, show-and-tell
- **Wyndle Tutor** — reading, spelling, homework, guided practice
- **Wyndle Maker** — LEGO, crafts, electronics, projects
- **Wyndle Storytime** — stories and imaginative play

Do **not** implement these as separate apps now. Build one runtime with a persona/config layer.

Example later configuration:

```yaml
persona:
  id: explorer
  display_name: Wyndle Explorer
  wake_words:
    - wyndle
    - hey wyndle
  age_band: 7-11
  traits:
    curiosity: high
    humor: medium
    verbosity: low
  capabilities:
    visual_questions: true
    scavenger_hunts: true
    reading_help: true
    external_web: parent_controlled
  proactive_behavior:
    enabled: false
  memory:
    persistent_enabled: false
```

The MVP uses only the base **Wyndle** persona.

---

# Verified Starting Facts

Use these as working facts, but still probe the physical camera because vendor behavior can vary by firmware/hardware revision.

## Tapo C216

TP-Link's current US product page states that the C216 supports:

- RTSP
- ONVIF
- 5V USB-C power
- pan/tilt physical movement
- microphone/speaker functions as part of the product
- IP65 weather resistance

Reference:

https://www.tp-link.com/us/home-networking/cloud-camera/tapo-c216/

Do not assume that every function is exposed through ONVIF. In particular, **speaker backchannel and PTZ control must be tested rather than assumed**.

## go2rtc

go2rtc currently documents two-way audio support for Tapo sources and can stream audio to supported cameras.

Reference:

https://github.com/AlexxIT/go2rtc

Use go2rtc as a pragmatic camera media bridge if it gets us reliable C216 speaker output quickly. Do not reimplement a proprietary Tapo talk protocol merely for architectural purity.

## Wake-word options

openWakeWord supports custom wake-word models and optional user-specific verifier models.

Reference:

https://github.com/dscripka/openWakeWord

sherpa-onnx has current offline keyword-spotting support and examples.

Reference:

https://github.com/k2-fsa/sherpa-onnx

The wake word must be locally detected and inexpensive enough to run continuously.

## Full-duplex model candidate

MiniCPM-o 4.5 is explicitly designed for simultaneous continuous video/audio input with concurrent speech/text output and proactive interaction.

Reference:

https://github.com/OpenBMB/MiniCPM-o

This makes it an important **Phase 2 experiment**, but do not block the first working prototype on it.

## Custom firmware status

OpenIPC is an active alternative camera firmware project, but the C216 is not currently listed in its public camera wiki as a supported target.

References:

https://github.com/OpenIPC/wiki
https://github.com/OpenIPC/firmware

Treat custom firmware as an optional reverse-engineering track for a spare C216 later. Do not flash or risk the primary test camera.

---

# Core Architecture

Start with a **modular MVP** because it gives us observability and lets us isolate failures.

```text
                        ONE TAPO C216
                  ┌─────────────────────┐
                  │ video / microphone  │
                  │ speaker             │
                  │ pan / tilt          │
                  └──────────┬──────────┘
                             │ LAN / Wi-Fi
                             ▼
                    CAMERA MEDIA LAYER
                  ┌─────────────────────┐
                  │ RTSP / FFmpeg       │
                  │ optional go2rtc     │
                  │ ONVIF / Tapo ctrl   │
                  └──────────┬──────────┘
                             │
                  ┌──────────┴──────────┐
                  ▼                     ▼
          ALWAYS-ON AUDIO          VISUAL BUFFER
          ┌─────────────┐          ┌─────────────┐
          │ wake word   │          │ latest frame│
          │ "Wyndle"    │          │ short ring  │
          │ VAD         │          │ scene change│
          └──────┬──────┘          └──────┬──────┘
                 │ wake                   │
                 └──────────┬─────────────┘
                            ▼
                    CONVERSATION SESSION
                   ┌──────────────────────┐
                   │ STT                  │
                   │ VLM/LLM             │
                   │ recent context       │
                   │ tool calls           │
                   └──────────┬───────────┘
                              ▼
                            TTS
                              │
                              ▼
                    C216 AUDIO BACKCHANNEL
```

Important: **Do not continuously run expensive VLM inference just because the camera is streaming.** The live stream can remain connected continuously while inference is event-driven or low-rate.

---

# Runtime State Machine

Implement an explicit state machine rather than scattered booleans.

Initial states:

```text
BOOTING
CAMERA_CONNECTING
IDLE_WATCHING
WAKE_DETECTED
LISTENING
THINKING
SPEAKING
CONVERSATION_OPEN
DEGRADED
```

Typical interaction:

```text
IDLE_WATCHING
   │
   │ hears "Wyndle"
   ▼
WAKE_DETECTED
   │
   ▼
LISTENING
   │ utterance ends
   ▼
THINKING
   │ response begins
   ▼
SPEAKING
   │ finished
   ▼
CONVERSATION_OPEN
   │ follow-up speech does NOT require wake word
   │
   ├── new user utterance -> LISTENING
   │
   └── timeout -> IDLE_WATCHING
```

Initial conversation-open timeout: configurable, default approximately **15 seconds after the last meaningful exchange**. Do not hard-code this throughout the codebase.

The wake word is required only to start/re-open a session, not before every sentence.

---

# Wake Word: Wyndle

Canonical identity:

```text
Display spelling: Wyndle
Pronunciation: WIN-dull
Primary trigger: "Wyndle"
Secondary trigger: "Hey Wyndle"
```

Children will pronounce names inconsistently. We want the detector tuned to the **phonetic target**, not several literal application names.

During benchmarking, test likely pronunciation variants such as:

```text
WIN-dull
WIN-dle
WEN-dull
WIND-ull
```

Do not make four independent personalities or commands from these. They are recognition variants for the same wake intent.

## Wake-word implementation order

Benchmark:

1. sherpa-onnx keyword spotting
2. openWakeWord custom model
3. optional openWakeWord speaker verifier for adult/parent mode only

For a kid-focused product, do **not** require speaker verification by default. A family camera should be able to respond to authorized children without individually enrolling every voice.

Collect metrics:

```text
true wake detections / attempts
false activations per hour
median detection latency
CPU utilization
RAM utilization
performance with TV/audio playing
performance from 1m / 3m / 5m
adult voices
child voices when test data is available lawfully and appropriately
```

Do not send ambient audio to an LLM while idle merely to determine whether somebody said the name. Wake detection must be local and lightweight.

---

# Conversation Audio Pipeline

The camera microphone is continuously available to the wake detector.

Once Wyndle wakes:

```text
camera audio
   ↓
resample/downmix to model format
   ↓
VAD
   ↓
utterance buffer
   ↓
STT
   ↓
agent
```

Recommended first STT implementation:

- `faster-whisper` if NVIDIA/CUDA is available
- otherwise a local sherpa-onnx or whisper.cpp path is acceptable

Do not transcribe the room continuously while idle.

## Barge-in

Version 1 can be half-duplex:

```text
Wyndle speaking -> user audio ignored/suppressed
```

But structure the audio subsystem so later versions can support:

```text
Wyndle speaking
+ user interrupts
+ VAD detects user speech
+ TTS stops
+ user utterance is processed
```

MiniCPM-o full-duplex experiments belong after the basic media path works.

---

# Echo / Self-Trigger Protection

The C216 microphone will hear the C216 speaker.

This is a critical failure mode.

Minimum MVP behavior:

```text
when TTS playback begins:
    disable wake acceptance
    suppress STT ingestion

when playback ends:
    wait short configurable guard interval
    restore microphone processing
```

Do not allow Wyndle to hear itself say "Wyndle" and recursively activate.

Later:

- acoustic echo cancellation
- barge-in
- reference-audio subtraction
- full duplex

---

# Camera Capability Probe — FIRST IMPLEMENTATION TASK

Before writing the agent, write a diagnostic program that determines what this exact physical camera/firmware exposes.

Create:

```text
tools/probe_c216.py
```

It must test and report:

```text
network connectivity
RTSP main stream
RTSP substream
video codec
resolution
FPS
microphone audio present in RTSP
microphone codec
RTSP reconnect behavior
ONVIF discovery/device info
ONVIF media profiles
ONVIF snapshot URI
ONVIF PTZ service exposed?
ONVIF continuous move?
ONVIF relative move?
ONVIF absolute move?
ONVIF presets/home?
ONVIF audio output configuration?
ONVIF backchannel?
go2rtc Tapo source connectivity
go2rtc audio-to-camera capability
Tapo-protocol PTZ fallback possibilities
```

Output a readable report:

```text
WYNDLE C216 CAPABILITY REPORT
=============================
IP connectivity                PASS
RTSP main video                PASS 2304x1296 H264 30fps
RTSP sub video                 PASS ...
RTSP microphone                PASS codec=...
ONVIF device                   PASS
ONVIF snapshot                 PASS
ONVIF continuous PTZ           PASS/FAIL/UNSUPPORTED
ONVIF audio backchannel        PASS/FAIL/UNSUPPORTED
go2rtc Tapo two-way audio      PASS/FAIL
speaker playback test          PASS/FAIL
round-trip talk latency        xxx ms
```

Never print the camera password.

Save a machine-readable JSON copy to:

```text
data/capability-report.json
```

Ignore this file from git if it contains IPs or other local details.

**Do not proceed to the conversational agent until camera input and speaker output are understood.**

---

# Camera Layer

Suggested layout:

```text
src/wyndle/camera/
    client.py
    rtsp.py
    audio_in.py
    audio_out.py
    onvif.py
    ptz.py
    go2rtc.py
    health.py
```

## Required API

Keep vendor-specific implementation behind a stable interface.

Illustrative interface:

```python
class Camera:
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def snapshot(self, high_quality: bool = True) -> bytes: ...
    def latest_frame(self): ...

    async def play_audio(self, pcm: bytes, sample_rate: int) -> None: ...
    async def stop_audio(self) -> None: ...

    async def pan(self, velocity: float, duration: float) -> None: ...
    async def tilt(self, velocity: float, duration: float) -> None: ...
    async def stop_ptz(self) -> None: ...
    async def home(self) -> None: ...

    def health(self) -> dict: ...
```

Do not let higher-level code know whether audio output is ONVIF, go2rtc, RTSP backchannel, or a Tapo-specific method.

## Video handling

Maintain:

- latest decoded frame
- timestamp
- small rolling buffer only when needed
- reconnect state
- last successful packet/frame timestamp

Use the lower-quality stream for lightweight scene monitoring when useful.

Use a high-quality frame/snapshot when the VLM needs detail.

Avoid multi-second buffering that makes Wyndle feel delayed.

---

# Visual Perception

The MVP needs two levels of vision.

## Level 1 — cheap continuous awareness

Do not use a large VLM for this.

Implement initially:

- frame/scene-change score
- optional lightweight person detection
- timestamp of last significant change

Possible detector:

- YOLO nano-class model or similarly lightweight local detector

Expose state such as:

```json
{
  "person_present": true,
  "scene_change_score": 0.31,
  "last_major_change": "...",
  "latest_frame_age_ms": 43
}
```

## Level 2 — semantic vision

Invoke a VLM when:

- user asks a visual question
- Wyndle intentionally "looks"
- a major scene change matters during an open conversation
- future proactive behavior requires understanding

Core API:

```python
async def answer_visual_question(question: str, frame: bytes) -> str: ...
async def describe_scene(frame: bytes) -> SceneDescription: ...
async def compare_frames(previous: bytes, current: bytes, question: str) -> str: ...
```

Use a provider abstraction so the model can change without touching the camera/agent layers.

---

# VLM / LLM Strategy

## MVP path

Support OpenAI-compatible local endpoints where practical.

Suggested interfaces:

```text
VisionProvider
LanguageProvider
```

They may be the same underlying model or separate models.

Do not hard-code MiniCPM-o into the entire application.

## Phase 2 path: MiniCPM-o 4.5

Once the complete C216 media loop works, build an experiment replacing some modular stages with MiniCPM-o 4.5 live mode.

Questions to benchmark:

```text
Can continuous camera video be sampled into MiniCPM-o live streaming cleanly?
Can camera audio be fed concurrently?
Can its generated audio be streamed directly to the C216 speaker?
Does its full-duplex behavior outperform modular STT -> LLM/VLM -> TTS?
How much GPU memory does the real deployment consume?
What end-to-end latency do we get?
How does it handle wake-session context?
Can wake-word gating sit in front of it without constantly running full inference?
```

Do not assume the end-to-end model is automatically the best product architecture. Measure it.

---

# Agent Runtime

Suggested layout:

```text
src/wyndle/agent/
    runtime.py
    state_machine.py
    session.py
    context.py
    prompts.py
    tools.py
    memory.py
```

The agent receives structured context.

Example:

```json
{
  "time": "2026-08-10T21:00:00-04:00",
  "session": {
    "open": true,
    "seconds_since_wake": 8,
    "seconds_since_last_user_speech": 2
  },
  "camera": {
    "connected": true,
    "person_present": true,
    "last_scene_change_seconds": 4
  },
  "speech": {
    "latest_user_utterance": "What am I holding?"
  },
  "recent_context": []
}
```

Avoid huge repeated prompts containing the entire history.

---

# Agent Behavior

Wyndle is a companion, not a security announcer.

Bad:

```text
A person entered the room.
A person is standing.
The person raised an arm.
The person is holding an object.
```

Desired:

```text
User: "Wyndle."
Wyndle: "Yeah?"
User: "What am I holding?"
Wyndle: "Looks like a red screwdriver."
```

Desired follow-up:

```text
User: "Is it Phillips or flathead?"
Wyndle: [uses a fresh frame if needed]
Wyndle: "Phillips."
```

Desired PTZ:

```text
User: "Look left."
Wyndle: [pans left]
User: "What do you see?"
Wyndle: [fresh frame]
Wyndle: "The workbench and a yellow drill."
```

Do not force Wyndle to verbally acknowledge every tool call.

---

# PTZ Tools

If supported by ONVIF, use ONVIF.

If not, create a Tapo-specific adapter only after probing/research.

High-level tools:

```python
look_left(amount: str = "small")
look_right(amount: str = "small")
look_up(amount: str = "small")
look_down(amount: str = "small")
look_home()
stop_looking()
```

Low-level PTZ wrappers must:

- enforce velocity limits
- enforce maximum movement durations
- always issue stop commands
- recover safely after connection errors

Do not give the LLM raw ONVIF XML or arbitrary camera-control endpoints.

---

# TTS / Camera Speaker

The product experience depends heavily on audio coming from the **camera itself**.

First preference:

```text
local TTS -> PCM/audio -> go2rtc/Tapo backchannel -> C216 speaker
```

Initial TTS candidates:

- Kokoro
- Piper
- sherpa-onnx-supported TTS models
- MiniCPM-o generated speech during Phase 2 experimentation

Primary metrics:

```text
text-ready -> first audible sample
speech naturalness
speaker compatibility
buffer underruns
end-to-end wake -> response latency
```

Streaming/chunked TTS is preferable if the backchannel allows it.

---

# Memory

Do not begin with an elaborate vector database.

## Working memory

Keep recent session context:

- last N user utterances
- last N Wyndle replies
- last visual answers
- recent PTZ actions
- last known simple scene state

## Persistent memory

For MVP, default **OFF**.

If enabled during development, use SQLite and store only explicit/useful events.

Potential schema:

```text
memories
- id
- created_at
- category
- text
- importance
- expires_at nullable
- source_session_id
```

Do not store raw continuous audio or video as “memory.”

Do not build face recognition in the first prototype.

---

# Kid-Focused Privacy and Safety Requirements

These are architecture requirements, not marketing copy.

Because future Wyndle variants are intended for children:

1. **Local-first by default.**
   - Camera media should remain on the LAN unless an explicitly configured inference provider requires otherwise.

2. **No continuous recording by default.**
   - Continuous streaming for perception is not the same as storing continuous footage.
   - Keep only short transient buffers required for runtime operation.

3. **Persistent memory defaults off.**
   - Parent/admin must explicitly enable it.

4. **No external messaging/purchases/control surfaces in kid mode.**
   - Do not give the first prototype tools for email, SMS, purchases, locks, vehicles, etc.

5. **Clear operational state.**
   - Dashboard must visibly show when the system is idle, listening, thinking, or speaking.

6. **Easy mute/privacy control.**
   - Software mute is required in MVP.
   - A future physical device should have a hardware privacy control.

7. **Configurable retention.**
   - Logs and optional memory need retention limits.

8. **Do not infer sensitive traits from children.**
   - No emotion diagnosis, health diagnosis, attractiveness scoring, or similar profiling.

9. **Parent-controlled web/tool access.**
   - Future internet-connected answers should be explicitly bounded by configuration.

The prototype can be built for adult developer testing first while preserving these boundaries in the architecture.

---

# Proactive Interaction

Do **not** enable free-form proactive chatter in MVP.

Build the interface but keep it disabled by default.

Later, a proactive decision may consider:

```text
is a session currently open?
is a person present?
did something semantically meaningful change?
has Wyndle spoken recently?
is the observation useful rather than merely detectable?
is proactive interaction allowed in this persona/config?
```

A future Wyndle Tutor might appropriately say:

```text
"You skipped that line. Start again at 'because'."
```

It should not say:

```text
"You moved your hand."
```

---

# Custom Firmware Investigation Track

This is **not required for MVP**.

Once the stock-firmware prototype works, a second inexpensive C216 can be opened for research.

Create documentation under:

```text
docs/firmware-research/
```

Investigate:

```text
PCB photos
SoC markings
image sensor
SPI-NOR / NAND / eMMC part
UART pads
UART voltage
boot log
bootloader type/version
U-Boot access
firmware partition map
firmware update package format
signature verification
root filesystem format
OpenIPC SoC support
OpenIPC sensor support
recovery path before any write
```

Rules:

- never experiment with the only working C216
- dump original flash before modification
- document recovery before writing flash
- do not publish vendor secrets/credentials captured from a personal unit
- custom firmware is only justified if it materially improves latency, privacy, media access, boot behavior, or local control

OpenIPC installation commonly relies on determining the SoC and may require UART/U-Boot for unsupported vendor devices. Read their current docs before attempting anything.

---

# Minimal Web Debug UI

Build a simple local dashboard. This is an engineering console, not a consumer UI.

Show:

```text
live video preview
camera connection status
RTSP status
camera audio status
speaker/backchannel status
ONVIF status
PTZ status
wake detector status
wake confidence
current state-machine state
VAD state
latest transcript
latest visual answer
latest agent response
conversation session timer
recent structured events
latency metrics
```

Controls:

```text
Test speaker
Analyze current frame
Force wake/session open
End session
Mute Wyndle
Pan left
Pan right
Tilt up
Tilt down
Stop PTZ
Home PTZ
```

Use WebSocket or SSE for live state updates.

---

# Observability

Use structured logs.

Example:

```text
[CAMERA] rtsp_connected stream=main
[CAMERA] audio_detected codec=aac
[WAKE] score=0.81 phrase=wyndle accepted=true
[SESSION] opened
[VAD] speech_start
[VAD] speech_end duration_ms=1870
[STT] latency_ms=244 text="what am I holding"
[VISION] reason=visual_question latency_ms=611
[AGENT] first_token_ms=132
[TTS] first_audio_ms=96
[SPEAKER] playback_started
[SESSION] timeout
```

Collect latency histograms for:

```text
wake word end -> wake accepted
speech end -> transcript final
transcript final -> first LLM token
visual request -> VLM result
LLM response -> first TTS audio
speech end -> first audible camera response
```

The last metric is the one the user actually feels.

---

# Reliability Requirements

The process must recover automatically from:

- Wi-Fi interruption
- RTSP disconnect
- camera reboot
- go2rtc restart
- ONVIF timeout
- VLM timeout
- LLM timeout
- STT failure
- TTS failure
- audio-backchannel failure

Use bounded exponential backoff.

One subsystem failure should move the runtime into a degraded state rather than crashing the entire process.

Example:

```text
camera video works + speaker unavailable
=> dashboard says DEGRADED_AUDIO_OUT
=> visual console interaction can still work
```

---

# Security

MVP is LAN-only.

Requirements:

- camera credentials only in `.env` or secret store
- never commit `.env`
- never log passwords
- never interpolate credentials into browser-visible URLs
- dashboard binds to localhost by default
- no automatic public tunnel
- no UPnP port forwarding
- sanitize camera URIs in logs

Example environment:

```env
WYNDLE_NAME=Wyndle
WYNDLE_WAKE_WORD=wyndle
WYNDLE_WAKE_SECONDARY=hey wyndle

TAPO_IP=192.168.1.123
TAPO_USERNAME=wyndle-local
TAPO_PASSWORD=change-me

RTSP_MAIN=rtsp://wyndle-local:change-me@192.168.1.123:554/stream1
RTSP_SUB=rtsp://wyndle-local:change-me@192.168.1.123:554/stream2

GO2RTC_URL=http://127.0.0.1:1984

VISION_BASE_URL=http://127.0.0.1:8000/v1
VISION_MODEL=local-vlm

LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_MODEL=local-agent-model

STT_ENGINE=faster-whisper
TTS_ENGINE=kokoro

CONVERSATION_TIMEOUT_SECONDS=15
PERSISTENT_MEMORY_ENABLED=false
PROACTIVE_SPEECH_ENABLED=false
```

The actual implementation may normalize secrets better than this example.

---

# Recommended Repository Layout

```text
wyndle-c216/
├── README.md
├── CODEX_HANDOFF.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── docker-compose.yml              # only if useful for go2rtc/local services
│
├── config/
│   └── personas/
│       └── wyndle.yaml
│
├── src/
│   └── wyndle/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       │
│       ├── camera/
│       │   ├── client.py
│       │   ├── rtsp.py
│       │   ├── audio_in.py
│       │   ├── audio_out.py
│       │   ├── onvif.py
│       │   ├── ptz.py
│       │   ├── go2rtc.py
│       │   └── health.py
│       │
│       ├── audio/
│       │   ├── pipeline.py
│       │   ├── wake.py
│       │   ├── vad.py
│       │   ├── stt.py
│       │   ├── tts.py
│       │   └── echo_guard.py
│       │
│       ├── vision/
│       │   ├── frames.py
│       │   ├── scene_change.py
│       │   ├── detector.py
│       │   ├── provider.py
│       │   └── minicpm_live.py
│       │
│       ├── agent/
│       │   ├── runtime.py
│       │   ├── state_machine.py
│       │   ├── session.py
│       │   ├── context.py
│       │   ├── prompts.py
│       │   ├── tools.py
│       │   └── memory.py
│       │
│       └── web/
│           ├── app.py
│           └── static/
│
├── tools/
│   ├── probe_c216.py
│   ├── test_rtsp.py
│   ├── test_camera_audio.py
│   ├── test_speaker.py
│   ├── test_ptz.py
│   ├── benchmark_wakeword.py
│   └── benchmark_latency.py
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── data/
│   └── .gitkeep
│
└── docs/
    ├── architecture.md
    ├── camera-capabilities.md
    ├── wake-word.md
    └── firmware-research/
```

Do not create empty architecture for its own sake. Create modules as they become necessary.

---

# Implementation Sequence

## Milestone 0 — Bootstrap

Deliver:

```text
Python project
configuration loader
logging
README setup instructions
.env.example
development commands
basic tests
```

No agent yet.

## Milestone 1 — C216 capability report

Deliver:

```text
probe_c216.py
reliable RTSP main/sub connection
microphone extraction
ONVIF inspection
PTZ test if exposed
speaker/two-way-audio test using go2rtc/Tapo route
```

Acceptance:

> We know exactly which local input/output/control paths work on the physical C216.

## Milestone 2 — Wyndle wake word

Deliver:

```text
continuous camera audio input
local wake detector
"Wyndle" trigger
"Hey Wyndle" trigger
false-positive metrics
simple state transition IDLE -> WAKE_DETECTED
```

Acceptance:

> Wyndle reliably wakes from the camera microphone without continuously transcribing ambient speech.

## Milestone 3 — Voice loop

Deliver:

```text
wake
VAD
STT
simple text agent
TTS
camera speaker output
conversation-open timeout
self-echo guard
```

Acceptance:

```text
User: "Wyndle."
Camera: "Yeah?"
User: "Say the number seven."
Camera: "Seven."
```

No vision required yet.

## Milestone 4 — Visual question answering

Deliver:

```text
fresh high-quality frame capture
VLM provider
agent visual tool
visual answer spoken through camera
```

Acceptance:

```text
User: "Wyndle. What am I holding?"
Wyndle: [correctly answers from current camera image]
```

## Milestone 5 — PTZ

Deliver:

```text
safe deterministic PTZ tools
agent tool invocation
fresh visual context after movement
```

Acceptance:

```text
User: "Wyndle, look left."
Camera pans left and stops.
User: "What do you see?"
Wyndle answers from the new view.
```

## Milestone 6 — Context

Deliver:

```text
short working memory
follow-up references
simple scene/world state
```

Acceptance:

```text
User: "This yellow drill has the bad battery."
...
User: "Which drill had the bad battery?"
Wyndle: "The yellow one you showed me."
```

Persistent memory remains disabled by default.

## Milestone 7 — MiniCPM-o live experiment

Run a controlled comparison against the modular pipeline.

Measure:

```text
latency
VRAM
CPU
quality
barge-in behavior
camera stream adaptation
speech naturalness
stability over 1+ hour
```

Keep whichever architecture actually performs better.

## Milestone 8 — optional firmware research

Only after stock firmware is proven and only on a spare unit.

---

# First End-to-End Demo

The prototype is successful when this works reliably:

```text
[Wyndle is idle. Camera stream is connected. Wake detector is running.]

User walks into view.
Wyndle does not randomly narrate the event.

User: "Wyndle."

Wyndle: "Yeah?"

User holds up a screwdriver.
User: "What am I holding?"

Wyndle captures a fresh frame.
Wyndle analyzes it.

Wyndle: "A screwdriver."

User: "What color is the handle?"

Wyndle: "Red."

User: "Look left."

Wyndle pans left and stops.

User: "What's over there?"

Wyndle captures a new frame.
Wyndle answers appropriately.

[15 seconds of no meaningful conversation]

Session closes.
Wyndle returns to wake-word mode.
```

---

# Performance Targets

These are targets, not reasons to fake results.

Initial goals:

```text
wake detection after phrase:       < 500 ms preferred
speech end -> final transcript:    < 700 ms preferred
simple non-vision first audio:     < 1.5 s preferred
visual question first audio:       < 2.5 s preferred
PTZ command initiation:            < 500 ms preferred
RTSP recovery after Wi-Fi return:  automatic
idle wake CPU burden:              low enough for 24/7 use
```

Report actual measured values.

Do not hide latency by playing canned filler phrases unless explicitly configured later.

---

# Engineering Principles

1. **One camera first.**
2. **Working loop before elegance.**
3. **Probe capabilities; do not assume.**
4. **Local-first.**
5. **Wake-word gated.**
6. **Do not store continuous media.**
7. **Vendor-specific code stays behind adapters.**
8. **Measure latency at every boundary.**
9. **Recover automatically from camera/network failures.**
10. **Keep the agent quiet unless it has a reason to speak.**
11. **Do not overbuild multi-camera/NVR infrastructure.**
12. **Preserve a path to kid-focused personas without forking the runtime.**

---

# Non-Goals for the First Prototype

Do not build:

```text
multi-camera routing
Frigate integration
Home Assistant integration
full NVR recording
cloud video storage
facial recognition
emotion recognition
multi-user biometrics
complex vector DB
mobile app
public internet access
remote camera sharing
purchases
email/SMS tools
smart-lock control
robot locomotion
custom C216 firmware
```

---

# Codex Working Instructions

Start at **Milestone 0** and immediately proceed into **Milestone 1**.

Do not spend the first iteration designing an enormous abstraction layer.

Prefer working diagnostic scripts and measured behavior.

When hardware-dependent functionality cannot be verified because the physical C216 is not reachable from the development environment:

1. implement the diagnostic path completely
2. provide the exact command needed to run it
3. fail with clear actionable output rather than a stack trace
4. continue implementing components that do not require physical hardware
5. do not invent successful camera test results

Maintain `docs/camera-capabilities.md` as the source of truth for what has actually been tested.

For each milestone:

```text
implement
run tests
record measured results
update README/docs
commit cleanly
```

The first engineering priority is not “AI personality.” It is proving the physical loop:

```text
C216 mic -> wake/STT -> agent -> TTS -> C216 speaker
                     +
                 C216 video -> VLM
                     +
                    PTZ
```

Once that works, Wyndle becomes an agent/product problem rather than a camera-integration problem.
