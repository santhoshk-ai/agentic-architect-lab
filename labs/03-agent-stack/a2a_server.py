"""
Block 3 - expose the LangGraph agent to OTHER agents over A2A (a2a-sdk 1.x, JSON-RPC binding).

    GET  /.well-known/agent-card.json   discovery: who am I, what skills, which endpoint
    POST /a2a                            JSON-RPC SendMessage

MCP vs A2A in one line: MCP connects an agent to its TOOLS; A2A connects an agent to other AGENTS
(opaque peers with their own reasoning, state and task lifecycle).

The A2A contextId maps to the LangGraph thread_id, so a remote agent keeps conversation memory, and the
human-approval interrupt surfaces as the A2A task state INPUT_REQUIRED. Reply "yes"/"no" on the same
context to resume.

Run:   python a2a_server.py           (http://127.0.0.1:9999)
Test:  python a2a_client.py
"""
from __future__ import annotations

import os

from a2a.helpers.proto_helpers import get_message_text, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from langgraph.types import Command
from starlette.applications import Starlette

from graph import build

HOST = os.getenv("A2A_HOST", "127.0.0.1")
PORT = int(os.getenv("A2A_PORT", "9999"))
BASE_URL = os.getenv("A2A_BASE_URL", f"http://{HOST}:{PORT}")

CARD = AgentCard(
    name="Nova City Services Agent",
    description="Answers Nova City residency, driving and general service questions with cited sources, "
                "and submits applications after human approval.",
    version="0.1.0",
    supported_interfaces=[AgentInterface(url=f"{BASE_URL}/a2a", protocol_binding="JSONRPC",
                                         protocol_version="1.0")],
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(id="answer-service-question", name="Answer service question",
                   description="Grounded, cited answers from the Nova City FAQ knowledge base.",
                   tags=["faq", "rag", "government-services"],
                   examples=["How do I renew my driving licence?"]),
        AgentSkill(id="submit-application", name="Submit application (human approval)",
                   description="Prepares a submission and pauses for approval (input-required).",
                   tags=["action", "human-in-the-loop"],
                   examples=["Please renew my driving licence now, ref LAB-001"]),
    ],
)


class NovaCityExecutor(AgentExecutor):
    def __init__(self):
        self.graph = build()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        cfg = {"configurable": {"thread_id": task.context_id}}
        text = get_message_text(context.message)

        snapshot = await self.graph.aget_state(cfg)
        if snapshot.next and "approve" in snapshot.next:       # thread is paused at the approval interrupt
            state = await self.graph.ainvoke(Command(resume=text), cfg)
        else:
            await updater.start_work()
            state = await self.graph.ainvoke({"question": text}, cfg)

        if "__interrupt__" in state:
            req = state["__interrupt__"][0].value
            await updater.requires_input(updater.new_agent_message([new_text_part(
                f"{state['answer']}\n\nApproval needed for {req['action']} {req['args']}. Reply yes or no.")]))
            return
        reply = state["answer"]
        if state.get("result"):
            reply += f"\n\nResult: {state['result']}"
        await updater.add_artifact([new_text_part(reply)], name="answer")
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel not supported in this lab")


def create_app() -> Starlette:
    handler = DefaultRequestHandler(agent_executor=NovaCityExecutor(), task_store=InMemoryTaskStore(),
                                    agent_card=CARD)
    routes = create_agent_card_routes(CARD) + create_jsonrpc_routes(handler, rpc_url="/a2a")
    return Starlette(routes=routes)


app = create_app()

if __name__ == "__main__":
    import uvicorn
    print(f"A2A agent on {BASE_URL}  (card: {BASE_URL}/.well-known/agent-card.json)")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
