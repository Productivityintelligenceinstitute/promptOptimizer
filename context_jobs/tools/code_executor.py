"""Docker-sandboxed Python code execution."""

from __future__ import annotations

import asyncio
import os
import shlex
import tempfile
from pathlib import Path
from typing import Any, Optional

from context_jobs.tools.base import BaseTool


class CodeExecutorTool(BaseTool):
    id = "code-exec"
    name = "Code Executor"
    description = (
        "Execute Python 3 code in an isolated Docker sandbox and return stdout/stderr. "
        "Only Python is supported; dependencies are limited to those preinstalled in the sandbox image."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute"},
            "timeout_seconds": {"type": "integer", "default": 10, "maximum": 30},
        },
        "required": ["code"],
    }

    async def execute(self, arguments: dict[str, Any], api_key: Optional[str] = None) -> str:
        code = str(arguments.get("code", "")).strip()
        if not code:
            raise ValueError("code is required")
        timeout = min(int(arguments.get("timeout_seconds") or 10), 30)
        image = os.environ.get("CODE_EXEC_DOCKER_IMAGE", "python:3.11-alpine")

        with tempfile.TemporaryDirectory() as tmp:
            script_path = Path(tmp) / "script.py"
            script_path.write_text(code, encoding="utf-8")
            host_dir = shlex.quote(str(tmp))
            cmd = (
                f"docker run --rm --network none --memory 256m --cpus 0.5 "
                f"-v {host_dir}:/work:ro -w /work {shlex.quote(image)} "
                f"python /work/script.py"
            )
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                raise TimeoutError(f"code execution exceeded {timeout}s")

        out = (stdout.decode("utf-8", errors="replace") if stdout else "")[:3000]
        err = (stderr.decode("utf-8", errors="replace") if stderr else "")[:1000]
        if err:
            out = f"{out}\n[stderr]: {err}".strip()
        return out or "(no output)"
