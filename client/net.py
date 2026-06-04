"""Rede: upload de zip e loop de tunnel WebSocket reverso."""
import asyncio
import base64
import io
import json
import os
import ssl
import zipfile
from typing import Callable, Optional

import certifi
import httpx
import websockets

import config


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def zip_directory(path: str) -> bytes:
    if not os.path.isdir(path):
        raise ValueError(f"pasta inválida: {path}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(path):
            for name in files:
                full = os.path.join(root, name)
                arc = os.path.relpath(full, path)
                zf.write(full, arc)
    return buf.getvalue()


def publish_folder(path: str, friendly: Optional[str]) -> dict:
    data = zip_directory(path)
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"build muito grande ({len(data) >> 20}MB > {config.MAX_UPLOAD_MB}MB)")
    files = {"file": ("dist.zip", data, "application/zip")}
    form = {"friendly": friendly or ""}
    with httpx.Client(timeout=config.UPLOAD_TIMEOUT_S, verify=certifi.where()) as client:
        r = client.post(config.PUBLISH_URL, files=files, data=form)
    r.raise_for_status()
    return r.json()


class TunnelClient:
    """Conecta no /tunnel, recebe envelopes de request, proxya pro localhost:<port>."""

    def __init__(self, port: int, friendly: Optional[str], on_event: Callable[[str, dict], None]):
        self.port = port
        self.friendly = friendly or ""
        self.on_event = on_event
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

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

                    async with httpx.AsyncClient(timeout=config.TUNNEL_LOCAL_TIMEOUT_S, verify=certifi.where()) as http:
                        await self._pump(ws, http)
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

    async def _pump(self, ws, http: httpx.AsyncClient):
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

    async def _handle_one(self, ws, http: httpx.AsyncClient, env: dict):
        req_id = env["id"]
        try:
            method = env.get("method", "GET")
            path = env.get("path", "/")
            url = f"http://localhost:{self.port}{path}"
            headers = {k: v[0] for k, v in (env.get("headers") or {}).items() if v}
            headers.pop("Host", None)
            headers.pop("host", None)
            headers.pop("Origin", None)
            headers.pop("origin", None)
            headers.pop("Referer", None)
            headers.pop("referer", None)
            body = base64.b64decode(env.get("body") or "")
            resp = await http.request(
                method, url, headers=headers, content=body or None
            )
            out = {
                "type": "resp",
                "id": req_id,
                "status": resp.status_code,
                "headers": {k: [v] for k, v in resp.headers.items()},
                "body": base64.b64encode(resp.content).decode(),
            }
        except Exception as e:
            out = {
                "type": "resp",
                "id": req_id,
                "status": 502,
                "headers": {"Content-Type": ["text/plain; charset=utf-8"]},
                "body": base64.b64encode(
                    f"floofy local proxy error: {e}".encode()
                ).decode(),
            }
        try:
            await ws.send(json.dumps(out))
        except Exception:
            pass
