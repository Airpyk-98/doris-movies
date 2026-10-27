#!/usr/bin/env python3
"""
Story to Film - Epic Automate Kaggle T4 GPU Executor
====================================================
Executes the complete uninterrupted 4-stage pipeline on Kaggle T4 GPU:
  Stage 1: Story-to-Scene Planning via NVIDIA NIM (with strict Anti-Flagging Sanitizer)
  Stage 2: Reference-Consistent Starting Frame Image Generation via Kie.ai (NanoBanana 2 Lite & peers)
  Stage 3: Sequential Scene Video Animation via Kie.ai (Grok Imagine, Seedance 2.0/2.5, Wan 3.0, Kling, etc.)
  Stage 4: Coherent Film Stitching via FFmpeg + Auto-Upload to User's Hugging Face Dataset
"""

import os
import re
import sys
import json
import time
import shutil
import threading
import subprocess
import urllib.parse
import requests
from huggingface_hub import HfApi

# =====================================================================
# 1. CONFIGURATION & JOB PAYLOAD INJECTION
# =====================================================================
JOB_CONFIG_RAW = os.environ.get("JOB_CONFIG_JSON", "__JOB_CONFIG_JSON_PLACEHOLDER__")
try:
    if JOB_CONFIG_RAW and not JOB_CONFIG_RAW.startswith("__JOB_CONFIG"):
        JOB_CONFIG = json.loads(JOB_CONFIG_RAW)
    else:
        JOB_CONFIG = {}
except Exception as e:
    print(f"[Init Warning] Failed to parse JOB_CONFIG_JSON: {e}")
    JOB_CONFIG = {}

FIRESTORE_PROJECT_ID = JOB_CONFIG.get("firebase_project_id") or os.environ.get("FIREBASE_PROJECT_ID", "story-to-film-epic-98")
JOB_ID = JOB_CONFIG.get("job_id") or os.environ.get("JOB_ID", "job_demo")

NVIDIA_API_KEY = JOB_CONFIG.get("nvidia_api_key") or os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_MODEL = JOB_CONFIG.get("nvidia_model") or os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
KIE_API_KEY = JOB_CONFIG.get("kie_api_key") or os.environ.get("KIE_API_KEY", "")
HF_USERNAME = JOB_CONFIG.get("hf_username") or os.environ.get("HF_USERNAME", "")
HF_TOKEN = JOB_CONFIG.get("hf_token") or os.environ.get("HF_TOKEN", "")
HF_DATASET_NAME = JOB_CONFIG.get("hf_dataset_name") or os.environ.get("HF_DATASET_NAME", "story-to-film-assets")

if "/" in HF_DATASET_NAME:
    HF_DATASET_REPO = HF_DATASET_NAME
elif HF_USERNAME:
    HF_DATASET_REPO = f"{HF_USERNAME}/{HF_DATASET_NAME}"
else:
    HF_DATASET_REPO = os.environ.get("HF_DATASET_REPO", "pearlyoscar/story-to-film-assets")

STORY_TEXT = JOB_CONFIG.get("story", "")
REFERENCE_TAGS = JOB_CONFIG.get("reference_tags", [])
IMAGE_MODEL = JOB_CONFIG.get("image_model", "nano-banana-2-lite")
IMAGE_RESOLUTION = JOB_CONFIG.get("image_resolution", "1K")
VIDEO_MODEL = JOB_CONFIG.get("video_model", "grok-imagine/image-to-video")
ASPECT_RATIO = JOB_CONFIG.get("aspect_ratio", "16:9")
SCENE_DURATION = int(JOB_CONFIG.get("scene_duration", 6))
VIDEO_QUALITY = JOB_CONFIG.get("video_quality", "720p")
VIDEO_MODE = JOB_CONFIG.get("video_mode", "normal")
RETRY_SCENES_ONLY = JOB_CONFIG.get("retry_scenes_only", False)
EXISTING_SCENES = JOB_CONFIG.get("existing_scenes", [])

cancel_event = threading.Event()
active_subprocesses = []
logs_buffer = []
scenes_state = []


