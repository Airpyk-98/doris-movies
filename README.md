# Doris Movies (Story to Film Studio)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Firebase](https://img.shields.io/badge/Firebase-Hosting%20%26%20Firestore-orange)](https://firebase.google.com/)
[![Kaggle GPU](https://img.shields.io/badge/Kaggle-NVIDIA%20T4%20GPU-blue)](https://www.kaggle.com/)
[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA-NIM%20Inference-76B900)](https://build.nvidia.com/)
[![Kie.ai](https://img.shields.io/badge/Kie.ai-Image%20%26%20Video%20Models-purple)](https://kie.ai/)
[![Hugging Face](https://img.shields.io/badge/Hugging%20Face-Dataset%20Storage-yellow)](https://huggingface.co/)

**Doris Movies (Story to Film)** is an autonomous, end-to-end AI cinema studio built following the `epic-automate` architecture. It transforms raw text stories or scripts into coherent, multi-scene films on **Kaggle Tesla T4 GPU compute** without intermediate manual pauses.

---

## 1. System Architecture & Information Flow

```
                      [ USER WEB BROWSER ]
                  (Firebase Hosting / Vanilla JS)
                     /            |            \
    (Auth & State)  /             |             \ (Assets & Stream)
                   v              |              v
       [ Google Cloud Firestore ] |       [ FastAPI Cloud Relay ]
        - User Credentials        |         (Port 7860 / Uvicorn)
        - Private Story Drafts    |               |
        - Live Job Telemetry      |               v
                   ^              |       [ Kaggle CLI Push ]
                   |              |       (Isolated Config Dir)
                   |              |               |
                   |              |               v
                   +--------------+------- [ Kaggle T4 GPU Worker ]
                                           (kaggle_executor.py)
                                                  |
           +----------------------+---------------+----------------------+
           |                      |                                      |
           v                      v                                      v
    [ NVIDIA NIM API ]      [ Kie.ai API ]                        [ FFmpeg Engine ]
    - Scene Planning        - NanoBanana 2 Lite (Frames)          - 30fps Normalization
    - Safety Sanitizer      - Grok Imagine (Video Animation)      - Stereo AAC 192k Audio
    - SSE Streaming         - Seedance 2.5 / Wan 3.0 / Kling      - Master Concat Demuxer
           |                      |                                      |
           +----------------------+--------------------------------------+
                                  |
                                  v
                   [ Hugging Face Datasets Storage ]
                     (Auto-created User Repo)
                     - Reference Uploads
                     - Scene 1..N MP4s
                     - Complete_Story_Film.mp4
```

---

## 2. Technology Stack & Component Deep Dive

### A. Frontend Layer (`public/`)
* **Technology**: Vanilla HTML5, CSS3, Modern ES Modules (Zero npm build step, maximum speed and reliability).
* **Design Language**: Minimalist Studio aesthetic (Primary: `#FFFFFF` / `#F8F8F5`, Signal Yellow: `#FACC15`, Architectural Dark: `#0A0A0A`).
* **Firebase SDK v10**: CDN-loaded ES modules for `firebase/app`, `firebase/auth`, and `firebase/firestore`.
* **State Management**:
  - Live bi-directional syncing with Firestore `onSnapshot`.
  - Automatic local draft saving (`/users/{uid}/drafts/current`).
  - Dynamic aspect ratio, resolution, duration, and generation mode presets linked to selected models.
  - Live Kie.ai credit cost calculator dynamically breaking down cost per frame, cost per video clip, and full-project totals.
  - Numbered auto-downloading engine for completed scenes (`1.Scene 1 - Title.mp4`).

### B. Auth & Database Layer (`firestore.rules`, `firestore.indexes.json`)
* **Authentication**: Google Sign-In with popup provider and isolated anonymous fallback.
* **Security Rules**: Fine-grained per-user isolation:
  - Users can strictly read and write only their own `/users/{uid}/...` documents.
  - Automations under `/automations/{jobId}` verify `resource.data.owner_uid == request.auth.uid`.
  - Kaggle worker updates its designated automation document via Firestore REST API or Admin SDK.

### C. Local & Cloud Relay Space (`relay_space/`)
* **Framework**: FastAPI + Uvicorn (`relay_space/app.py`).
* **Purpose**: Solves browser CORS restrictions and securely mediates between the browser and backend services.
* **Endpoints**:
  - `GET /`: Health check.
  - `POST /api/nvidia/models`: Fetches live model catalog from `https://integrate.api.nvidia.com/v1/models`.
  - `POST /api/kie/credits`: Queries user balance from `https://api.kie.ai/api/v1/chat/credit`.
  - `POST /api/hf/ensure-dataset`: Auto-provisions the user's asset dataset on Hugging Face.
  - `POST /api/hf/upload-reference`: Streams uploaded reference images to Hugging Face via temporary file buffers.
  - `POST /api/kaggle/launch`: Dynamically injects job parameters into `kaggle_executor.py`, configures an isolated `KAGGLE_CONFIG_DIR`, and triggers `kaggle kernels push`.

### D. Compute & Orchestration Worker (`kaggle_worker/kaggle_executor.py`)
* **Hardware**: Kaggle T4 GPU (`NvidiaTeslaT4`) with internet access enabled.
* **Execution Pipeline**:
  1. **Initialization & HF Dataset Check**: Auto-creates `<hf_username>/story-to-film-assets` if not already present.
  2. **Stage 1 — Scene Planning**: Invokes NVIDIA NIM using SSE streaming (`stream: True`) to prevent 120s gateway read timeouts. Automatically cleans prompts using a dual-layer regex anti-flagging safety sanitizer.
  3. **Stage 2 — Reference-Consistent Images**: Calls Kie.ai Image API (`nano-banana-2-lite` default) passing uploaded `@tag` URLs for visual character and environmental consistency.
  4. **Stage 3 — Sequential Video Animation**: Calls Kie.ai Video API (`grok-imagine/image-to-video` default, plus Seedance 2.5, Wan 3.0, Kling 3.0, Veo 3.1) and immediately writes completed MP4 files to Hugging Face.
  5. **Stage 4 — FFmpeg Film Stitcher**:
     - Tests audio presence with `ffprobe`.
     - Normalizes resolution, aspect ratio, padding, and forces 30fps YUV420p.
     - Preserves original dialogue/voices with stereo AAC (`192k @ 44.1kHz`), injecting an `anullsrc` synthetic silent channel only if an individual scene had no audio stream.
     - Concat-demuxes into `Complete_Story_Film.mp4` with `+faststart` metadata.
  6. **Telemetry & Watchdog**: Continuously reports progress (0-100%) and logs to Firestore, listening for cancel signals to kill subprocesses immediately.

---

## 3. Directory Structure

```
doris-movies/
├── .firebaserc                     # Active Firebase project mapping
├── .gitignore                      # Security-hardened git exclusion rules
├── firebase.json                   # Firebase Hosting, Firestore, and Auth configs
├── firestore.rules                 # Multi-user isolation security rules
├── firestore.indexes.json          # Firestore query indexes
├── README.md                       # Comprehensive system documentation
├── handoff.md                      # Operational log and audit trail
├── public/                         # Production frontend assets
│   ├── index.html                  # Responsive studio interface
│   ├── style.css                   # Minimalist CSS styling
│   └── app.js                      # Core frontend logic & Firestore bindings
├── kaggle_worker/                  # Kaggle GPU execution files
│   ├── kaggle_executor.py          # 4-stage pipeline orchestrator (ASCII safe)
│   └── kernel-metadata.json        # Kaggle kernel manifest
└── relay_space/                    # FastAPI Relay service
    ├── app.py                      # Relay endpoints & Kaggle launcher
    ├── Dockerfile                  # Container definition for cloud deployment
    ├── kaggle_executor.py          # Mirrored worker code for dynamic injection
    └── README.md                   # Relay service instructions
```

---

## 4. Quick Start & Setup Guide for New Agents

### Prerequisites
- Python 3.10+
- Node.js 18+ & npm
- Firebase CLI (`npm install -g firebase-tools`)
- FFmpeg installed in system PATH

### Step 1: Clone Repository
```bash
git clone https://github.com/Airpyk-98/doris-movies.git
cd doris-movies
```

### Step 2: Install Python Dependencies
```bash
pip install fastapi "uvicorn[standard]" requests huggingface_hub kaggle pydantic
```

### Step 3: Start the Local Cloud Relay
```bash
python -m uvicorn app:app --app-dir relay_space --host 0.0.0.0 --port 7860
```
Verify the relay by visiting `http://localhost:7860` (should return `{"status": "ok", "service": "Story to Film Relay"}`).

### Step 4: Deploy Firebase Web Studio
```bash
# Log in to Firebase CLI
firebase login

# Verify project selection
firebase use story-to-film-epic-98

# Deploy Firestore rules & Hosting
firebase deploy --only firestore:rules,hosting
```
The live web studio will be accessible at:
`https://story-to-film-epic-98.web.app`

---

## 5. Configuration & Credentials Reference

Users configure credentials directly within the **Settings & Keys** tab of the web app. Credentials are saved encrypted into the user's private Firestore profile (`/users/{uid}/settings/credentials`):

| Key | Format / Source | Description |
|---|---|---|
| **Kie.ai API Key** | `api-key-...` from [Kie.ai](https://kie.ai) | Powers NanoBanana image and Grok/Seedance video generation. |
| **NVIDIA API Key** | `nvapi-...` from [NVIDIA Build](https://build.nvidia.com) | Powers scene planning via NVIDIA NIM LLMs. |
| **Kaggle Username** | Username from [Kaggle](https://www.kaggle.com) | Directs GPU worker kernel pushes to your Kaggle account. |
| **Kaggle Key** | 32-character API key from `kaggle.json` | Authenticates kernel dispatch. |
| **Hugging Face Username** | HF account name | Namespace for auto-created dataset repository. |
| **Hugging Face Token** | `hf_...` (Write permission required) | Uploads reference images, scene clips, and stitched films. |
| **Relay URL** | `http://localhost:7860` (or deployed Space) | Bridge for CORS-free Kaggle pushes and dataset creation. |

---

## 6. Critical Technical Notes & Troubleshooting

1. **Windows Encoding & Kaggle CLI**:
   - The Kaggle CLI on Windows opens scripts using the system default encoding (often `cp1252`). `kaggle_executor.py` is strictly maintained as pure ASCII to prevent UnicodeDecodeErrors during `kaggle kernels push`.
   - The relay automatically sets `PYTHONUTF8=1` and uses an isolated temporary `KAGGLE_CONFIG_DIR`.

2. **NVIDIA NIM SSE Streaming**:
   - Reasoning models (such as `z-ai/glm-5.3` or DeepSeek) stream hidden reasoning content prior to generating final JSON. Standard HTTP calls time out at 120 seconds.
   - `kaggle_executor.py` uses Server-Sent Events (`"stream": True`) with per-chunk timeout tracking and automatic fallbacks to `meta/llama-3.3-70b-instruct`, `deepseek-ai/deepseek-v3.1`, or `qwen/qwen2.5-72b-instruct`.

3. **FFmpeg Audio Preservation**:
   - Scene videos generated by Kie.ai models contain synchronized audio and voice tracks.
   - Stage 4 in `kaggle_executor.py` explicitly normalizes audio via `-c:a aac -b:a 192k -ar 44100 -ac 2` and only generates synthetic silence (`anullsrc`) if a clip entirely lacks audio. The `-an` flag must **never** be used.

---

## 7. License
Distributed under the MIT License. See `LICENSE` for details.
