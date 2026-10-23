"""Simple terminal chat: python cli.py"""
from app.agent import run_agent

print("AI Agent with Tools. Type 'exit' to quit.")
while True:
    try:
        text = input("\nYou: ")
    except (EOFError, KeyboardInterrupt):
        break
    if text.strip().lower() in {"exit", "quit"}:
        break
    print("Agent:", run_agent(text))
