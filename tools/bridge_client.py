"""Local CLI client for the Colab bridge.

Reads BRIDGE_URL and BRIDGE_TOKEN from the .colab_bridge file in the project
root and POSTs code to the running Colab bridge server.

Usage:
    # one-liner via -c
    py -3 tools/bridge_client.py -c "import torch; print(torch.cuda.is_available())"

    # health check
    py -3 tools/bridge_client.py --health

    # multi-line via stdin
    py -3 tools/bridge_client.py < script.py

    # run a file
    py -3 tools/bridge_client.py -f path/to/script.py

    # custom timeout (seconds)
    py -3 tools/bridge_client.py -c "long_thing()" --timeout 600
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx


CONFIG_PATH = Path(__file__).resolve().parent.parent / ".colab_bridge"


def load_config() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        sys.stderr.write(
            f"ERROR: {CONFIG_PATH} not found.\n"
            "Start the bridge cell in your Colab notebook and save the printed\n"
            "BRIDGE_URL and BRIDGE_TOKEN lines to that file (one per line).\n"
        )
        sys.exit(2)
    config: dict[str, str] = {}
    for raw in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        config[key.strip()] = val.strip().strip('"').strip("'")
    if "BRIDGE_URL" not in config or "BRIDGE_TOKEN" not in config:
        sys.stderr.write("ERROR: BRIDGE_URL and BRIDGE_TOKEN must both be set in .colab_bridge\n")
        sys.exit(2)
    return config


def call(path: str, method: str = "GET", body: dict | None = None, timeout: float = 330.0) -> dict:
    cfg = load_config()
    url = cfg["BRIDGE_URL"].rstrip("/") + path
    headers = {"Authorization": f"Bearer {cfg['BRIDGE_TOKEN']}"}
    with httpx.Client(timeout=timeout) as client:
        if method == "GET":
            r = client.get(url, headers=headers)
        else:
            r = client.post(url, headers=headers, json=body or {})
    r.raise_for_status()
    return r.json()


def cmd_exec(code: str, timeout: float) -> int:
    """Run code on the remote kernel. Prints stdout/stderr/result/error."""
    try:
        resp = call("/exec", method="POST", body={"code": code, "timeout": timeout}, timeout=timeout + 30)
    except httpx.HTTPError as e:
        sys.stderr.write(f"BRIDGE HTTP ERROR: {e}\n")
        return 3
    if resp.get("stdout"):
        sys.stdout.write(resp["stdout"])
    if resp.get("stderr"):
        sys.stderr.write(resp["stderr"])
    if resp.get("result") is not None:
        sys.stdout.write(("\n" if resp.get("stdout") else "") + str(resp["result"]) + "\n")
    if resp.get("error"):
        sys.stderr.write(resp["error"])
        return 1
    sys.stderr.write(f"[bridge: {resp['elapsed']:.2f}s]\n")
    return 0


def cmd_health() -> int:
    try:
        resp = call("/health", timeout=15)
    except httpx.HTTPError as e:
        sys.stderr.write(f"BRIDGE HTTP ERROR: {e}\n")
        return 3
    print(json.dumps(resp, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Send code to the Colab bridge.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("-c", "--code", help="Inline Python to execute")
    g.add_argument("-f", "--file", help="Path to a Python file to execute remotely")
    g.add_argument("--health", action="store_true", help="GET /health and print status")
    p.add_argument("--timeout", type=float, default=300.0, help="Server-side soft timeout (seconds)")
    args = p.parse_args()

    if args.health:
        return cmd_health()

    if args.file:
        code = Path(args.file).read_text(encoding="utf-8")
    elif args.code:
        code = args.code
    else:
        if sys.stdin.isatty():
            p.print_help()
            return 2
        code = sys.stdin.read()

    return cmd_exec(code, timeout=args.timeout)


if __name__ == "__main__":
    sys.exit(main())
