"""SASP agent tools for querying Splunk, ISE, threat intel, and other data sources."""

from .splunk_query import run as _splunk_query
from .ise_lookup import run as _ise_lookup
from .asset_lookup import run as _asset_lookup
from .threat_intel import run as _threat_intel
from .baseline_query import run as _baseline_query
from .mitre_mapper import run as _mitre_mapper

TOOL_REGISTRY = {
    "splunk_query": _splunk_query,
    "ise_lookup": _ise_lookup,
    "asset_lookup": _asset_lookup,
    "threat_intel": _threat_intel,
    "baseline_query": _baseline_query,
    "mitre_mapper": _mitre_mapper,
}

__all__ = ["TOOL_REGISTRY"]
