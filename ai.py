from __future__ import annotations

import os
import re
import traceback
from typing import Iterable, Optional

from dotenv import load_dotenv
from google import genai


class UnsafeRequestError(Exception):
    """Raised when a prompt violates safety rules."""


class AIServiceError(Exception):
    """Raised when the AI service cannot complete."""


# Load environment variables so GOOGLE_API_KEY is available when running locally or in production.
load_dotenv()

_client: Optional[genai.Client] = None
_client_key: Optional[str] = None


def _log_debug(message: str) -> None:
    # Simple debug logger so errors are visible in the server console.
    print(f"[AI DEBUG] {message}", flush=True)

# Cached system prompt describing TALE language and constraints.
SYSTEM_PROMPT = """
You are an expert TALE code generator.
Always respond with TALE code only.
Never include markdown, backticks, comments, or explanations.
Never output Python or other languages.
Keep programs concise and free of unbounded or infinite loops.

TALE philosophy: readable, English-like programming for beginners.
Core syntax rules:
- Variables: x is 5
- Output: say x
- Input: ask name
- Condition:
  if x > 5
  say "big"
  else
  say "small"
  end
- Loops:
  repeat 5
  say "hello"
  end
- While loops:
  while x < 3
  add 1 to x
  end
- Functions:
  function add a b
  return a + b
  end
- Lists:
  list numbers is [1,2,3]
- Dictionary access: set scores player to 10, get scores player
- File IO: open "path" as f, write f "data", close f
- Flow: try / catch err / finally / end
- Blocks end with the word end on its own line.

Generation rules:
- Return only executable TALE code.
- No markdown, no backticks, no comments, no prose.
- Avoid dangerous content, system commands, hacking, or unbounded loops.
- Return full programs as needed; keep concise but do not truncate necessary code.
""".strip()

UNSAFE_PATTERNS = [
    r"\bhack(ing)?\b",
    r"\bexploit\b",
    r"\bsystem command\b",
    r"\bcommand prompt\b",
    r"\bterminal\b",
    r"\bshell\b",
    r"\bbash\b",
    r"\bpowershell\b",
    r"\bcmd\.exe\b",
    r"\binfinite loop\b",
    r"while\s+true",
    r"for\s+ever",
]


def _is_unsafe(text: str) -> bool:
    lowered = (text or "").lower()
    unsafe = any(re.search(pattern, lowered) for pattern in UNSAFE_PATTERNS)
    if unsafe:
        _log_debug("Prompt flagged as unsafe")
    return unsafe


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```[a-zA-Z0-9_-]*", "", cleaned)
    cleaned = re.sub(r"```$", "", cleaned)
    return cleaned.strip()


def _first_text(parts: Iterable) -> str:
    for part in parts:
        if hasattr(part, "text") and part.text:
            return str(part.text)
    return ""


def _blocked_reason(response) -> Optional[str]:
    feedback = getattr(response, "prompt_feedback", None)
    reason = getattr(feedback, "block_reason", None)
    if reason and str(reason).lower() not in {"block_reason_unspecified", ""}:
        _log_debug(f"Prompt blocked: {reason}")
        return str(reason)

    for cand in getattr(response, "candidates", []) or []:
        finish_reason = getattr(cand, "finish_reason", None)
        if finish_reason and "safety" in str(finish_reason).lower():
            _log_debug(f"Candidate blocked for safety: {finish_reason}")
            return str(finish_reason)
    return None


def _extract_text(response) -> str:
    reason = _blocked_reason(response)
    if reason:
        raise UnsafeRequestError("Unsafe request")

    primary = getattr(response, "text", "")
    if primary:
        _log_debug("Using primary response text")
        return primary

    _log_debug("Falling back to candidate parts for text")
    return _first_text(
        part
        for cand in getattr(response, "candidates", []) or []
        for part in getattr(getattr(cand, "content", None), "parts", []) or []
    )


def generate_tale_code(user_prompt: str) -> str:
    prompt = (user_prompt or "").strip()
    if not prompt:
        raise ValueError("Empty prompt")

    if _is_unsafe(prompt):
        raise UnsafeRequestError("Unsafe request")

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        _log_debug("GOOGLE_API_KEY missing or empty")
        raise AIServiceError("AI not configured")

    global _client, _client_key
    if _client is None or _client_key != api_key:
        _log_debug("(Re)initializing genai client")
        _client = genai.Client(api_key=api_key)
        _client_key = api_key
    else:
        _log_debug("Reusing existing genai client")

    composed = f"{SYSTEM_PROMPT}\n\nUser request:\n{prompt}\n\nReturn only TALE code with no comments."
    _log_debug(
        f"Calling model with prompt_len={len(prompt)} system_len={len(SYSTEM_PROMPT)}"
    )

    def _call_model() -> object:
        base_args = {
            "model": "gemini-2.5-flash",
            "contents": composed,
        }
        gen_cfg = {
            "temperature": 0.35,
            "response_mime_type": "text/plain",
        }

        try:
            return _client.models.generate_content(
                **base_args, generation_config=gen_cfg
            )
        except TypeError as exc:
            _log_debug(f"generation_config rejected: {exc}")
            try:
                return _client.models.generate_content(**base_args, config=gen_cfg)
            except TypeError as exc2:
                _log_debug(f"config rejected; retrying bare call: {exc2}")
                return _client.models.generate_content(**base_args)

    try:
        response = _call_model()
        _log_debug("Model call succeeded")
    except UnsafeRequestError:
        raise
    except Exception as exc:  # noqa: BLE001
        _log_debug(f"Model call failed: {type(exc).__name__}: {exc}")
        _log_debug(traceback.format_exc())
        raise AIServiceError(f"AI request failed: {exc}") from exc

    text = _extract_text(response)
    code = _strip_code_fences(text)
    _log_debug(f"Received code_len={len(code)}")

    if not code:
        _log_debug("AI returned empty response")
        raise AIServiceError("AI returned empty response")

    return code
