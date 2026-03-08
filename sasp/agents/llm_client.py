"""SASP LLM Client — shared OpenAI-compatible API client for all agents.

Uses the OpenAI chat completions format (/v1/chat/completions), which is
supported by LM Studio, vLLM, Ollama (/v1/ endpoint), TGI, and cloud
providers. Swapping the serving layer requires only changing the endpoint
URL and model name in AgentConfig — zero code changes.
"""

import logging
import re
import time
from typing import List, Dict, Optional

import requests

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds, multiplied by attempt number

# Some models (e.g. Nemotron) emit <think>...</think> reasoning traces
# before the actual response. We preserve the thinking for audit/logging
# but separate it from the structured output for JSON parsing.
_THINK_PATTERN = re.compile(r"<think>(.*?)</think>\s*", re.DOTALL)


def split_thinking(text: str) -> tuple:
    """Separate <think>...</think> reasoning from the response body.

    Returns:
        (thinking, response) — thinking is the chain-of-thought text
        (empty string if none), response is everything after the tags.
    """
    match = _THINK_PATTERN.search(text)
    if match:
        thinking = match.group(1).strip()
        response = _THINK_PATTERN.sub("", text).strip()
        return thinking, response
    return "", text.strip()


def chat_completion(
    endpoint: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.1,
    max_tokens: int = 4096,
    timeout: int = 60,
    raw: bool = False,
) -> str:
    """Send a chat completion request and return the assistant's response text.

    By default, strips ``<think>`` tags and returns the response body only
    (suitable for JSON parsing in agent nodes). Set ``raw=True`` to return
    the full model output including reasoning traces (suitable for the chat UI
    where analysts benefit from seeing the model's thought process).

    Args:
        endpoint: Base URL of the OpenAI-compatible server (e.g. http://localhost:1234).
        model: Model identifier as reported by the server.
        messages: List of {"role": ..., "content": ...} message dicts.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens to generate.
        timeout: HTTP request timeout in seconds.
        raw: If True, return full output including <think> tags.

    Returns:
        The assistant's response text, or empty string on failure.
    """
    url = f"{endpoint}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            raw_content = data["choices"][0]["message"]["content"]
            if raw:
                return raw_content
            thinking, response = split_thinking(raw_content)
            if thinking:
                logger.debug("Model reasoning: %s", thinking[:500])
            return response
        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            logger.warning("LLM call attempt %d/%d failed: %s", attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

    return ""


def generate(
    endpoint: str,
    model: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    timeout: int = 60,
) -> str:
    """Convenience wrapper: builds a messages list from a prompt string.

    Args:
        endpoint: Base URL of the OpenAI-compatible server.
        model: Model identifier.
        prompt: The user prompt text.
        system_prompt: Optional system prompt prepended to messages.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens to generate.
        timeout: HTTP request timeout in seconds.

    Returns:
        The assistant's response text, or empty string on failure.
    """
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    return chat_completion(
        endpoint=endpoint,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