# =====================================================================
# 2. ANTI-FLAGGING PROMPT SANITIZER (ZERO-MODERATION-FAILURE ENGINE)
# =====================================================================
FLAGGED_WORD_REPLACEMENTS = {
    r"\bblood(y|ied)?\b": "crimson shadow",
    r"\bgore\b|\bgory\b": "dramatic shadow",
    r"\bkill(s|ed|ing)?\b": "confront",
    r"\bmurder(s|ed|ing|er)?\b": "betrayal",
    r"\bdead\b|\bcorpse\b|\bcadaver\b": "motionless figure",
    r"\bdie(s|d)?\b|\bdying\b|\bdeath\b": "fading away",
    r"\bgun(s|shot)?\b|\bpistol\b|\brifle\b|\bfirearm\b": "metallic signaling device",
    r"\bshoot(s|ing)?\b|\bshot\b": "project energy toward",
    r"\bknife\b|\bdagger\b|\bblade\b|\bsword\b|\bweapon(s)?\b": "gleaming metallic prop",
    r"\bstab(s|bed|bing)?\b|\bslash(ed|ing)?\b": "lunges dramatically toward",
    r"\bbomb(s|ing)?\b|\bexplosi(on|ve)\b|\bgrenade\b|\bterroris(t|m)\b": "sudden blinding flash of light",
    r"\bsuicid(e|al)\b|\bself[- ]harm\b|\bhang(ed|ing)?\b": "isolated contemplation",
    r"\bnude\b|\bnaked\b|\bnsfw\b|\bsexy\b|\berotic\b|\bsensual\b|\bundress(ed)?\b": "wardrobe-styled",
    r"\brape\b|\bassault(ed|ing)?\b|\babuse(d)?\b|\btortur(e|ed|ing)\b": "intense argument",
    r"\bdrug(s)?\b|\bcocaine\b|\bheroin\b|\bmeth\b|\bnarcotic(s)?\b": "mysterious potion",
    r"\bchild\b|\bkid(s)?\b|\bminor\b|\bbaby\b|\binfant\b": "young apprentice",
    r"\bhitler\b|\bnazi\b|\bfascist\b": "historical authoritarian",
    r"\bchoke(s|d|ing)?\b|\bstrangl(e|ed|ing)\b": "grip the shoulder of",
    r"\bbleed(s|ing)?\b|\bwound(s|ed)?\b|\binjur(y|ed)\b|\bscar(s)?\b": "weathered mark",
    r"\bfight(s|ing)?\b|\bbrawl\b|\bpunch(es|ed|ing)?\b|\bkick(s|ed|ing)?\b": "intense martial choreography",
}


