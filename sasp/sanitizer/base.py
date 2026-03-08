"""
SASP Input Sanitizer - Base Class

Provides the foundation for data source-specific sanitizers.
Protects ML models and LLM agents from injection attacks.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import logging
import json

from .patterns import INJECTION_PATTERNS

logger = logging.getLogger(__name__)


@dataclass
class SanitizationResult:
    """Result of sanitization operation."""
    original: Any
    sanitized: Any
    is_clean: bool
    threats_detected: List[str]
    modifications: List[str]


class BaseSanitizer(ABC):
    """
    Base class for input sanitization.
    
    All data entering the SASP pipeline must pass through
    a sanitizer to protect against:
    - Prompt injection attacks
    - SQL injection
    - Command injection
    - Data exfiltration attempts
    - Model evasion patterns
    """
    
    def __init__(self, 
                 strict_mode: bool = True,
                 log_originals: bool = True,
                 patterns: Optional[List[str]] = None):
        """
        Initialize sanitizer.
        
        Args:
            strict_mode: If True, reject suspicious input. If False, sanitize and pass.
            log_originals: If True, log original input for forensics.
            patterns: Custom injection patterns to check.
        """
        self.strict_mode = strict_mode
        self.log_originals = log_originals
        self.patterns = patterns or INJECTION_PATTERNS
    
    @abstractmethod
    def sanitize(self, data: Any) -> SanitizationResult:
        """
        Sanitize input data.
        
        Args:
            data: Raw input data
            
        Returns:
            SanitizationResult with sanitized data and metadata
        """
        pass
    
    @abstractmethod
    def validate_schema(self, data: Any) -> bool:
        """
        Validate data matches expected schema.
        
        Args:
            data: Input data
            
        Returns:
            True if valid, False otherwise
        """
        pass
    
    def check_injection_patterns(self, text: str) -> List[str]:
        """
        Check text for known injection patterns.
        
        Args:
            text: Text to check
            
        Returns:
            List of detected pattern names
        """
        detected = []
        for pattern_name, pattern_regex in self.patterns.items():
            if pattern_regex.search(text):
                detected.append(pattern_name)
        return detected
    
    def encode_special_chars(self, text: str) -> str:
        """
        Encode special characters to prevent injection.

        Args:
            text: Input text

        Returns:
            Encoded text
        """
        import html
        import unicodedata
        # Strip null bytes
        text = text.replace('\x00', '')
        # Remove zero-width characters
        import re
        text = re.sub(r'[\u200B-\u200F\u2060\uFEFF]', '', text)
        # NFKC normalize unicode
        text = unicodedata.normalize('NFKC', text)
        # HTML-encode special chars <>&'"
        text = html.escape(text, quote=True)
        return text
    
    def truncate(self, text: str, max_length: int = 10000) -> str:
        """
        Truncate text to prevent DoS via large inputs.
        
        Args:
            text: Input text
            max_length: Maximum allowed length
            
        Returns:
            Truncated text
        """
        if len(text) > max_length:
            logger.warning(f"Truncating input from {len(text)} to {max_length}")
            return text[:max_length]
        return text
    
    def log_original(self, data: Any, threats: List[str]) -> None:
        """
        Log original input for forensic analysis.
        
        Args:
            data: Original input
            threats: Detected threats
        """
        if self.log_originals:
            logger.warning(
                f"Sanitization event",
                extra={
                    "original_data": json.dumps(data) if isinstance(data, dict) else str(data),
                    "threats_detected": threats,
                    "sanitizer": self.__class__.__name__
                }
            )
