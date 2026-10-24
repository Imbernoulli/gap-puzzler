"""Export actual policy execution media with exact source-time provenance.

RGB mode holds archived policy inputs until their next capture. Native mode
photographs saved body/joint states on an explicit CUDA renderer without any
physics steps. Neither mode interpolates motion or uses a CPU scene renderer.
"""
from __future__ import annotations

import argparse
import json
import inspect
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EPISODE = ROOT / (
    "runs/pyramid_full12_bimanual_layout_c_v13/workspace/runs/"
    "full12_original_order_layout_c_v10/episode"
)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def montage(episode: Path, index: int, record: dict) -> Image.Image:
    """Keep all four actual policy cameras visible without detection overlays."""
    width, panel_height, bar_height = 1024, 410, 36
    image = Image.new("RGB", (width, panel_height * 2 + bar_height), "#131719")
    font = ImageFont.truetype(FONT, 16)
    with np.load(episode / "rgb" / f"{index:04d}.npz") as cameras:
        for slot, key in enumerate(("top", "front", "rear", "side")):
            panel = Image.fromarray(cameras[key]).resize(
                (width // 2, panel_height), Image.Resampling.LANCZOS
            )
            draw = ImageDraw.Draw(panel)
            draw.rounded_rectangle((10, 10, 80, 34), radius=4, fill="#15191ddd")
            draw.text((18, 13), key.upper(), font=font, fill="#f0f3f3")
            image.paste(panel, ((slot % 2) * width // 2, (slot // 2) * panel_height))
    draw = ImageDraw.Draw(image)
    draw.text(
        (14, panel_height * 2 + 9),
        f"Recorded policy RGB · observation {index + 1:03d} · sim {record['timestamp']:.2f} s",
        font=font,
        fill="#e8eded",
    )
    return image


def render(episode: Path, output: Path, manifest_path: Path, speed: float, fps: int) -> dict:
    records = json.loads((episode / "rgb/observations.json").read_text())
    if not records:
        raise ValueError("No archived policy observations")
    # A live recorder may atomically publish a JSON record just before its NPZ.
    for index in range(len(records)):
        if not (episode / "rgb" / f"{index:04d}.npz").is_file():
            records = records[:index]
            break
    if not records:
        raise ValueError("No complete archived RGB captures")
    times = [float(record["timestamp"]) for record in records]
    if not all(math.isfinite(t) for t in times) or any(b < a for a, b in zip(times, times[1:])):
        raise ValueError("Capture timestamps must be finite and nondecreasing")
    starts = [0]
    for timestamp in times[1:]:
        starts.append(max(starts[-1] + 1, round((timestamp - times[0]) / speed * fps)))
    # The last capture remains visible for one display second. This is an
    # explicit hold; it makes no statement about subsequent simulation state.
    end_frame = starts[-1] + fps
    ends = starts[1:] + [end_frame]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="policy-site-") as temporary:
        temporary_video = Path(temporary) / "policy.mp4"
        command = [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", "1024x856", "-r", str(fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
            "-preset", "fast", "-crf", "23", "-threads", "2", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(temporary_video),
        ]
        encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
        try:
            for index, (record, start, end) in enumerate(zip(records, starts, ends)):
                frame = montage(episode, index, record)
                if index == 0:
                    frame.save(output.with_name(output.stem + "_poster.jpg"), quality=90)
                if index == len(records) - 1:
                    frame.save(output.with_name(output.stem + "_latest.jpg"), quality=90)
                raw = frame.tobytes()
                for _ in range(end - start):
                    encoder.stdin.write(raw)
            encoder.stdin.close()
            if encoder.wait() != 0:
                raise RuntimeError("ffmpeg could not encode archived RGB captures")
        except BaseException:
            encoder.kill()
            encoder.wait()
            raise
        probe = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,nb_frames",
            "-of", "json", str(temporary_video),
        ]))
        subprocess.run([
            "ffmpeg", "-v", "error", "-threads", "2", "-i", str(temporary_video),
            "-f", "null", "-",
        ], check=True)
        # Temp directories may live on a different filesystem from the website.
        local_temporary = output.with_name("." + output.name + ".tmp")
        local_temporary.write_bytes(temporary_video.read_bytes())
        os.replace(local_temporary, output)

    result_path = episode / "result.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else None
    intervals = [
        {"observation": index, "videoStart": start / fps, "videoEnd": end / fps,
         "simTime": times[index], "capture": relative(episode / "rgb" / f"{index:04d}.npz")}
        for index, (start, end) in enumerate(zip(starts, ends))
    ]
    mapping = [{"videoTime": entry["videoStart"], "simTime": entry["simTime"]}
               for entry in intervals]
    mapping.append({"videoTime": end_frame / fps, "simTime": times[-1]})
    manifest = {
        "schema": "policy-site-media-v1",
        "sourceEpisode": relative(episode),
        "sourceObservations": relative(episode / "rgb/observations.json"),
        "observationCount": len(records),
        "partial": result is None,
        "runSuccess": result.get("success") if result else None,
        "rssSuccess": result.get("rss_success") if result else None,
        "graphAccepted": result.get("graph_success") if result else None,
        "independentPhysicalSuccess": result.get("independent_audit", {}).get("success") if result else None,
        "lastCoveredSimulationTime": times[-1],
        "media": {
            "src": "media/" + output.name,
            "poster": "media/" + output.with_name(output.stem + "_poster.jpg").name,
            "latest": "media/" + output.with_name(output.stem + "_latest.jpg").name,
            "kind": "recorded_policy_rgb",
            "label": "Recorded RGB observations",
            "duration": float(probe["format"]["duration"]),
            "fps": fps,
            "nominalSimulationSpeed": speed,
            "mappingMode": "step",
            "mapping": mapping,
            "intervals": intervals,
            "provenance": "Actual saved RGB inputs to this visual policy run; four calibrated cameras.",
            "sampling": "Each archived observation is held until the next capture. No intermediate motion is synthesized; the final capture is held for one second.",
            "encoding": "Saved-image composition and CPU video encoding only; no physics or CPU rendering.",
        },
    }
    atomic_json(manifest_path, manifest)
    return manifest


