"""Rede do client lab: WS tunnel servindo pasta local OU proxyando porta local."""
import asyncio
import base64
import json
import mimetypes
import os
import ssl
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote

import certifi
import httpx
import websockets

import config


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


class _FolderHandler:
    """Lê arquivos diretamente do disco em resposta a envelopes do túnel."""

    def __init__(self, folder: str):
        self.folder = Path(folder).resolve()

    async def handle(self, env: dict) -> dict:
        req_id = env["id"]
        method = env.get("method", "GET")
        if method not in ("GET", "HEAD"):
            return _resp(req_id, 405, b"method not allowed", "text/plain; charset=utf-8")

        raw = env.get("path", "/")
        rel = unquote(raw.split("?", 1)[0].split("#", 1)[0]).lstrip("/")

        try:
            target = (self.folder / rel).resolve()
            target.relative_to(self.folder)
        except (ValueError, OSError):
            return _resp(req_id, 403, b"forbidden", "text/plain; charset=utf-8")

        if target.is_dir():
            idx = target / "index.html"
            if idx.is_file():
                target = idx

        if not target.is_file():
            fallback = self.folder / "index.html"
            if fallback.is_file():
                target = fallback
            else:
                return _resp(req_id, 404, b"not found", "text/plain; charset=utf-8")

        try:
            data = target.read_bytes()
        except OSError as e:
            return _resp(req_id, 500, f"read error: {e}".encode(), "text/plain; charset=utf-8")

        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = data if method == "GET" else b""
        return _resp(req_id, 200, body, ctype, cache="no-cache")


class _PortHandler:
    """Proxya envelopes pro localhost:<port>."""

    def __init__(self, port: int):
        self.port = port

    async def handle(self, env: dict, http: httpx.AsyncClient) -> dict:
        req_id = env["id"]
        method = env.get("method", "GET")
        path = env.get("path", "/")
        url = f"http://localhost:{self.port}{path}"
        headers = {k: v[0] for k, v in (env.get("headers") or {}).items() if v}
        for h in ("Host", "host", "Origin", "origin", "Referer", "referer"):
            headers.pop(h, None)
        body = base64.b64decode(env.get("body") or "")
        resp = await http.request(method, url, headers=headers, content=body or None)
        return {
            "type": "resp",
            "id": req_id,
            "status": resp.status_code,
            "headers": {k: [v] for k, v in resp.headers.items()},
            "body": base64.b64encode(resp.content).decode(),
        }


def _resp(req_id: str, status: int, body: bytes, ctype: str, cache: Optional[str] = None) -> dict:
    headers = {"Content-Type": [ctype]}
    if cache:
        headers["Cache-Control"] = [cache]
    return {
        "type": "resp",
        "id": req_id,
        "status": status,
        "headers": headers,
        "body": base64.b64encode(body).decode(),
    }


class TunnelClient:
    """Abre WS pro servidor e responde envelopes a partir de uma pasta local ou de uma porta local."""

    def __init__(
        self,
        mode: str,
        target,
        friendly: Optional[str],
        on_event: Callable[[str, dict], None],
    ):
        if mode not in ("folder", "port"):
            raise ValueError(f"mode inválido: {mode}")
        if mode == "folder":
            if not target or not os.path.isdir(target):
                raise ValueError(f"pasta inválida: {target}")
            self.handler = _FolderHandler(str(target))
        else:
            port = int(target)
            if not 1 <= port <= 65535:
                raise ValueError(f"porta fora do intervalo 1-65535: {port}")
            self.handler = _PortHandler(port)
        self.mode = mode
        self.friendly = friendly or ""
        self.on_event = on_event
        self._stop = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task: Optional[asyncio.Task] = None

    def start(self):
        self._loop = asyncio.new_event_loop()
        self._task = self._loop.create_task(self._run())
        try:
            self._loop.run_until_complete(self._task)
        finally:
            self._loop.close()

    def stop(self):
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._stop.set)

    async def _run(self):
        attempt = 0
        while not self._stop.is_set():
            try:
                self.on_event("status", {"state": "connecting"})
                url = config.TUNNEL_URL + f"?friendly={self.friendly}"
                async with websockets.connect(url, max_size=64 << 20, ssl=_ssl_context()) as ws:
                    attempt = 0
                    hello = json.loads(await ws.recv())
                    if hello.get("type") != "hello":
                        raise RuntimeError(f"esperava hello, veio {hello}")
                    self.on_event("up", {"url": hello["url"], "slug": hello["slug"]})

                    if self.mode == "port":
                        async with httpx.AsyncClient(timeout=config.TUNNEL_LOCAL_TIMEOUT_S, verify=certifi.where()) as http:
                            await self._pump(ws, http)
                    else:
                        await self._pump(ws, None)
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.on_event("error", {"message": str(e)})
                if self._stop.is_set():
                    return
                delay = config.RECONNECT_BACKOFF_S[min(attempt, len(config.RECONNECT_BACKOFF_S) - 1)]
                attempt += 1
                self.on_event("status", {"state": "reconnecting", "in_s": delay})
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                    return
                except asyncio.TimeoutError:
                    pass
        self.on_event("status", {"state": "off"})

    async def _pump(self, ws, http: Optional[httpx.AsyncClient]):
        stop_task = asyncio.create_task(self._stop.wait())
        try:
            while True:
                recv_task = asyncio.create_task(ws.recv())
                done, _ = await asyncio.wait(
                    {recv_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if stop_task in done:
                    recv_task.cancel()
                    await ws.close()
                    return
                raw = recv_task.result()
                env = json.loads(raw)
                if env.get("type") != "req":
                    continue
                asyncio.create_task(self._handle_one(ws, http, env))
        finally:
            stop_task.cancel()

    async def _handle_one(self, ws, http: Optional[httpx.AsyncClient], env: dict):
        req_id = env["id"]
        try:
            if self.mode == "folder":
                out = await self.handler.handle(env)
            else:
                out = await self.handler.handle(env, http)
        except Exception as e:
            out = _resp(req_id, 502, f"lab handler error: {e}".encode(), "text/plain; charset=utf-8")
        try:
            await ws.send(json.dumps(out))
        except Exception:
            pass
