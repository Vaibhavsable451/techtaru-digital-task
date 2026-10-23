"""
Tool-calling agent built directly on the Groq API (OpenAI-compatible function calling, no LangChain wrapper).

Flow:
  user message -> LLM picks tool (or none) -> Python executes tool
  -> result sent back to LLM -> final natural-language answer
"""

import json
import os

import json
import os

import groq
from dotenv import load_dotenv
from groq import Groq

from .tools import execute_tool

load_dotenv()

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
BOT_NAME = os.getenv("BOT_NAME", "Robo")
MAX_TOOL_ROUNDS = 5
MAX_INPUT_CHARS = 2000

SYSTEM_PROMPT = (
    f"Your name is {BOT_NAME}. If asked who you are, introduce yourself as {BOT_NAME}, a friendly AI assistant. "
    "You are a helpful assistant with access to tools for weather and stock prices. "
    "Use a tool only when the user's request needs live weather or stock data. "
    "For greetings and general knowledge questions, answer directly without tools. "
    "Convert company names to ticker symbols (e.g. Apple -> AAPL). "
    "If a tool returns an error, explain it honestly and NEVER invent weather or prices."
)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city (temperature, humidity, wind, conditions).",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name, e.g. Pune"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "Get the latest stock price for a ticker symbol (e.g. AAPL for Apple).",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "Stock ticker, e.g. AAPL"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_stock_value",
            "description": "Calculate the total value of a number of shares of a stock (price x quantity).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock ticker, e.g. TSLA"},
                    "quantity": {"type": "number", "description": "Number of shares"},
                },
                "required": ["symbol", "quantity"],
            },
        },
    },
]

_client = None


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"), timeout=30.0, max_retries=2)
    return _client


def run_agent_traced(user_message: str, client=None):
    """Run one user turn. Returns (final_answer, list_of_tool_names_used)."""
    used = []
    # ---- Edge case: empty / invalid input (handled BEFORE calling the LLM) ----
    if not isinstance(user_message, str) or not user_message.strip():
        return "Please enter a question.", used
    user_message = user_message.strip()
    if len(user_message) > MAX_INPUT_CHARS:
        return f"Your message is too long. Please keep it under {MAX_INPUT_CHARS} characters.", used
    if client is None:
        if not os.getenv("GROQ_API_KEY"):
            return "Groq API key is not configured. Add GROQ_API_KEY to your .env file.", used
        client = get_client()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    retried_bad_call = False

    try:
        rounds = 0
        while rounds < MAX_TOOL_ROUNDS:
            try:
                response = client.chat.completions.create(
                    model=MODEL, messages=messages, tools=TOOLS,
                    tool_choice="auto", temperature=0.2,
                )
            except groq.BadRequestError as exc:
                # Llama models occasionally emit a malformed tool call; retry once.
                if "tool_use_failed" in str(exc) and not retried_bad_call:
                    retried_bad_call = True
                    continue
                return f"The AI model could not process that request: {exc}", used

            rounds += 1
            msg = response.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:  # no tool needed -> this is the final answer
                return (msg.content or "").strip() or "Sorry, I could not generate a response.", used

            # Keep the model's tool-call message, then add each tool result.
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    result = {"success": False, "error": "Model produced invalid tool arguments."}
                else:
                    used.append(tc.function.name)
                    result = execute_tool(tc.function.name, args)  # Python executes, not the LLM
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })

        return "Sorry, I couldn't complete that request (too many tool steps). Please try rephrasing.", used

    # ---- Edge cases: LLM API failures ----
    except groq.RateLimitError:
        return "The AI service is rate-limited right now. Please wait a moment and try again.", used
    except groq.AuthenticationError:
        return "Groq authentication failed. Please check your GROQ_API_KEY.", used
    except groq.NotFoundError:
        return f"Model '{MODEL}' is not available. Set GROQ_MODEL in .env to a valid Groq model.", used
    except groq.APITimeoutError:
        return "The AI service timed out. Please try again.", used
    except groq.APIConnectionError:
        return "Could not connect to the AI service. Check your internet connection.", used
    except groq.APIStatusError as exc:
        return f"The AI service returned an error (HTTP {exc.status_code}). Please try again.", used
    except Exception as exc:
        return f"Unexpected error: {exc}", used


def run_agent(user_message: str, client=None) -> str:
    """Run one user turn through the agent and return only the final answer string."""
    return run_agent_traced(user_message, client)[0]