"""Core logic: unstructured text -> validated structured JSON using Groq.

Why json_object mode + Pydantic?  Groq guarantees syntactically valid JSON in
json_object mode, but not that it matches OUR schema. So we put the JSON Schema
in the prompt, then validate with Pydantic and retry once with the error text.
"""
import json
import logging

from groq import APIConnectionError, AuthenticationError, Groq, RateLimitError
from pydantic import BaseModel, ValidationError

from . import config
from .schemas import SCHEMAS, DocType

log = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Base class; `status` is the HTTP status the API should return."""
    status = 500


class EmptyInputError(ExtractionError):
    status = 422


class MissingKeyError(ExtractionError):
    status = 500


class RateLimitedError(ExtractionError):
    status = 429


class UpstreamError(ExtractionError):
    status = 502


class NoDataFoundError(ExtractionError):
    status = 422


def _system_prompt(schema: type[BaseModel], doc_type: DocType) -> str:
    return (
        f"You extract data from a {doc_type.value}. "
        "Reply with ONE JSON object only, matching this JSON Schema exactly:\n"
        f"{json.dumps(schema.model_json_schema())}\n"
        "Rules: use ONLY facts present in the text; never guess or invent. "
        "Use null for missing scalar fields and [] for missing lists. "
        "Numbers must be plain numbers (no currency symbols or commas)."
    )


def _is_empty(obj: BaseModel) -> bool:
    """True when the model returned nothing useful (all null / empty)."""
    return not any(v not in (None, [], "") for v in obj.model_dump().values())


def _check_invoice(data: dict) -> list[str]:
    """Cheap sanity checks so wrong math is flagged, not silently trusted."""
    warnings: list[str] = []
    items = data.get("line_items") or []
    sub, tax, total = data.get("subtotal"), data.get("tax"), data.get("total")
    item_sum = sum(i["total"] for i in items if i.get("total") is not None)
    if sub is not None and items and abs(item_sum - sub) > 0.01:
        warnings.append(f"Line items sum to {item_sum}, but subtotal is {sub}.")
    if None not in (sub, tax, total) and abs(sub + tax - total) > 0.01:
        warnings.append(f"Subtotal + tax = {sub + tax}, but total is {total}.")
    return warnings


def _model_options() -> dict:
    """gpt-oss models are reasoning models: keep effort low so extraction stays fast."""
    if config.GROQ_MODEL.startswith("openai/gpt-oss"):
        return {"extra_body": {"reasoning_effort": "low"}}
    return {}


def _get_client() -> Groq:
    if not config.GROQ_API_KEY:
        raise MissingKeyError(
            "GROQ_API_KEY is not set. Create a free key at "
            "https://console.groq.com/keys and add it to .env, then restart."
        )
    return Groq(api_key=config.GROQ_API_KEY)


def extract(text: str, doc_type: DocType, client: Groq | None = None):
    """Return (validated_dict, warnings). Raises ExtractionError subclasses."""
    text = (text or "").strip()
    if not text:
        raise EmptyInputError("Input text is empty. Paste a resume or invoice.")
    if len(text) > config.MAX_INPUT_CHARS:
        raise EmptyInputError(
            f"Input is too long ({len(text)} chars). Limit is {config.MAX_INPUT_CHARS}."
        )

    client = client or _get_client()
    schema = SCHEMAS[doc_type]
    messages = [
        {"role": "system", "content": _system_prompt(schema, doc_type)},
        {"role": "user", "content": text},
    ]

    for attempt in (1, 2):  # one retry on invalid output
        try:
            resp = client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
                **_model_options(),
            )
        except RateLimitError as e:
            raise RateLimitedError(
                "Groq rate limit reached (free tier). Wait a few seconds and retry."
            ) from e
        except AuthenticationError as e:
            raise MissingKeyError("Groq rejected the API key. Check GROQ_API_KEY.") from e
        except APIConnectionError as e:
            raise UpstreamError("Could not reach Groq. Check your internet.") from e

        raw = resp.choices[0].message.content or ""
        try:
            parsed = schema.model_validate_json(raw)
            break
        except (ValidationError, ValueError) as e:
            log.warning("Attempt %s produced invalid output: %s", attempt, e)
            if attempt == 2:
                raise UpstreamError(
                    "The model returned output that did not match the schema."
                ) from e
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"Invalid. Fix this error and reply with JSON only:\n{e}"},
            ]

    if _is_empty(parsed):
        raise NoDataFoundError(f"No {doc_type.value} data found in the text.")

    data = parsed.model_dump()
    warnings = _check_invoice(data) if doc_type == DocType.invoice else []
    return data, warnings
