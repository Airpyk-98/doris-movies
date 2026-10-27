# Epic Automate Project Handoff — Story to Film Studio

> **Note for Subsequent Agents**: This document tracks the real-time operational status, architectural bindings, credentials status, and incremental modifications for the **Story to Film** automation project (`epic-automate` standard). Update this document after every major change.

---

## 1. Project Identity & Architecture
- **Project Name**: Story to Film — Autonomous AI Cinema Studio
- **Workspace**: `c:\Users\DELL\Desktop\FAC2`
- **Date Created**: 2026-10-26
- **Last Modified**: 2026-10-27 01:08
- **Modus Operandi**: `epic-automate`
  - **Frontend**: Dedicated Brand-New Firebase Project (`story-to-film-epic-98`) on Firebase Hosting (`https://story-to-film-epic-98.web.app`).
  - **Design System**: Minimalist White (`#FFFFFF` / `#F8F8F5`), Signal Cinema Yellow (`#FACC15`), and Architectural Black (`#0A0A0A`) engineered with `ui-ux-pro-max`, `impeccable`, and `imagegen-frontend-mobile`.
  - **Multi-User Authentication & Data Isolation**: Firebase Authentication (Google Sign-In + isolated session fallback) with per-user Firestore Security Rules (`firestore.rules`).
  - **State & Progress**: Cloud Firestore (`/users/{uid}/settings/credentials`, `/users/{uid}/drafts/current`, `/automations/{jobId}`).
  - **Compute Server**: Kaggle T4 GPU (`NvidiaTeslaT4`) via Kernel Push (`<user_kaggle_username>/story-to-film-worker`), running uninterrupted 4-stage execution:
    1. **Stage 1 (Scene Planning)**: NVIDIA NIM (`https://integrate.api.nvidia.com/v1/chat/completions`) on Kaggle with user-selected model & dual-layer Anti-Flagging Prompt Sanitizer.
    2. **Stage 2 (Scene Images)**: Kie.ai (`POST https://api.kie.ai/api/v1/jobs/createTask`) with `@tag` reference image URLs (`nano-banana-2-lite` default + NanoBanana 2, 2.1, Pro, Seedream 5.0/4.5, Flux Kontext, Grok Imagine Image).
    3. **Stage 3 (Scene Videos)**: Kie.ai sequential animation (`grok-imagine/image-to-video` default + Seedance 2.5, Seedance 2.0, Wan 3.0 / 2.7 / 2.5, Kling 3.0 Omni / 2.6, Google Veo 3.1, Runway Gen-4, Hailuo 02) with instant browser auto-download (`1.Scene 1 - Title.mp4`, etc.).
    4. **Stage 4 (Film Stitching & Storage)**: FFmpeg normalization & concatenation on Kaggle T4 into `Complete_Story_Film.mp4`, auto-uploaded to the user's Hugging Face Dataset with an embedded HTML5 Video Player preview.

---

## 2. Infrastructure Endpoints & Identifiers
| Service | Resource | Identifier / URL | Status |
|---|---|---|---|
| **Firebase Hosting** | Web Frontend | `https://story-to-film-epic-98.web.app` | 🟢 Live |
| **Cloud Firestore** | State & User Settings | Project: `story-to-film-epic-98` (`nam5`) | 🟢 Active |
| **Firebase Auth** | Multi-User Sign-In | Google Sign-In + Isolated Session | 🟢 Active |
| **Kaggle Kernel** | T4 GPU Worker | `<user_kaggle_username>/story-to-film-worker` (`NvidiaTeslaT4`) | 🟢 Ready |
| **Hugging Face** | Default Asset Dataset | `https://huggingface.co/datasets/pearlyoscar/story-to-film-assets` (auto-creates per user) | 🟢 Active |
| **GitHub** | Source Code Repo | `https://github.com/Airpyk-98/story-to-film-epic` | 🟢 Synced |
| **Relay Server** | Local/Cloud Dispatcher | `http://localhost:7860` (`relay_space/app.py`) | 🟢 Running |

