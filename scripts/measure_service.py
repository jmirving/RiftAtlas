"""Measure an installed service on Linux/WSL; emit JSON, never modify its data."""
import concurrent.futures
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import resource
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time

import httpx


def main():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    root = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items() if key not in
           ("PYTHONPATH", "DPS_DRAFTS_PATH", "DPS_MANIFEST_PATH", "DPS_ROLES_PATH")}
    env.update(DPS_DRAFTS_PATH=str(root / "data/drafts.csv"), DPS_MANIFEST_PATH=str(root / "data/manifest.json"))
    with tempfile.TemporaryFile(mode="w+") as log:
        started = time.perf_counter()
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "rift_atlas.api:app",
                                    "--host", "127.0.0.1", "--port", str(port), "--workers", "1"],
                                   cwd=root, env=env, stdout=log, stderr=log)
        try:
            base = f"http://127.0.0.1:{port}"
            with httpx.Client(base_url=base, timeout=60) as client:
                while True:
                    if process.poll() is not None or time.perf_counter() - started > 90:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    try:
                        if client.get("/healthz").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.05)
                startup = time.perf_counter() - started
                metadata = client.get("/api/v1/dataset").json()
                samples = {}
                queries = {
                    "single_pin": {"champion": "Maokai"},
                    "two_pins": {"champion": "Maokai", "pinned": ["Maokai", "Jinx"]},
                    "four_pins": {"champion": "Maokai", "pinned": ["Maokai", "Jinx", "Ahri", "Nautilus"]},
                    "top_leagues": {"champion": "Maokai", "league": ["LCK", "LPL"]},
                    "recent_patches": {"champion": "Maokai", "patch_from": "16.17", "patch_to": "16.20"},
                    "empty_leagues": {"champion": "Maokai", "league": ""},
                    "maximum_results": {"champion": "Maokai", "limit": 50},
                }
                def request(client, params):
                    begin = time.perf_counter()
                    response = client.get("/api/v1/relationships", params=params)
                    response.raise_for_status()
                    assert response.json()["dataset_id"] == metadata["dataset_id"]
                    return time.perf_counter() - begin
                for name, query in queries.items():
                    request(client, query)
                    elapsed = [request(client, query) for _ in range(5)]
                    samples[name] = {"samples": 5, "median_seconds": statistics.median(elapsed), "max_seconds": max(elapsed)}
                barrier = threading.Barrier(2)
                def user(query):
                    with httpx.Client(base_url=base, timeout=60) as own:
                        barrier.wait(timeout=10)
                        return [request(own, query) for _ in range(10)]
                concurrent_started = time.perf_counter()
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(user, queries[name]) for name in ("two_pins", "four_pins")]
                    concurrent_samples = [value for future in futures for value in future.result()]
                concurrent_wall = time.perf_counter() - concurrent_started
                status = Path(f"/proc/{process.pid}/status").read_text()
                peak_kib = int(next(line.split()[1] for line in status.splitlines() if line.startswith("VmHWM:")))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        log.seek(0)
        ready_line = next(line.strip() for line in log if "DPS ready" in line)
    print(json.dumps({"measured_at": datetime.now(timezone.utc).isoformat(),
        "environment": {"platform": platform.platform(), "python": platform.python_version(), "cpu_count": os.cpu_count(),
                        "workers": 1, "installed_package": True, "deployment": "local WSL; not Render"},
        "dataset_id": metadata["dataset_id"], "csv_sha256": metadata["csv_sha256"],
        "startup_to_http_ready_seconds": startup, "startup_log": ready_line,
        "server_peak_rss_mib": peak_kib / 1024,
        "process_peak_rss_mib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024,
        "warm_http_queries": samples,
        "two_concurrent_http_clients": {"requests": 20, "wall_seconds": concurrent_wall,
            "median_seconds": statistics.median(concurrent_samples), "max_seconds": max(concurrent_samples)},
        "limitations": "Local HTTP baseline only; deployment cold start, restart, and simultaneous browser users remain to be measured on Render."}, indent=2))


if __name__ == "__main__":
    main()
