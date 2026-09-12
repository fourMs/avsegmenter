import time, json
from pathlib import Path
from musicalgestures._camera import make_proxy, camera_motion
from musicalgestures._performers import detect_people
V = Path("/home/alexanje/Downloads/balint/output.mp4"); out = Path("/home/alexanje/Downloads/balint/analysis")
hw = ["-hwaccel", "cuda"]
t0 = time.time()
proxy = make_proxy(V, out / "proxy_videogram.mp4", fps=2.0, height=180, ffmpeg_input_args=hw)
print("proxy", proxy, round(time.time() - t0), flush=True)
cam = camera_motion(V, proxy_path=proxy, cache=out / "camera.json", verbose=True)
print("camera", cam["summary"], len(cam["cuts"]), round(time.time() - t0), flush=True)
det = detect_people(V, fps=1.0, width=640, verbose=True, ffmpeg_input_args=hw)
(out / "persons.json").write_text(json.dumps(det))
print("persons", len(det["frames"]), round(time.time() - t0), flush=True)
