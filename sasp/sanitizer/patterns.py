"""
SASP Injection Pattern Library

Regex patterns for detecting injection attacks in input data.
Used by sanitizers to protect ML models and LLM agents.
"""

import re
from typing import Dict, Pattern

# Prompt injection patterns targeting LLMs
PROMPT_INJECTION_PATTERNS: Dict[str, Pattern] = {
    "ignore_instructions": re.compile(
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
        re.IGNORECASE
    ),
    "new_instructions": re.compile(
        r"(new|actual|real)\s+instructions?\s*:",
        re.IGNORECASE
    ),
    "system_prompt_leak": re.compile(
        r"(show|print|display|reveal|output)\s+(your\s+)?(system\s+)?(prompt|instructions)",
        re.IGNORECASE
    ),
    "role_switch": re.compile(
        r"you\s+are\s+(now\s+(?:actually\s+)?|actually\s+)(a|an)\s+",
        re.IGNORECASE
    ),
    "jailbreak_dan": re.compile(
        r"(DAN|do\s+anything\s+now|developer\s+mode)",
        re.IGNORECASE
    ),
    "base64_injection": re.compile(
        r"base64\s*:\s*[A-Za-z0-9+/=]{20,}",
        re.IGNORECASE
    ),
    "markdown_injection": re.compile(
        r"\[.*?\]\(javascript:|data:text/html",
        re.IGNORECASE
    ),
    "xml_injection": re.compile(
        r"<\s*(script|system|admin|root)\s*>",
        re.IGNORECASE
    ),
}

# SQL injection patterns
SQL_INJECTION_PATTERNS: Dict[str, Pattern] = {
    "sql_union": re.compile(
        r"union\s+(all\s+)?select",
        re.IGNORECASE
    ),
    "sql_or_true": re.compile(
        r"'\s*or\s+'?\d*'?\s*=\s*'?\d*",
        re.IGNORECASE
    ),
    "sql_comment": re.compile(
        r"(--|#|/\*)",
    ),
    "sql_drop": re.compile(
        r"drop\s+(table|database)",
        re.IGNORECASE
    ),
}

# Command injection patterns
COMMAND_INJECTION_PATTERNS: Dict[str, Pattern] = {
    "shell_pipe": re.compile(
        r"\|\s*(cat|ls|rm|wget|curl|nc|bash|sh|python|perl)",
        re.IGNORECASE
    ),
    "shell_semicolon": re.compile(
        r";\s*(cat|ls|rm|wget|curl|nc|bash|sh|python|perl)",
        re.IGNORECASE
    ),
    "shell_backtick": re.compile(
        r"`[^`]+`",
    ),
    "shell_subshell": re.compile(
        r"\$\([^)]+\)",
    ),
}

# Data exfiltration patterns
EXFILTRATION_PATTERNS: Dict[str, Pattern] = {
    "webhook_url": re.compile(
        r"https?://[^\s]+\.(requestbin|webhook\.site|pipedream|ngrok)",
        re.IGNORECASE
    ),
    "data_url": re.compile(
        r"data:[^;]+;base64,",
        re.IGNORECASE
    ),
}

# Model evasion patterns (adversarial)
EVASION_PATTERNS: Dict[str, Pattern] = {
    "unicode_homoglyph": re.compile(
        r"[\u0400-\u04FF]",  # Cyrillic lookalikes
    ),
    "zero_width": re.compile(
        r"[\u200B-\u200F\u2060\uFEFF]",  # Zero-width characters
    ),
    "rtl_override": re.compile(
        r"[\u202A-\u202E]",  # Right-to-left override
    ),
}

# Combined pattern dictionary
INJECTION_PATTERNS: Dict[str, Pattern] = {
    **PROMPT_INJECTION_PATTERNS,
    **SQL_INJECTION_PATTERNS,
    **COMMAND_INJECTION_PATTERNS,
    **EXFILTRATION_PATTERNS,
    **EVASION_PATTERNS,
}


def get_patterns_by_category(category: str) -> Dict[str, Pattern]:
    """
    Get patterns for a specific attack category.
    
    Args:
        category: One of 'prompt', 'sql', 'command', 'exfiltration', 'evasion'
        
    Returns:
        Dictionary of pattern name to compiled regex
    """
    categories = {
        "prompt": PROMPT_INJECTION_PATTERNS,
        "sql": SQL_INJECTION_PATTERNS,
        "command": COMMAND_INJECTION_PATTERNS,
        "exfiltration": EXFILTRATION_PATTERNS,
        "evasion": EVASION_PATTERNS,
    }
    return categories.get(category, {})


def check_all_patterns(text: str) -> Dict[str, list]:
    """
    Check text against all injection patterns.
    
    Args:
        text: Text to check
        
    Returns:
        Dictionary of category to list of matched pattern names
    """
    results = {}
    
    for category, patterns in [
        ("prompt", PROMPT_INJECTION_PATTERNS),
        ("sql", SQL_INJECTION_PATTERNS),
        ("command", COMMAND_INJECTION_PATTERNS),
        ("exfiltration", EXFILTRATION_PATTERNS),
        ("evasion", EVASION_PATTERNS),
    ]:
        matches = []
        for name, pattern in patterns.items():
            if pattern.search(text):
                matches.append(name)
        if matches:
            results[category] = matches
    
    return results
