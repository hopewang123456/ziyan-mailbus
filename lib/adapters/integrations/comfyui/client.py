"""ComfyUI HTTP 客户端 — mailbus 接入层（不 patch ComfyUI 源码）。"""

from __future__ import annotations

from lib.adapters.clock import now_dt, now_ts, now_utc_dt
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple


def _base_url() -> str:
    from .url_resolve import resolve_comfyui_base_url

    return resolve_comfyui_base_url()


def health_check(base_url: str | None = None) -> Tuple[bool, dict]:
    url = f"{(base_url or _base_url())}/system_stats"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return True, body
    except Exception as exc:
        return False, {"error": str(exc)}


def _build_sd15_workflow(
    *,
    prompt: str,
    negative: str,
    ckpt: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
) -> dict:
    """最小 SD1.5 txt2img API workflow（8GB 友好）。"""
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "mailbus", "images": ["8", 0]},
        },
    }


def _build_sd15_img2img_workflow(
    *,
    prompt: str,
    negative: str,
    ckpt: str,
    image_name: str,
    steps: int,
    cfg: float,
    seed: int,
    denoise: float,
) -> dict:
    """SD1.5 img2img — 基于参考图微调表情/眨眼，保持同一人。"""
    return {
        "10": {
            "class_type": "LoadImage",
            "inputs": {"image": image_name},
        },
        "11": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["10", 0], "vae": ["4", 2]},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": denoise,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["11", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "mailbus", "images": ["8", 0]},
        },
    }


def _build_sd15_inpaint_workflow(
    *,
    prompt: str,
    negative: str,
    ckpt: str,
    image_name: str,
    mask_name: str,
    steps: int,
    cfg: float,
    seed: int,
    denoise: float,
) -> dict:
    """SD1.5 局部 inpaint — 仅重绘 mask 区域（用于眼部眨眼）。"""
    return {
        "10": {
            "class_type": "LoadImage",
            "inputs": {"image": image_name},
        },
        "12": {
            "class_type": "LoadImage",
            "inputs": {"image": mask_name},
        },
        "13": {
            "class_type": "ImageToMask",
            "inputs": {"image": ["12", 0], "channel": "red"},
        },
        "11": {
            "class_type": "VAEEncodeForInpaint",
            "inputs": {
                "pixels": ["10", 0],
                "vae": ["4", 2],
                "mask": ["13", 0],
                "grow_mask_by": 8,
            },
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": denoise,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["11", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "mailbus", "images": ["8", 0]},
        },
    }


def upload_image(local_path: str, *, base_url: str | None = None) -> dict:
    """上传本地图片到 ComfyUI input 目录，供 LoadImage 使用。"""
    base = (base_url or _base_url()).rstrip("/")
    if not os.path.isfile(local_path):
        return {"ok": False, "error": "file_not_found", "path": local_path}
    filename = os.path.basename(local_path)
    boundary = f"----mailbus{uuid.uuid4().hex}"
    with open(local_path, "rb") as f:
        raw = f.read()
    parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        raw,
        f"\r\n--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="type"\r\n\r\n',
        b"input\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    req = urllib.request.Request(
        f"{base}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        name = data.get("name") or filename
        return {"ok": True, "name": name, "subfolder": data.get("subfolder") or "", "type": data.get("type") or "input"}
    except Exception as exc:
        return {"ok": False, "error": "upload_failed", "message": str(exc)}