def sanitize_prompt_for_generation(prompt_text: str) -> str:
    """Strips and replaces any terms that could trigger Kie.ai image/video safety filters."""
    if not prompt_text:
        return ""
    cleaned = prompt_text
    for pattern, replacement in FLAGGED_WORD_REPLACEMENTS.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[`#*<>]", "", cleaned).strip()
    return cleaned


# =====================================================================
# 3. REAL-TIME FIRESTORE SYNC & CANCELLATION WATCHDOG
# =====================================================================
def append_log(msg: str):
    ts = time.strftime("%H:%M:%S", time.gmtime())
    entry = f"[{ts}] {msg}"
    print(entry, flush=True)
    logs_buffer.append(entry)
    if len(logs_buffer) > 120:
        del logs_buffer[:-120]


def update_firestore(progress_pct: int, milestone_text: str, status: str = "running", asset_url: str = None):
    """Pushes live percentage, milestone, logs, and scene storyboard state to Firestore REST API."""
    url = (
        f"https://firestore.googleapis.com/v1/projects/{FIRESTORE_PROJECT_ID}"
        f"/databases/(default)/documents/automations/{JOB_ID}"
    )
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fields = {
        "progress": {"integerValue": str(int(progress_pct))},
        "current_milestone": {"stringValue": milestone_text},
        "status": {"stringValue": status},
        "updated_at": {"stringValue": now_iso},
        "logs_json": {"stringValue": json.dumps(logs_buffer[-80:])},
        "scenes_json": {"stringValue": json.dumps(scenes_state)},
    }
    mask_fields = ["progress", "current_milestone", "status", "updated_at", "logs_json", "scenes_json"]

    if asset_url:
        fields["asset_url"] = {"stringValue": asset_url}
        fields["asset_type"] = {"stringValue": "video"}
        mask_fields.extend(["asset_url", "asset_type"])

    update_mask = "&".join(f"updateMask.fieldPaths={f}" for f in mask_fields)
    try:
        requests.patch(f"{url}?{update_mask}", json={"fields": fields}, timeout=8)
    except Exception as e:
        print(f"[Firestore Sync Warning] {e}", flush=True)


def cancellation_watchdog():
    """Polls Firestore every 3 seconds to abort immediately if the user clicks Cancel."""
    url = (
        f"https://firestore.googleapis.com/v1/projects/{FIRESTORE_PROJECT_ID}"
        f"/databases/(default)/documents/automations/{JOB_ID}"
    )
    while not cancel_event.is_set():
        try:
            resp = requests.get(url, timeout=6)
            if resp.status_code == 200:
                doc_fields = resp.json().get("fields", {})
                cancel_req = doc_fields.get("cancel_requested", {}).get("booleanValue", False)
                if cancel_req:
                    append_log("[Cancel] Cancel signal received from user! Terminating all processes immediately...")
                    cancel_event.set()
                    for proc in list(active_subprocesses):
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    update_firestore(0, "Execution cancelled by user.", status="cancelled")
                    os._exit(0)
        except Exception:
            pass
        time.sleep(3)


def check_cancel():
    if cancel_event.is_set():
        sys.exit(0)


# =====================================================================
# 4. STAGE 1: NVIDIA NIM SCENE PLANNING ON KAGGLE SERVER (SSE STREAMING + FALLBACK)
# =====================================================================
def call_nvidia_nim_streaming(model_id: str, system_prompt: str, user_prompt: str) -> str:
    """Streams tokens from NVIDIA NIM so reasoning models (like z-ai/glm-5.3, deepseek-r1) never hit a read timeout."""
    check_cancel()
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.35,
        "max_tokens": 8192,
        "stream": True,
    }

    content_chunks = []
    reasoning_chars = 0
    last_report_time = time.time()

    with requests.post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        headers=headers,
        json=payload,
        stream=True,
        timeout=(25, 90),
    ) as resp:
        if resp.status_code != 200:
            err_body = resp.text[:400]
            raise RuntimeError(f"NVIDIA NIM HTTP {resp.status_code} on {model_id}: {err_body}")

        for raw_line in resp.iter_lines(decode_unicode=True):
            check_cancel()
            if not raw_line:
                continue
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk_json = json.loads(data_str)
                choices = chunk_json.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                r_piece = delta.get("reasoning_content") or ""
                c_piece = delta.get("content") or ""
                if r_piece:
                    reasoning_chars += len(r_piece)
                if c_piece:
                    content_chunks.append(c_piece)

                now = time.time()
                if now - last_report_time >= 12:
                    last_report_time = now
                    total_c = sum(len(x) for x in content_chunks)
                    append_log(
                        f"[Stage 1] {model_id} streaming... (reasoning: {reasoning_chars} chars, output: {total_c} chars)"
                    )
                    update_firestore(
                        12,
                        f"Stage 1/4: {model_id} streaming scene plan ({total_c} chars generated)...",
                    )
            except Exception:
                continue

    return "".join(content_chunks).strip()


def plan_scenes_with_nvidia(story: str, ref_tags: list, duration: int, aspect_ratio: str) -> list:
    """Uses the user's NVIDIA API Key and chosen NVIDIA model on Kaggle to plan scenes, with automatic fallback."""
    append_log(f"[Stage 1] Planning story scenes on Kaggle via NVIDIA NIM ({NVIDIA_MODEL})...")
    update_firestore(8, f"Stage 1/4: Planning scenes with NVIDIA NIM ({NVIDIA_MODEL})...")

    tag_names = [f"@{t['tag'].lstrip('@')}" for t in ref_tags if t.get("tag")]
    tag_list_str = ", ".join(tag_names) if tag_names else "None provided"

    system_prompt = f"""You are an elite Hollywood Storyboard Director and AI Cinematographer for the "Story to Film" engine.
Your job is to read a user's story and split it into sequential, visually consistent cinematic scenes.

CRITICAL RULES:
1. Each scene MUST fit a {duration}-second duration -- one clear action or emotional moment per scene.
2. Uploaded Reference Tags available: {tag_list_str}.
   - Whenever ANY uploaded character, location, or prop appears in a scene, you MUST reference it using its exact @tag (e.g., {', '.join(tag_names[:3]) if tag_names else '@Hero'}).
   - ONLY use @tags from the provided list ({tag_list_str}). NEVER invent new @tags that were not uploaded.
   - Keep characters visually consistent by ALWAYS calling them by their @tag, never re-describing their physical identity differently.
3. Frame all prompts as cinematic shots using mostly:
   - "Medium wide-angle shot" for establishing views
   - "Medium shot" for conversations and dialogue
   - "Close-up shot" for emphasis and emotion
   Keep prompts simple, with one clear subject focus, clear lighting, and clear camera/subject motion.
4. STRICT CONTENT SAFETY (ZERO MODERATION FLAGS):
   - NEVER use words that trigger AI image/video safety filters: NO blood, gore, murder, kill, dead, corpse, gun, rifle, pistol, shoot, knife, blade, weapon, explosion, bomb, suicide, self-harm, nude, naked, sexy, sensual, NSFW, abuse, torture, drugs, child/kid in peril, or real celebrity/politician names.
   - Always translate dramatic tension into safe, family-friendly, PG-rated visual cinema (e.g., intense gazes, dramatic shadows, glowing energy, sweeping camera movement).

Return ONLY a valid JSON array of scene objects (no markdown explanation outside JSON) with this exact schema:
[
  {{
    "scene_number": 1,
    "title": "Short 2-4 Word Title",
    "image_prompt": "Medium wide-angle shot of @Tag standing in ... clear cinematic lighting...",
    "video_prompt": "Slow dolly-in camera movement as @Tag turns forward with a determined expression, soft ambient wind...",
    "tags_used": ["@Tag"]
  }}
]"""

    user_prompt = f"""Story / Script:
\"\"\"
{story}
\"\"\"

Target Aspect Ratio: {aspect_ratio}
Scene Duration: {duration} seconds per scene
Available Uploaded @Tags: {tag_list_str}

Output the JSON array of planned scenes now (be concise and output valid JSON immediately):"""

    candidate_models = [NVIDIA_MODEL]
    for fb in ("meta/llama-3.3-70b-instruct", "deepseek-ai/deepseek-v3.1", "qwen/qwen2.5-72b-instruct", "meta/llama-3.1-70b-instruct"):
        if fb not in candidate_models:
            candidate_models.append(fb)

    raw_scenes = None
    last_err = None
    used_model = NVIDIA_MODEL

    for model_try in candidate_models:
        check_cancel()
        try:
            if model_try != NVIDIA_MODEL:
                append_log(f"[Stage 1 Fallback] Retrying scene planning with fast model '{model_try}'...")
                update_firestore(10, f"Stage 1/4: Retrying scene planning with {model_try}...")

            content = call_nvidia_nim_streaming(model_try, system_prompt, user_prompt)
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

            match = re.search(r"\[.*\]", content, flags=re.DOTALL)
            if not match:
                raise RuntimeError(f"Model {model_try} did not return a JSON array. Output: {content[:240]}")

            parsed = json.loads(match.group(0))
            if isinstance(parsed, list) and len(parsed) > 0:
                raw_scenes = parsed
                used_model = model_try
                break
        except Exception as e:
            last_err = e
            append_log(f"[Stage 1 Notice] {model_try} attempt issue: {e}")

    if not raw_scenes:
        raise RuntimeError(f"Scene planning failed across models. Last error: {last_err}")

    valid_tag_lookup = {f"@{t['tag'].lstrip('@')}".lower(): f"@{t['tag'].lstrip('@')}" for t in ref_tags if t.get("tag")}
    bare_tag_lookup = {t['tag'].lstrip('@').lower(): f"@{t['tag'].lstrip('@')}" for t in ref_tags if t.get("tag")}

    planned = []
    for idx, sc in enumerate(raw_scenes, start=1):
        img_p = sanitize_prompt_for_generation(sc.get("image_prompt", ""))
        vid_p = sanitize_prompt_for_generation(sc.get("video_prompt", ""))
        title = re.sub(r"[^a-zA-Z0-9 _-]", "", sc.get("title", f"Scene {idx}")).strip() or f"Scene {idx}"

        detected_tags = []
        raw_tags = sc.get("tags_used", [])
        if isinstance(raw_tags, list):
            for rt in raw_tags:
                norm = f"@{str(rt).lstrip('@')}".lower()
                if norm in valid_tag_lookup and valid_tag_lookup[norm] not in detected_tags:
                    detected_tags.append(valid_tag_lookup[norm])

        combined_lower = (img_p + " " + vid_p).lower()
        for bare_low, canonical_tag in bare_tag_lookup.items():
            if re.search(rf"@?{re.escape(bare_low)}\b", combined_lower):
                if canonical_tag not in detected_tags:
                    detected_tags.append(canonical_tag)

        planned.append({
            "scene_number": idx,
            "title": title,
            "image_prompt": img_p,
            "video_prompt": vid_p,
            "tags_used": detected_tags,
            "image_status": "pending",
            "image_url": "",
            "video_status": "pending",
            "video_url": "",
            "download_filename": f"{idx}.Scene {idx} - {title}.mp4",
            "error": "",
        })

    append_log(f"[Stage 1 Complete] Planned {len(planned)} scenes ({len(planned) * duration}s total runtime) via {used_model}.")
    return planned


# =====================================================================
# 5. KIE.AI UNIFIED TASK CREATION & POLLING ENGINE
# =====================================================================
def resolve_tag_urls_and_prompt(prompt: str, tags_used: list, ref_tags: list):
    """Maps @tags to uploaded reference image URLs and formats prompt cleanly."""
    tag_map = {f"@{t['tag'].lstrip('@')}".lower(): t["url"] for t in ref_tags if t.get("tag") and t.get("url")}
    urls = []
    resolved_prompt = prompt

    for tag in tags_used:
        key = f"@{tag.lstrip('@')}".lower()
        if key in tag_map and tag_map[key] not in urls:
            urls.append(tag_map[key])
            ref_idx = len(urls)
            clean_name = tag.lstrip("@")
            resolved_prompt = re.sub(
                rf"@{re.escape(clean_name)}\b",
                f"{clean_name} (matching reference image {ref_idx})",
                resolved_prompt,
                flags=re.IGNORECASE,
            )

    return sanitize_prompt_for_generation(resolved_prompt), urls


def kie_create_and_poll(model_id: str, input_payload: dict, task_label: str, timeout_sec: int = 420) -> str:
    """Creates a task on Kie.ai (`POST /api/v1/jobs/createTask`) and polls `recordInfo` until completion."""
    check_cancel()
    create_url = "https://api.kie.ai/api/v1/jobs/createTask"
    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model_id,
        "input": input_payload,
    }

    append_log(f"[Kie.ai] Dispatching {task_label} to [{model_id}]...")
    resp = requests.post(create_url, headers=headers, json=body, timeout=30)
    data = resp.json() if resp.content else {}

    if resp.status_code != 200 or data.get("code") != 200:
        err_msg = data.get("msg") or resp.text[:300]
        raise RuntimeError(f"Kie.ai createTask failed for {model_id}: {err_msg}")

    task_id = (data.get("data") or {}).get("taskId")
    if not task_id:
        raise RuntimeError(f"Kie.ai did not return taskId: {data}")

    append_log(f"[Kie.ai] Polling task {task_id} for {task_label}...")
    poll_url = f"https://api.kie.ai/api/v1/jobs/recordInfo?taskId={urllib.parse.quote(str(task_id))}"
    start_t = time.time()

    while time.time() - start_t < timeout_sec:
        check_cancel()
        time.sleep(5)
        try:
            p_resp = requests.get(poll_url, headers=headers, timeout=20)
            if p_resp.status_code != 200:
                continue
            p_json = p_resp.json()
            t_data = p_json.get("data") or {}
            state = str(t_data.get("state") or t_data.get("status") or "").lower()

            if state in ("success", "completed", "done"):
                res_json_str = t_data.get("resultJson")
                if isinstance(res_json_str, str) and res_json_str.strip():
                    parsed_res = json.loads(res_json_str)
                elif isinstance(res_json_str, dict):
                    parsed_res = res_json_str
                else:
                    parsed_res = t_data

                result_urls = (
                    parsed_res.get("resultUrls")
                    or parsed_res.get("video_urls")
                    or parsed_res.get("image_urls")
                    or parsed_res.get("urls")
                    or []
                )
                if isinstance(result_urls, list) and len(result_urls) > 0:
                    return result_urls[0]
                if parsed_res.get("url"):
                    return parsed_res["url"]
                raise RuntimeError(f"Task succeeded but no URL found in resultJson: {res_json_str}")

            if state in ("fail", "failed", "error", "cancelled", "canceled"):
                fail_msg = t_data.get("failMsg") or t_data.get("error") or "Unknown Kie.ai failure"
                raise RuntimeError(f"Kie.ai task {task_id} failed: {fail_msg}")

        except RuntimeError:
            raise
        except Exception as poll_err:
            print(f"[Poll retry] {poll_err}", flush=True)

    raise RuntimeError(f"Kie.ai task {task_id} timed out after {timeout_sec}s.")


def build_kie_image_input(model_id: str, prompt: str, ref_urls: list, aspect_ratio: str, resolution: str) -> dict:
    """Builds the exact model-specific `input` payload for Kie.ai Image Generation."""
    m = model_id.lower()
    if "nano-banana" in m:
        inp = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution or "1K",
            "output_format": "png",
        }
        if ref_urls:
            inp["image_input"] = ref_urls[:8]
            inp["image_urls"] = ref_urls[:8]
        return inp

    if "seedream" in m:
        inp = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution or "1K",
        }
        if ref_urls:
            inp["image_urls"] = ref_urls[:6]
            inp["image_input"] = ref_urls[:6]
        return inp

    if "flux" in m:
        inp = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
        }
        if ref_urls:
            inp["input_image"] = ref_urls[0]
            inp["image_urls"] = ref_urls[:4]
        return inp

    inp = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
    }
    if ref_urls:
        inp["image_urls"] = ref_urls[:4]
        inp["image_input"] = ref_urls[:4]
    return inp


def build_kie_video_input(
    model_id: str,
    prompt: str,
    scene_image_url: str,
    ref_urls: list,
    aspect_ratio: str,
    duration: int,
    resolution: str,
    mode: str,
) -> dict:
    """Builds the exact model-specific `input` payload for Kie.ai Video Generation."""
    m = model_id.lower()
    dur_str = str(duration)
    api_res = "480p" if resolution == "360p" else (resolution or "720p")

    if "grok-imagine" in m:
        all_imgs = [scene_image_url] + [u for u in ref_urls if u != scene_image_url]
        return {
            "prompt": prompt,
            "image_urls": all_imgs[:1],
            "duration": dur_str if dur_str in ("6", "10") else "6",
            "resolution": api_res if api_res in ("480p", "720p") else "720p",
            "aspect_ratio": aspect_ratio,
            "mode": mode if mode in ("normal", "fun") else "normal",
        }

    if "seedance" in m:
        all_refs = [scene_image_url] + [u for u in ref_urls if u != scene_image_url]
        return {
            "prompt": prompt,
            "image_url": scene_image_url,
            "reference_image_urls": all_refs[:4],
            "resolution": api_res if api_res in ("480p", "720p", "1080p") else "720p",
            "duration": dur_str,
            "aspect_ratio": aspect_ratio,
        }

    if "wan" in m:
        return {
            "prompt": prompt,
            "image_url": scene_image_url,
            "first_frame_url": scene_image_url,
            "duration": dur_str if dur_str in ("5", "10") else "5",
            "resolution": api_res if api_res in ("480p", "720p", "1080p") else "720p",
            "aspect_ratio": aspect_ratio,
            "enable_prompt_expansion": True,
        }

    if "kling" in m:
        return {
            "prompt": prompt,
            "image_url": scene_image_url,
            "image_urls": [scene_image_url],
            "duration": dur_str if dur_str in ("5", "10") else "5",
            "aspect_ratio": aspect_ratio,
        }

    if "veo" in m:
        return {
            "prompt": prompt,
            "generation_mode": "FIRST_AND_LAST_FRAMES_2_VIDEO",
            "image_urls": [scene_image_url],
            "aspect_ratio": aspect_ratio,
        }

    if "runway" in m:
        return {
            "prompt": prompt,
            "image_url": scene_image_url,
            "aspect_ratio": aspect_ratio,
            "duration": dur_str if dur_str in ("5", "10") else "5",
            "quality": "720p" if dur_str == "10" else (api_res if api_res in ("720p", "1080p") else "720p"),
        }

    return {
        "prompt": prompt,
        "image_url": scene_image_url,
        "image_urls": [scene_image_url],
        "aspect_ratio": aspect_ratio,
        "duration": dur_str,
    }


# =====================================================================
# 6. DOWNLOAD, HUGGING FACE UPLOAD & FFMPEG FILM STITCHER
# =====================================================================
def download_binary(url: str, local_path: str):
    check_cancel()
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)


def upload_to_hf(api: HfApi, local_path: str, remote_path: str) -> str:
    check_cancel()
    api.upload_file(
        path_or_fileobj=local_path,
        path_in_repo=remote_path,
        repo_id=HF_DATASET_REPO,
        repo_type="dataset",
    )
    quoted_remote = "/".join(urllib.parse.quote(part) for part in remote_path.split("/"))
    return f"https://huggingface.co/datasets/{HF_DATASET_REPO}/resolve/main/{quoted_remote}"


def clip_has_audio(video_path: str) -> bool:
    """Checks via ffprobe whether a video file contains an audio stream."""
    try:
        res = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                video_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
        return b"audio" in (res.stdout or b"").lower()
    except Exception:
        return True


def stitch_videos_ffmpeg(video_paths: list, output_path: str, aspect_ratio: str, quality: str):
    """Normalizes all scene clips to identical resolution/fps/audio (preserving voices & sound) and stitches them into a single coherent movie."""
    check_cancel()
    if len(video_paths) == 1:
        shutil.copyfile(video_paths[0], output_path)
        return

    height_map = {"360p": 360, "480p": 480, "720p": 720, "1080p": 1080}
    h = height_map.get(quality, 720)
    if aspect_ratio == "9:16":
        target_w, target_h = h, int(round(h * 16 / 9 / 2) * 2)
    elif aspect_ratio == "1:1":
        target_w, target_h = h, h
    else:
        target_w, target_h = int(round(h * 16 / 9 / 2) * 2), h

    norm_dir = os.path.dirname(output_path)
    norm_files = []

    for i, vp in enumerate(video_paths):
        check_cancel()
        norm_p = os.path.join(norm_dir, f"_norm_scene_{i:03d}.mp4")
        vf = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black,fps=30,format=yuv420p"
        )
        has_audio = clip_has_audio(vp)
        if has_audio:
            cmd = [
                "ffmpeg", "-y",
                "-i", vp,
                "-vf", vf,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "20",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
                norm_p,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", vp,
                "-f", "lavfi",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-vf", vf,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "20",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
                "-shortest",
                norm_p,
            ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        active_subprocesses.append(proc)
        _, stderr = proc.communicate()
        if proc in active_subprocesses:
            active_subprocesses.remove(proc)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg normalization failed on clip {i+1}: {stderr.decode(errors='replace')[-300:]}")
        norm_files.append(norm_p)

    concat_list_path = os.path.join(norm_dir, "concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for nf in norm_files:
            escaped = nf.replace("\\", "/")
            f.write(f"file '{escaped}'\n")

    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-ac", "2",
        "-movflags", "+faststart",
        output_path,
    ]
    proc = subprocess.Popen(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    active_subprocesses.append(proc)
    _, stderr = proc.communicate()
    if proc in active_subprocesses:
        active_subprocesses.remove(proc)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {stderr.decode(errors='replace')[-300:]}")


# =====================================================================
# 7. MAIN EXECUTION ORCHESTRATOR
# =====================================================================
def main():
    global scenes_state
    append_log(f"[Init] Starting Story to Film Kaggle T4 Pipeline for Job: {JOB_ID}")

    watchdog = threading.Thread(target=cancellation_watchdog, daemon=True)
    watchdog.start()

    try:
        check_cancel()
        if not NVIDIA_API_KEY:
            raise RuntimeError("Missing NVIDIA API Key. Please add your NVIDIA API key in the Settings tab.")
        if not KIE_API_KEY:
            raise RuntimeError("Missing Kie.ai API Key. Please add your Kie.ai API key in the Settings tab.")
        if not HF_TOKEN:
            raise RuntimeError("Missing Hugging Face Token. Please add your Hugging Face token in the Settings tab.")

        update_firestore(4, f"Verifying / auto-creating Hugging Face Dataset ({HF_DATASET_REPO})...")
        append_log(f"[HF] Ensuring Hugging Face Dataset '{HF_DATASET_REPO}' exists...")
        hf_api = HfApi(token=HF_TOKEN)
        hf_api.create_repo(repo_id=HF_DATASET_REPO, repo_type="dataset", private=False, exist_ok=True)
        append_log(f"[HF] Hugging Face Dataset '{HF_DATASET_REPO}' ready.")

        work_dir = os.path.abspath(f"./work_{JOB_ID}")
        os.makedirs(work_dir, exist_ok=True)

        if RETRY_SCENES_ONLY and EXISTING_SCENES:
            scenes_state = EXISTING_SCENES
            append_log(f"[Retry] Inspecting {len(scenes_state)} existing scenes...")
        else:
            scenes_state = plan_scenes_with_nvidia(
                story=STORY_TEXT,
                ref_tags=REFERENCE_TAGS,
                duration=SCENE_DURATION,
                aspect_ratio=ASPECT_RATIO,
            )
            update_firestore(
                18,
                f"Planned {len(scenes_state)} scenes ({len(scenes_state) * SCENE_DURATION}s total). Starting image generation...",
            )

        total_scenes = max(len(scenes_state), 1)

        # Stage 2: Reference-Consistent Image Generation (18% -> 50%)
        for idx, scene in enumerate(scenes_state):
            check_cancel()
            sc_num = scene["scene_number"]
            if scene.get("image_status") == "done" and scene.get("image_url"):
                append_log(f"[Stage 2] Scene {sc_num} image already complete, skipping.")
                continue

            pct = 18 + int((idx / total_scenes) * 32)
            scene["image_status"] = "generating"
            scene["error"] = ""
            update_firestore(
                pct,
                f"Stage 2/4: Generating starting image for Scene {sc_num}/{total_scenes} ({scene['title']}) via {IMAGE_MODEL}...",
            )

            try:
                resolved_img_prompt, ref_urls = resolve_tag_urls_and_prompt(
                    scene["image_prompt"], scene.get("tags_used", []), REFERENCE_TAGS
                )
                img_input = build_kie_image_input(
                    model_id=IMAGE_MODEL,
                    prompt=resolved_img_prompt,
                    ref_urls=ref_urls,
                    aspect_ratio=ASPECT_RATIO,
                    resolution=IMAGE_RESOLUTION,
                )
                kie_img_url = kie_create_and_poll(
                    model_id=IMAGE_MODEL,
                    input_payload=img_input,
                    task_label=f"Scene {sc_num} Image",
                    timeout_sec=300,
                )

                local_img = os.path.join(work_dir, f"scene_{sc_num:02d}.png")
                download_binary(kie_img_url, local_img)
                hf_img_url = upload_to_hf(
                    hf_api, local_img, f"jobs/{JOB_ID}/images/scene_{sc_num:02d}.png"
                )

                scene["image_url"] = hf_img_url
                scene["image_status"] = "done"
                append_log(f"[Stage 2] Scene {sc_num} image ready: {hf_img_url}")
                update_firestore(pct + 2, f"Scene {sc_num}/{total_scenes} starting frame complete.")
            except Exception as img_err:
                scene["image_status"] = "failed"
                scene["error"] = str(img_err)
                append_log(f"[Stage 2 Warning] Scene {sc_num} image failed: {img_err}")
                update_firestore(pct, f"Scene {sc_num} image failed, continuing remaining scenes...")

        # Stage 3: Sequential Video Generation (50% -> 86%)
        local_scene_videos = []
        for idx, scene in enumerate(scenes_state):
            check_cancel()
            sc_num = scene["scene_number"]
            dl_name = scene.get("download_filename") or f"{sc_num}.Scene {sc_num} - {scene['title']}.mp4"
            local_vid = os.path.join(work_dir, f"scene_{sc_num:02d}.mp4")

            if scene.get("video_status") == "done" and scene.get("video_url"):
                try:
                    download_binary(scene["video_url"], local_vid)
                    local_scene_videos.append(local_vid)
                    continue
                except Exception:
                    pass

            if scene.get("image_status") != "done" or not scene.get("image_url"):
                scene["video_status"] = "failed"
                scene["error"] = scene.get("error") or "Skipped video because starting image failed."
                continue

            pct = 50 + int((idx / total_scenes) * 35)
            scene["video_status"] = "generating"
            update_firestore(
                pct,
                f"Stage 3/4: Animating Scene {sc_num}/{total_scenes} ({scene['title']}) via {VIDEO_MODEL}...",
            )

            try:
                resolved_vid_prompt, ref_urls = resolve_tag_urls_and_prompt(
                    scene["video_prompt"], scene.get("tags_used", []), REFERENCE_TAGS
                )
                vid_input = build_kie_video_input(
                    model_id=VIDEO_MODEL,
                    prompt=resolved_vid_prompt,
                    scene_image_url=scene["image_url"],
                    ref_urls=ref_urls,
                    aspect_ratio=ASPECT_RATIO,
                    duration=SCENE_DURATION,
                    resolution=VIDEO_QUALITY,
                    mode=VIDEO_MODE,
                )
                kie_vid_url = kie_create_and_poll(
                    model_id=VIDEO_MODEL,
                    input_payload=vid_input,
                    task_label=f"Scene {sc_num} Video",
                    timeout_sec=600,
                )

                download_binary(kie_vid_url, local_vid)
                hf_vid_url = upload_to_hf(
                    hf_api, local_vid, f"jobs/{JOB_ID}/scenes/{dl_name}"
                )

                scene["video_url"] = hf_vid_url
                scene["video_status"] = "done"
                local_scene_videos.append(local_vid)
                append_log(f"[Stage 3] Scene {sc_num} video ready ({dl_name}): {hf_vid_url}")
                update_firestore(pct + 3, f"Scene {sc_num}/{total_scenes} video finished & ready for download.")
            except Exception as vid_err:
                scene["video_status"] = "failed"
                scene["error"] = str(vid_err)
                append_log(f"[Stage 3 Warning] Scene {sc_num} video failed: {vid_err}")
                update_firestore(pct, f"Scene {sc_num} video failed, continuing remaining scenes...")

        # Stage 4: Stitch All Succeeded Scene Videos into Coherent Final Film (86% -> 100%)
        check_cancel()
        if not local_scene_videos:
            raise RuntimeError("No scene videos succeeded; cannot stitch final film. Check scene errors and retry.")

        update_firestore(88, f"Stage 4/4: Stitching {len(local_scene_videos)} scenes into a coherent film with FFmpeg...")
        append_log(f"[Stage 4] Stitching {len(local_scene_videos)} scene clips with FFmpeg on Kaggle T4...")

        final_film_local = os.path.join(work_dir, "Complete_Story_Film.mp4")
        stitch_videos_ffmpeg(
            video_paths=local_scene_videos,
            output_path=final_film_local,
            aspect_ratio=ASPECT_RATIO,
            quality=VIDEO_QUALITY,
        )

        update_firestore(95, "Uploading stitched master film to Hugging Face Datasets...")
        append_log(f"[HF] Uploading stitched master film to {HF_DATASET_REPO}...")
        final_hf_url = upload_to_hf(
            hf_api,
            final_film_local,
            f"jobs/{JOB_ID}/Complete_Story_Film.mp4",
        )

        succeeded_count = sum(1 for s in scenes_state if s.get("video_status") == "done")
        failed_count = len(scenes_state) - succeeded_count
        summary_msg = (
            f"Film complete! {succeeded_count}/{len(scenes_state)} scenes stitched into final movie."
            if failed_count == 0
            else f"Film stitched ({succeeded_count}/{len(scenes_state)} scenes succeeded, {failed_count} failed -- retry available)."
        )
        append_log(f"[Complete] {summary_msg} Master URL: {final_hf_url}")
        update_firestore(100, summary_msg, status="completed", asset_url=final_hf_url)

    except Exception as e:
        err_str = str(e)
        append_log(f"[Pipeline Error] {err_str}")
        update_firestore(0, f"Error: {err_str[:240]}", status="failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
