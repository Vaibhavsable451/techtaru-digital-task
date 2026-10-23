from fastapi import FastAPI
from pydantic import BaseModel

from .agent import run_agent

app = FastAPI(
    title="AI Agent with Tools",
    description="An AI agent that routes user intent to Python tools (weather, stocks).",
    version="1.0.0",
)


class ChatRequest(BaseModel):
    message: str = ""


class ChatResponse(BaseModel):
    response: str


@app.get("/")
def root():
    return {"message": "AI Agent with Tools is running. Open /docs to try it."}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    return {"response": run_agent(request.message)}
