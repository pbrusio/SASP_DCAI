"""Prompt template loader — loads and formats prompt templates with variable substitution."""

import logging
import os
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Directory containing prompt templates
TEMPLATE_DIR = Path(__file__).parent / "prompt_templates"

# Cache for loaded templates
_template_cache: Dict[str, str] = {}


class PromptLoader:
    """Loads and formats prompt templates for agent nodes."""

    def __init__(self, template_dir: Optional[Path] = None):
        self.template_dir = template_dir or TEMPLATE_DIR
        self._cache: Dict[str, str] = {}

    def load_template(self, name: str) -> str:
        """Load a template by name (without extension). Caches after first load."""
        if name in self._cache:
            return self._cache[name]

        template_path = self.template_dir / f"{name}.txt"
        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")

        template = template_path.read_text(encoding="utf-8")
        self._cache[name] = template
        logger.debug("Loaded prompt template: %s", name)
        return template

    def format_template(self, name: str, **kwargs) -> str:
        """Load a template and substitute variables. Uses {variable_name} syntax."""
        template = self.load_template(name)
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning("Missing template variable %s in %s, leaving placeholder", e, name)
            # Partial formatting — leave unresolved placeholders
            for key, value in kwargs.items():
                template = template.replace(f"{{{key}}}", str(value))
            return template

    def list_templates(self) -> list:
        """List available template names."""
        return [p.stem for p in self.template_dir.glob("*.txt")]

    def clear_cache(self):
        """Clear the template cache."""
        self._cache.clear()


# Module-level convenience instance
_default_loader = None


def get_loader() -> PromptLoader:
    """Get the default PromptLoader instance."""
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptLoader()
    return _default_loader


def load_template(name: str) -> str:
    """Convenience function to load a template."""
    return get_loader().load_template(name)


def format_template(name: str, **kwargs) -> str:
    """Convenience function to format a template."""
    return get_loader().format_template(name, **kwargs)