---

## 3. Credentials & Secrets Audit
- [x] **GitHub PAT**: Verified (`@Airpyk-98`, `repo` scope).
- [x] **Hugging Face Token**: Verified (`@pearlyoscar`, Write access, also configurable per user in UI Settings).
- [x] **Kaggle API**: Verified (`@ikechukwuebiringa`, normalized UTF-8 `~/.kaggle/kaggle.json`, also configurable per user in UI Settings).
- [x] **Firebase Authentication**: Active CLI session (`gabrielyoutubeautomation@gmail.com`) bound to new project `story-to-film-epic-98`.
- [x] **Kie.ai & NVIDIA NIM Keys**: Configured per-user via the private **Settings & Keys** tab in the UI (`/users/{uid}/settings/credentials`), with live Kie.ai credit balance checking (`GET https://api.kie.ai/api/v1/chat/credit`) and live NVIDIA NIM model catalog loading (`GET https://integrate.api.nvidia.com/v1/models`).

---

## 4. Work Completed & Modifications Log
- **2026-10-26**: Audited and verified all 4 foundational Epic Automate credentials (GitHub, Hugging Face, Kaggle, Firebase).
- **2026-10-26**: Provisioned brand-new isolated Firebase project `story-to-film-epic-98`, enabled Firestore & Identity Toolkit APIs, and created `(default)` Firestore database.
- **2026-10-26**: Authored and deployed strict per-user Firestore security rules (`firestore.rules`) via `firestore-rules-author` subagent.
- **2026-10-26**: Built `kaggle_worker/kaggle_executor.py` implementing uninterrupted 4-stage execution (NVIDIA NIM planning + Anti-Flagging Sanitizer -> Kie.ai `@tag` reference images -> Kie.ai videos -> FFmpeg T4 film stitching -> Hugging Face Dataset upload + real-time Firestore reporting & cancellation watchdog).
- **2026-10-26**: Built minimalist White, Signal Yellow, and Black frontend (`public/index.html`, `public/style.css`, `public/app.js`) featuring dynamic model presets, real-time Kie.ai credit cost estimator, per-user Kie.ai credit balance checker, NVIDIA model catalog loader, `@tag` multi-upload, and auto-downloading scene clips.
- **2026-10-26**: Deployed to Firebase Hosting (`https://story-to-film-epic-98.web.app`) and pushed full repository to GitHub (`https://github.com/Airpyk-98/story-to-film-epic`).
- **2026-10-27**: Added `/api/hf/upload-reference` endpoint in `relay_space/app.py` (using temp-file-backed `HfApi.upload_file`) and isolated `KAGGLE_CONFIG_DIR` + `PYTHONUTF8=1` for reliable per-user Kaggle kernel pushes.
- **2026-10-27**: Upgraded `kaggle_worker/kaggle_executor.py` and `relay_space/kaggle_executor.py` to use SSE streaming (`"stream": True`) with `(25, 90)` per-chunk read timeouts, live reasoning/token telemetry, and automatic fast-model fallbacks (`meta/llama-3.3-70b-instruct`, `deepseek-ai/deepseek-v3.1`, `qwen/qwen2.5-72b-instruct`, `meta/llama-3.1-70b-instruct`) so reasoning models like `z-ai/glm-5.3` never fail with a 120s read timeout on Stage 1.

---

## 5. Instructions for Subsequent Agents
1. **Never reuse an old Firebase project** unless explicitly instructed by the user.
2. **Relay Service**: Ensure `relay_space/app.py` is running on port `7860` (`python -m uvicorn app:app --app-dir relay_space --host 0.0.0.0 --port 7860`) when triggering local Kaggle CLI kernel pushes or proxying CORS-restricted endpoints.
3. **Modify Compute Pipeline**: Edit `kaggle_worker/kaggle_executor.py` and copy to `relay_space/kaggle_executor.py`.
4. **Always update this `handoff.md`** file after any modification.
