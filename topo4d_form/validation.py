from jsonschema import Draft7Validator
import json
import requests
import os
from . import TOPO4D_SCHEMA_URL

# Required keys for the UI to mark with an asterisk
# Aligns with schema.json: require properties.datetime and topo4d:data_type
model_required_keys = [
    "datetime",
    "topo4d_data_type",
    "trafometa_reference_epoch",
    # Asset convenience
    "href",
]


def _load_schema():
    schema_path = TOPO4D_SCHEMA_URL
    response = requests.get(schema_path)
    response.raise_for_status()
    schema = response.json()
    return schema



_SCHEMA = _load_schema()
_VALIDATOR = Draft7Validator(_SCHEMA)


def validate_topo4d_item(item_dict):
    """Validate a full STAC Item dict against the topo4d schema.

    Returns a user-friendly error string or None if valid.
    """
    errors = list(_VALIDATOR.iter_errors(item_dict))
    if not errors:
        return None
    # Build a concise message
    msgs = []
    for e in errors:
        path = "/".join([str(p) for p in e.path])
        msgs.append(f"{path}: {e.message}")
    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for m in msgs:
        if m not in seen:
            uniq.append(m)
            seen.add(m)
    return "\n".join(uniq)
