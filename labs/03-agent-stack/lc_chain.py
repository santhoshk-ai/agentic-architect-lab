"""
Block 3 (extra, 10 min) - the same triage done the LangChain way, to compare with triage.py.

    prompt template | chat model .with_structured_output(Triage)

init_chat_model() hides the provider: "bedrock_converse" (Nova 2 Lite) or "google_genai" (Gemini).
Needs real credentials (no mock). Run:  python lc_chain.py
"""
import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate

from triage import FEW_SHOT, SYSTEM, TESTS, Triage

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "bedrock")
if PROVIDER == "gemini":
    model = init_chat_model(os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"), model_provider="google_genai")
else:
    model = init_chat_model(os.getenv("BEDROCK_MODEL", "us.amazon.nova-2-lite-v1:0"),
                            model_provider="bedrock_converse", region_name=os.getenv("AWS_REGION", "us-east-1"))

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM),
    ("human", FEW_SHOT.replace("{", "{{").replace("}", "}}") + "\n<message>{message}</message>"),
])
chain = prompt | model.with_structured_output(Triage)

if __name__ == "__main__":
    for msg in TESTS:
        print(chain.invoke({"message": msg}).model_dump_json(), "<-", msg)
