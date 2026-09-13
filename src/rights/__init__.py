"""Wave-1b economic-rights stubs.

Unit of value is an economic right (option / 505(b)(2) / method-of-use),
not a ranked list. Live clients are unwired: stubs raise NotConfigured or
write empty_stub. Empty confidence never implies ownability.
"""

from src.rights.exceptions import NotConfigured
from src.rights.query import decision_required, ownability_query
from src.rights.schema import SCHEMA_VERSION, REQUIRED_BLOCKS, RightsRecord, empty_rights

__all__ = [
    "NotConfigured",
    "SCHEMA_VERSION",
    "REQUIRED_BLOCKS",
    "RightsRecord",
    "empty_rights",
    "ownability_query",
    "decision_required",
]