def _post_json(url: str, payload: dict, *, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _run_workflow(workflow: dict, *, base: str, timeout: int, seed: int, ckpt: str) -> dict:
    client_id = str(uuid.uuid4())
    try:
        sub = _post_json(
            f"{base}/prompt",
            {"prompt": workflow, "client_id": client_id},
            timeout=120,
        )
    except Exception as exc:
        return {"ok": False, "error": "submit_failed", "message": str(exc)}

    if sub.get("node_errors"):
        return {"ok": False, "error": "validation_failed", "node_errors": sub["node_errors"]}
    prompt_id = sub.get("prompt_id")
    if not prompt_id:
        return {"ok": False, "error": "no_prompt_id", "response": sub}

    polled = _poll_history(base, prompt_id, timeout=timeout)
    if not polled.get("ok"):
        return {"ok": False, "error": polled.get("error"), "prompt_id": prompt_id, **polled}

    images: List[dict] = []
    for node_out in (polled.get("outputs") or {}).values():
        if not isinstance(node_out, dict):
            continue
        for img in node_out.get("images") or []:
            if isinstance(img, dict) and img.get("filename"):
                images.append({
                    "filename": img["filename"],
                    "subfolder": img.get("subfolder") or "",
                    "type": img.get("type") or "output",
                    "view_url": (
                        f"{base}/view?filename={img['filename']}"
                        f"&subfolder={img.get('subfolder') or ''}&type={img.get('type') or 'output'}"
                    ),
                })

    return {
        "ok": bool(images),
        "provider": "comfyui",
        "prompt_id": prompt_id,
        "checkpoint": ckpt,
        "images": images,
        "seed": seed,
    }


def _get_json(url: str, *, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _poll_history(base: str, prompt_id: str, *, timeout: int = 300) -> dict:
    deadline = now_ts() + timeout
    last_err: str | None = None
    while now_ts() < deadline:
        try:
            hist = _get_json(f"{base}/history/{prompt_id}", timeout=30)
            entry = hist.get(prompt_id) if isinstance(hist, dict) else None
            if isinstance(entry, dict):
                st = entry.get("status") or {}
                if st.get("status_str") == "error":
                    return {"ok": False, "error": "comfy_execution_error", "details": entry}
                if st.get("completed"):
                    return {"ok": True, "outputs": entry.get("outputs") or {}}
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last_err = str(exc)
            time.sleep(2.5)
            continue
        time.sleep(1.5)
    return {"ok": False, "error": "timeout", "message": last_err}


def generate_txt2img(
    inputs: dict,
    *,
    base_url: str | None = None,
    timeout: int = 300,
) -> dict:
    """提交 SD1.5 生图并返回输出文件信息。"""
    base = (base_url or _base_url()).rstrip("/")
    ok, health = health_check(base)
    if not ok:
        return {"ok": False, "error": "comfy_unreachable", "details": health}

    prompt = (
        inputs.get("prompt")
        or inputs.get("intent")
        or inputs.get("topic")
        or "high quality illustration"
    )
    negative = inputs.get("negative") or "low quality, blurry, watermark, text"
    ckpt = os.environ.get("COMFYUI_CHECKPOINT") or inputs.get("checkpoint") or ""
    if not ckpt:
        ckpt = _pick_checkpoint(base)
    if not ckpt:
        return {
            "ok": False,
            "error": "no_checkpoint",
            "message": "无可用 checkpoint；运行 tools/ensure-comfyui.py --download-model",
        }

    width = int(inputs.get("width") or 512)
    height = int(inputs.get("height") or 512)
    steps = int(inputs.get("steps") or 20)
    cfg = float(inputs.get("cfg") or 7.0)
    seed = int(inputs.get("seed") or (abs(hash(prompt)) % (2**31)))

    workflow = _build_sd15_workflow(
        prompt=str(prompt)[:2000],
        negative=str(negative)[:500],
        ckpt=ckpt,
        width=min(width, 768),
        height=min(height, 768),
        steps=min(steps, 30),
        cfg=cfg,
        seed=seed,
    )
    return _run_workflow(workflow, base=base, timeout=timeout, seed=seed, ckpt=ckpt)


def generate_img2img(
    inputs: dict,
    *,
    reference_path: str,
    base_url: str | None = None,
    timeout: int = 300,
) -> dict:
    """基于参考肖像 img2img — 用于眨眼/微表情帧（人物动，不是整图动）。"""
    base = (base_url or _base_url()).rstrip("/")
    ok, health = health_check(base)
    if not ok:
        return {"ok": False, "error": "comfy_unreachable", "details": health}

    uploaded = upload_image(reference_path, base_url=base)
    if not uploaded.get("ok"):
        return uploaded

    prompt = (
        inputs.get("prompt")
        or inputs.get("intent")
        or "same person, photorealistic portrait"
    )
    negative = inputs.get("negative") or (
        "different person, face change, head turn, camera move, zoom, pan, "
        "low quality, blurry, watermark, text, deformed eyes"
    )
    ckpt = os.environ.get("COMFYUI_CHECKPOINT") or inputs.get("checkpoint") or ""
    if not ckpt:
        ckpt = _pick_checkpoint(base)
    if not ckpt:
        return {
            "ok": False,
            "error": "no_checkpoint",
            "message": "无可用 checkpoint",
        }

    steps = int(inputs.get("steps") or 18)
    cfg = float(inputs.get("cfg") or 6.5)
    seed = int(inputs.get("seed") or (abs(hash(prompt)) % (2**31)))
    denoise = float(inputs.get("denoise") or 0.32)
    max_denoise = float(inputs.get("max_denoise") or 0.70)
    denoise = max(0.12, min(denoise, max_denoise))

    workflow = _build_sd15_img2img_workflow(
        prompt=str(prompt)[:2000],
        negative=str(negative)[:500],
        ckpt=ckpt,
        image_name=uploaded["name"],
        steps=min(steps, 28),
        cfg=cfg,
        seed=seed,
        denoise=denoise,
    )
    out = _run_workflow(workflow, base=base, timeout=timeout, seed=seed, ckpt=ckpt)
    out["denoise"] = denoise
    out["reference"] = reference_path
    return out


def generate_inpaint(
    inputs: dict,
    *,
    reference_path: str,
    mask_path: str,
    base_url: str | None = None,
    timeout: int = 300,
) -> dict:
    """局部 inpaint — 仅 mask 白区重绘，用于眼部眨眼。"""
    base = (base_url or _base_url()).rstrip("/")
    ok, health = health_check(base)
    if not ok:
        return {"ok": False, "error": "comfy_unreachable", "details": health}

    uploaded = upload_image(reference_path, base_url=base)
    if not uploaded.get("ok"):
        return uploaded
    uploaded_mask = upload_image(mask_path, base_url=base)
    if not uploaded_mask.get("ok"):
        return uploaded_mask

    prompt = inputs.get("prompt") or "same person, photorealistic portrait"
    negative = inputs.get("negative") or "different person, deformed eyes, blurry"
    ckpt = os.environ.get("COMFYUI_CHECKPOINT") or inputs.get("checkpoint") or ""
    if not ckpt:
        ckpt = _pick_checkpoint(base)
    if not ckpt:
        return {"ok": False, "error": "no_checkpoint", "message": "无可用 checkpoint"}

    steps = int(inputs.get("steps") or 20)
    cfg = float(inputs.get("cfg") or 7.0)
    seed = int(inputs.get("seed") or (abs(hash(prompt)) % (2**31)))
    denoise = float(inputs.get("denoise") or 0.85)
    denoise = max(0.5, min(denoise, 0.98))

    workflow = _build_sd15_inpaint_workflow(
        prompt=str(prompt)[:2000],
        negative=str(negative)[:500],
        ckpt=ckpt,
        image_name=uploaded["name"],
        mask_name=uploaded_mask["name"],
        steps=min(steps, 28),
        cfg=cfg,
        seed=seed,
        denoise=denoise,
    )
    out = _run_workflow(workflow, base=base, timeout=timeout, seed=seed, ckpt=ckpt)
    out["denoise"] = denoise
    out["reference"] = reference_path
    out["mask"] = mask_path
    return out


def _pick_checkpoint(base: str) -> str:
    """从 /object_info CheckpointLoaderSimple 或环境变量选第一个 ckpt。"""
    env_list = os.environ.get("COMFYUI_CHECKPOINT_LIST", "")
    if env_list.strip():
        return env_list.split(",")[0].strip()
    try:
        info = _get_json(f"{base}/object_info/CheckpointLoaderSimple", timeout=15)
        choices = (
            (info.get("CheckpointLoaderSimple") or {})
            .get("input", {})
            .get("required", {})
            .get("ckpt_name", [[]])[0]
        )
        if isinstance(choices, list) and choices:
            for pref in ("v1-5", "sd1", "realistic", "dreamshaper", "anything"):
                for c in choices:
                    if pref in str(c).lower():
                        return str(c)
            return str(choices[0])
    except Exception:
        pass
    return ""
