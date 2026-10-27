"""Verify native skill discovery without a model call or personal configuration."""
import argparse
import base64
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request


def check(binary, root, timeout):
    with tempfile.TemporaryDirectory(prefix="case-opencode-", dir=root / "1_workspace/validation") as scratch:
        env = os.environ.copy()
        for key, directory in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                               ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state")):
            env[key] = str(Path(scratch) / directory)
        password = secrets.token_urlsafe(32)
        env["OPENCODE_SERVER_PASSWORD"] = password
        env["OPENCODE_PASSWORD"] = password
        process = subprocess.Popen(
            [binary, "serve", "--stdio", "--hostname", "127.0.0.1", "--port", "0"],
            cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        ready = queue.Queue()

        def read_ready():
            try:
                ready.put(process.stdout.readline())
            except Exception:
                ready.put("")

        reader = threading.Thread(target=read_ready, daemon=True)
        reader.start()
        try:
            deadline = time.monotonic() + timeout
            try:
                url = json.loads(ready.get(timeout=timeout))["url"]
            except (queue.Empty, ValueError, KeyError) as exc:
                raise RuntimeError("OpenCode did not provide a server-ready response.") from exc
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
                raise RuntimeError("OpenCode returned an unexpected local server address.")
            base = f"http://127.0.0.1:{parsed.port}"
            authorization = base64.b64encode(f"opencode:{password}".encode()).decode()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            while time.monotonic() < deadline:
                request = urllib.request.Request(base + "/api/skill", headers={
                    "Authorization": "Basic " + authorization,
                })
                with opener.open(request, timeout=min(5, max(.1, deadline - time.monotonic()))) as response:
                    result = json.load(response)
                skill = next((item for item in result.get("data", [])
                              if item.get("id") == "pdf-to-markdown"), None)
                if skill is not None:
                    print(json.dumps({"native_skill": skill["id"], "discovered": True,
                                      "note": "Registration verified; model invocation was not requested."}, indent=2))
                    return
                if process.poll() is not None:
                    raise RuntimeError("OpenCode exited before skill discovery completed.")
                time.sleep(min(.25, max(0, deadline - time.monotonic())))
            raise RuntimeError("pdf-to-markdown was not discovered before the timeout.")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            reader.join(timeout=1)
            process.stdin.close()
            process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opencode", help="OpenCode executable path; defaults to PATH lookup.")
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 120:
        parser.error("--timeout must be between 1 and 120 seconds")
    binary = args.opencode or shutil.which("opencode")
    if not binary:
        parser.error("OpenCode is not on PATH; supply its executable with --opencode.")
    try:
        check(binary, Path(__file__).resolve().parents[2], args.timeout)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"Skill check failed: {exc}\n")


if __name__ == "__main__":
    main()
