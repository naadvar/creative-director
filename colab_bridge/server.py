"""FastAPI bridge server that runs inside a Colab session.

Exposes a small auth-protected API for executing Python in the kernel's
persistent globals. Designed to be tunneled via cloudflared to a
*.trycloudflare.com URL so an external client (the local Claude Code
agent) can drive experiments.

Threat model: anyone with the URL + token can execute arbitrary Python
in the Colab session. Treat the token like a password.
"""
from __future__ import annotations

import io
import os
import secrets
import sys
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel


AUTH_TOKEN = os.environ.get("BRIDGE_TOKEN") or secrets.token_urlsafe(32)


def _resolve_kernel_globals() -> dict:
    """Return a dict to use as the persistent execution namespace.

    When running inside a Jupyter/Colab kernel, `__main__.__dict__` IS the
    notebook's cell-level globals, so anything we set here is also visible
    to subsequent cells (and vice versa). Falling back to a fresh dict
    keeps the server usable outside notebook environments.
    """
    try:
        import __main__

        ns = __main__.__dict__
        # Tag so callers can confirm we're sharing with __main__
        ns.setdefault("__bridge_shared__", True)
        return ns
    except Exception:
        return {
            "__name__": "__bridge__",
            "__builtins__": __builtins__,
            "__bridge_shared__": False,
        }


# Persistent execution namespace. Shared with notebook cells when possible.
KERNEL_GLOBALS: dict = _resolve_kernel_globals()

app = FastAPI(title="creative-director Colab bridge", version="0.1.0")


def _check_auth(authorization: Optional[str] = Header(None)) -> None:
    expected = f"Bearer {AUTH_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")


class ExecRequest(BaseModel):
    code: str
    timeout: float = 300.0  # informational only; FastAPI doesn't enforce


class ExecResponse(BaseModel):
    stdout: str
    stderr: str
    result: Optional[str]
    error: Optional[str]
    elapsed: float


@app.get("/health")
def health(_=Depends(_check_auth)) -> dict:
    info = {
        "ok": True,
        "python": sys.version.split()[0],
        "pid": os.getpid(),
        "cwd": os.getcwd(),
    }
    try:
        import torch

        info["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            info["device_name"] = torch.cuda.get_device_name(0)
    except Exception as e:
        info["torch_error"] = str(e)
    return info


@app.post("/exec", response_model=ExecResponse)
def exec_code(req: ExecRequest, _=Depends(_check_auth)) -> ExecResponse:
    """Run a code snippet in the kernel's persistent globals.

    Tries to compile as an expression first (so we can return repr(result)),
    falls back to statement execution. Captures stdout + stderr.
    """
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    result_repr: Optional[str] = None
    err: Optional[str] = None

    t0 = time.time()
    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            try:
                code_obj = compile(req.code, "<bridge>", "eval")
                value = eval(code_obj, KERNEL_GLOBALS)
                if value is not None:
                    result_repr = repr(value)
            except SyntaxError:
                exec(compile(req.code, "<bridge>", "exec"), KERNEL_GLOBALS)
    except SystemExit as e:
        err = f"SystemExit({e.code})"
    except BaseException:
        err = traceback.format_exc()

    return ExecResponse(
        stdout=stdout_buf.getvalue(),
        stderr=stderr_buf.getvalue(),
        result=result_repr,
        error=err,
        elapsed=time.time() - t0,
    )


def start_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the server (blocking). Usually called from a background thread."""
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")
