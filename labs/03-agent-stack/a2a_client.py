"""
Block 3 - a second agent (the "caller") discovering and talking to the Nova City agent over A2A.

    python a2a_client.py                       # A2A server must be running on :9999
    python a2a_client.py --auto-approve yes
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers.proto_helpers import get_artifact_text, get_message_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState

A2A_URL = os.getenv("A2A_URL", "http://127.0.0.1:9999")
A2A_TIMEOUT = float(os.getenv("A2A_TIMEOUT", "120"))   # a graph run (triage + RAG + LLM) exceeds httpx's 5s default


async def send(client, text: str, context_id: str, task_id: str | None = None):
    msg = new_text_message(text, context_id=context_id, task_id=task_id, role=Role.ROLE_USER)
    final = None
    async for event in client.send_message(SendMessageRequest(message=msg)):
        final = event
    task = final.task if final.HasField("task") else None
    return task


def show(task) -> str:
    state = TaskState.Name(task.status.state)
    text = "\n".join(get_artifact_text(a) for a in task.artifacts) or \
        (get_message_text(task.status.message) if task.status.HasField("message") else "")
    print(f"  task={task.id[:8]} state={state}\n  {text.strip()}")
    return state


async def main():
    auto = sys.argv[sys.argv.index("--auto-approve") + 1] if "--auto-approve" in sys.argv else None
    http = httpx.AsyncClient(timeout=A2A_TIMEOUT)
    client = await create_client(A2A_URL, client_config=ClientConfig(streaming=False, httpx_client=http))
    print(f"Connected to A2A agent at {A2A_URL}")
    context_id = str(uuid.uuid4())
    for q in ["How do I renew my driving licence?", "Please renew my driving licence now, ref LAB-002"]:
        print(f"\n> {q}")
        task = await send(client, q, context_id)
        if show(task) == "TASK_STATE_INPUT_REQUIRED":
            answer = auto if auto is not None else input("  approve? (yes/no) ")
            print(f"> {answer}")
            show(await send(client, answer, context_id, task_id=task.id))
    await client.close()
    await http.aclose()


if __name__ == "__main__":
    asyncio.run(main())
