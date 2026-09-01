from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


class ClientRuntimeUnavailable(RuntimeError):
    pass


@dataclass
class _Connection:
    user_id: int
    websocket: WebSocket
    connection_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class _PendingRequest:
    user_id: int
    connection_id: str
    future: asyncio.Future[dict[str, Any]]


class ClientRuntimeBroker:
    """Routes server-side capability calls to the authenticated desktop session."""

    def __init__(self) -> None:
        self._connections: dict[int, _Connection] = {}
        self._pending: dict[str, _PendingRequest] = {}
        self._lock = asyncio.Lock()

    async def serve(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        connection = _Connection(user_id=user_id, websocket=websocket)
        previous: _Connection | None = None
        async with self._lock:
            previous = self._connections.get(user_id)
            self._connections[user_id] = connection

        if previous is not None:
            try:
                await previous.websocket.close(code=4001, reason="Replaced by a newer desktop session")
            except Exception:
                pass

        await websocket.send_json(
            {
                "type": "ready",
                "connection_id": connection.connection_id,
                "user_id": user_id,
            }
        )

        try:
            while True:
                message = await websocket.receive_json()
                message_type = message.get("type")
                if message_type == "response":
                    await self._resolve_response(connection, message)
                elif message_type == "ping":
                    async with connection.send_lock:
                        await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            pass
        finally:
            await self._remove_connection(connection)

    async def is_connected(self, user_id: int) -> bool:
        async with self._lock:
            return user_id in self._connections

    async def execute(
        self,
        *,
        user_id: int,
        capability: str,
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        request_id = uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = loop.create_future()

        async with self._lock:
            connection = self._connections.get(user_id)
            if connection is None:
                raise ClientRuntimeUnavailable("No desktop client is connected for this user")
            self._pending[request_id] = _PendingRequest(
                user_id=user_id,
                connection_id=connection.connection_id,
                future=future,
            )

        try:
            async with connection.send_lock:
                await connection.websocket.send_json(
                    {
                        "type": "request",
                        "request_id": request_id,
                        "capability": capability,
                        "payload": payload,
                    }
                )
            return await asyncio.wait_for(future, timeout=max(1, timeout_seconds))
        except asyncio.TimeoutError as exc:
            raise ClientRuntimeUnavailable("Desktop capability request timed out") from exc
        except ClientRuntimeUnavailable:
            raise
        except Exception as exc:
            raise ClientRuntimeUnavailable("Desktop client connection was lost") from exc
        finally:
            async with self._lock:
                self._pending.pop(request_id, None)

    async def _resolve_response(
        self,
        connection: _Connection,
        message: dict[str, Any],
    ) -> None:
        request_id = str(message.get("request_id") or "")
        if not request_id:
            return
        async with self._lock:
            pending = self._pending.get(request_id)
        if (
            pending is None
            or pending.user_id != connection.user_id
            or pending.connection_id != connection.connection_id
            or pending.future.done()
        ):
            return

        if message.get("ok") is False:
            pending.future.set_exception(
                ClientRuntimeUnavailable(str(message.get("error") or "Desktop capability failed"))
            )
            return
        result = message.get("result")
        pending.future.set_result(result if isinstance(result, dict) else {"data": result})

    async def _remove_connection(self, connection: _Connection) -> None:
        pending_to_fail: list[asyncio.Future[dict[str, Any]]] = []
        async with self._lock:
            current = self._connections.get(connection.user_id)
            if current is connection:
                self._connections.pop(connection.user_id, None)
            for request in self._pending.values():
                if (
                    request.connection_id == connection.connection_id
                    and not request.future.done()
                ):
                    pending_to_fail.append(request.future)
        for future in pending_to_fail:
            future.set_exception(ClientRuntimeUnavailable("Desktop client disconnected"))


client_runtime_broker = ClientRuntimeBroker()