def render_native(episode: Path, output: Path, manifest_path: Path,
                  speed: float, stride: int, limit: int | None = None) -> dict:
    """Photograph recorded native poses on a GPU, without stepping physics."""
    result = json.loads((episode / "result.json").read_text())
    all_frames = json.loads((episode / "frames.json").read_text())
    frames = all_frames[::stride]
    if frames[-1]["step"] != all_frames[-1]["step"]:
        frames.append(all_frames[-1])
    if limit is not None:
        frames = frames[:limit]
    workspace = next((parent for parent in episode.parents
                      if (parent / "puzzler/task.py").exists()), None)
    if workspace is None:
        raise ValueError(f"Cannot identify original policy workspace for {episode}")
    # Use the run's task/asset code, not whichever puzzler package the launcher
    # might otherwise select. The model's body order must match the recording.
    sys.path.insert(0, str(workspace))
    import robosimstudio as rss
    import robosimstudio_bench as bench
    import warp as wp
    from puzzler import task

    wp.init()
    if not wp.get_device("cuda:0").is_cuda:
        raise RuntimeError("Native replay requires a CUDA GPU; CPU is forbidden")
    variant = task.Variant(**result["variant"])
    options = dict(max_steps=1, suite="site_native_pose_replay")
    parameters = inspect.signature(task.task_spec).parameters
    if "terminate_on_success" in parameters:
        options["terminate_on_success"] = False
    if "contact_capacity" in parameters:
        options["contact_capacity"] = 512
    spec = task.task_spec(variant, **options)
    # Env construction compiles the native geometry but does not reset/step it.
    # Small contact storage is sufficient because no physics is executed.
    env = bench.Env(spec, device="cuda:0", renderer="", control_mode="joint_position")
    if not env.model.device.is_cuda:
        raise RuntimeError("Native replay model did not build on CUDA")
    camera = rss.CameraSpec(
        name="policy_replay", width=960, height=600, fov_y=48,
        eye=(.98, -.91, 1.30), look_at=(.42, -.005, .83), up=(0, 0, 1),
    )
    renderer = env.make_renderer("tiled", cameras=[camera], channels=["rgb"])
    control_hz = float(result["control_hz"])
    # Recorded samples normally arrive every five control steps. The movie
    # therefore displays every stride-th recorded sample at the stated speed.
    sample_seconds = (all_frames[1]["step"] - all_frames[0]["step"]) / control_hz
    fps = speed / (sample_seconds * stride)
    times = [frame["step"] / control_hz for frame in frames]
    starts = [0]
    for timestamp in times[1:]:
        starts.append(max(starts[-1] + 1, round((timestamp - times[0]) / speed * fps)))
    end_frame = starts[-1] + max(1, round(fps))
    ends = starts[1:] + [end_frame]
    output.parent.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(FONT, 15)
    try:
        with tempfile.TemporaryDirectory(prefix="policy-native-") as temporary:
            temporary_video = Path(temporary) / "policy.mp4"
            encoder = subprocess.Popen([
                "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-s", "960x600", "-r", str(fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
                "-preset", "fast", "-crf", "22", "-threads", "2", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(temporary_video),
            ], stdin=subprocess.PIPE)
            try:
                for index, (frame, start, end) in enumerate(zip(frames, starts, ends)):
                    body_q = np.asarray(frame["body_q"], dtype=np.float32)
                    joint_q = np.asarray(frame["joint_q"], dtype=np.float32)
                    if body_q.shape != tuple(env.state.body_q.shape) + (7,):
                        # Warp transform-array shape excludes its seven scalar coordinates.
                        raise ValueError(f"Recorded body shape {body_q.shape} differs from model {env.state.body_q.shape}")
                    if joint_q.shape != tuple(env.state.joint_q.shape):
                        raise ValueError("Recorded joint order differs from native model")
                    env.state.body_q.assign(body_q)
                    env.state.joint_q.assign(joint_q)
                    env.sync()
                    if index in (0, len(frames) - 1):
                        for name, pose in frame["poses"].items():
                            if not np.allclose(env[name].pose, pose, atol=1e-6, rtol=0):
                                raise ValueError(f"Replay body order does not match recording for {name}")
                    rgb = np.asarray(renderer.render(env.state)[camera.name]["rgb"])[..., :3]
                    image = Image.fromarray(rgb)
                    draw = ImageDraw.Draw(image)
                    draw.rectangle((0, 572, 960, 600), fill="#131719")
                    draw.text((12, 578), f"Recorded policy execution · sim {times[index]:.2f} s · {speed:g}×", font=font, fill="#e8eded")
                    if index == 0:
                        image.save(output.with_name(output.stem + "_poster.jpg"), quality=91)
                    if index == len(frames) - 1:
                        image.save(output.with_name(output.stem + "_latest.jpg"), quality=91)
                    raw = image.tobytes()
                    for _ in range(end - start):
                        encoder.stdin.write(raw)
                    if index % 100 == 0:
                        print(f"Native GPU replay {index + 1}/{len(frames)} frames", flush=True)
                encoder.stdin.close()
                if encoder.wait() != 0:
                    raise RuntimeError("ffmpeg failed during native GPU replay")
            except BaseException:
                encoder.kill()
                encoder.wait()
                raise
            probe = json.loads(subprocess.check_output([
                "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,nb_frames",
                "-of", "json", str(temporary_video),
            ]))
            subprocess.run(["ffmpeg", "-v", "error", "-threads", "2", "-i", str(temporary_video),
                            "-f", "null", "-"], check=True)
            local_temporary = output.with_name("." + output.name + ".tmp")
            local_temporary.write_bytes(temporary_video.read_bytes())
            os.replace(local_temporary, output)
    finally:
        renderer.close()
        env.close()
    intervals = [
        {"recordedFrame": min(index * stride, len(all_frames) - 1), "nativeStep": frame["step"],
         "videoStart": start / fps, "videoEnd": end / fps, "simTime": times[index]}
        for index, (frame, start, end) in enumerate(zip(frames, starts, ends))
    ]
    mapping = [{"videoTime": row["videoStart"], "simTime": row["simTime"]} for row in intervals]
    mapping.append({"videoTime": end_frame / fps, "simTime": times[-1]})
    manifest = {
        "schema": "policy-site-media-v1",
        "sourceEpisode": relative(episode),
        "sourceFrames": relative(episode / "frames.json"),
        "sourceResult": relative(episode / "result.json"),
        "recordedFrameCount": len(all_frames), "displayedFrameCount": len(frames),
        "nativeFrameCount": len(frames),
        "partial": frames[-1]["step"] < all_frames[-1]["step"],
        "runSuccess": result.get("success"),
        "rssSuccess": result.get("rss_success"),
        "graphAccepted": result.get("graph_success"),
        "independentPhysicalSuccess": result.get("independent_audit", {}).get("success"),
        "graphTerminalError": result.get("error"),
        "lastCoveredSimulationTime": times[-1],
        "media": {
            "src": "media/" + output.name,
            "poster": "media/" + output.with_name(output.stem + "_poster.jpg").name,
            "latest": "media/" + output.with_name(output.stem + "_latest.jpg").name,
            "kind": "native_recorded_state_render",
            "label": "Recorded policy execution",
            "duration": float(probe["format"]["duration"]),
            "fps": fps, "nominalSimulationSpeed": speed, "mappingMode": "step",
            "mapping": mapping, "intervals": intervals,
            "provenance": "Native body_q and joint_q saved by this policy execution, rendered with RSS tiled on CUDA. No physics steps, pose edits or policy reruns.",
            "sampling": f"Every {stride}th recorded native sample; final frame held for one display second.",
            "renderDevice": str(env.model.device),
            "recordingControlHz": control_hz,
        },
    }
    atomic_json(manifest_path, manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, default=DEFAULT_EPISODE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path, default=ROOT / "results/site_policy_media/manifest.json")
    parser.add_argument("--speed", type=float, default=8)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--mode", choices=("rgb", "native"), default="rgb")
    parser.add_argument("--stride", type=int, default=4, help="Native recorded-frame stride")
    parser.add_argument("--limit", type=int, help="Native preflight frame limit")
    arguments = parser.parse_args()
    if arguments.speed <= 0 or arguments.fps <= 0 or arguments.stride <= 0:
        parser.error("--speed, --fps and --stride must be positive")
    if arguments.limit is not None and arguments.limit <= 0:
        parser.error("--limit must be positive")
    if arguments.output is None:
        kind = "native" if arguments.mode == "native" else "rgb"
        arguments.output = ROOT / f"site/media/policy_v13_{kind}.mp4"
    if arguments.mode == "native":
        exported = render_native(arguments.episode.resolve(), arguments.output.resolve(),
                                 arguments.manifest.resolve(), arguments.speed,
                                 arguments.stride, arguments.limit)
    else:
        exported = render(arguments.episode.resolve(), arguments.output.resolve(),
                          arguments.manifest.resolve(), arguments.speed, arguments.fps)
    print(json.dumps({key: exported.get(key) for key in (
        "observationCount", "partial", "runSuccess", "lastCoveredSimulationTime"
    )}, indent=2))
    print(exported["media"]["src"])
