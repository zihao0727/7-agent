from __future__ import annotations

import asyncio
import unittest

from starlette.websockets import WebSocketDisconnect

from backend.client_runtime import ClientRuntimeBroker, ClientRuntimeUnavailable


class _FakeWebSocket:
    def __init__(self) -> None:
        self.received: asyncio.Queue[dict | None] = asyncio.Queue()
        self.sent: asyncio.Queue[dict] = asyncio.Queue()

    async def accept(self) -> None:
        return None

    async def close(self, code: int, reason: str) -> None:
        await self.received.put(None)

    async def send_json(self, payload: dict) -> None:
        await self.sent.put(payload)

    async def receive_json(self) -> dict:
        payload = await self.received.get()
        if payload is None:
            raise WebSocketDisconnect()
        return payload


class ClientRuntimeBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_is_resolved_only_by_the_users_connection(self) -> None:
        broker = ClientRuntimeBroker()
        websocket = _FakeWebSocket()
        serving = asyncio.create_task(broker.serve(7, websocket))
        ready = await websocket.sent.get()
        self.assertEqual(ready["type"], "ready")

        executing = asyncio.create_task(
            broker.execute(
                user_id=7,
                capability="lark-cli",
                payload={"args": ["auth", "status"]},
                timeout_seconds=2,
            )
        )
        request = await websocket.sent.get()
        await websocket.received.put(
            {
                "type": "response",
                "request_id": request["request_id"],
                "ok": True,
                "result": {"exit_code": 0, "stdout": "ok"},
            }
        )
        result = await executing
        self.assertEqual(result["stdout"], "ok")

        await websocket.received.put(None)
        await serving

    async def test_missing_user_connection_fails_closed(self) -> None:
        broker = ClientRuntimeBroker()
        with self.assertRaises(ClientRuntimeUnavailable):
            await broker.execute(
                user_id=9,
                capability="lark-cli",
                payload={},
                timeout_seconds=1,
            )
