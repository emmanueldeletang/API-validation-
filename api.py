"""
JSON Schema Validation API

Validates incoming JSON data against predefined schemas and returns
business-friendly error messages, including deep sub-schema error detection.
"""

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from jsonschema import Draft7Validator, RefResolver, ValidationError

app = FastAPI(
    title="JSON Schema Validation API",
    description="Validates JSON payloads and returns business-friendly error details",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Schema registry – load all JSON schemas from the schemas/ folder
# ---------------------------------------------------------------------------
SCHEMA_DIR = Path(__file__).parent / "schemas"
_schema_registry: dict[str, dict] = {}


def _load_schemas() -> None:
    """Load every *.json file in the schemas directory into the registry."""
    if not SCHEMA_DIR.exists():
        return
    for schema_file in SCHEMA_DIR.glob("*.json"):
        key = schema_file.stem  # e.g. "order_schema"
        with open(schema_file, encoding="utf-8") as f:
            _schema_registry[key] = json.load(f)


_load_schemas()

# ---------------------------------------------------------------------------
# Business-context mapping
# ---------------------------------------------------------------------------
# Maps JSON-path prefixes to human-readable business context so that raw
# validation errors become meaningful to end users.
BUSINESS_CONTEXT: dict[str, dict[str, str]] = {
    "order_schema": {
        "order_id": "Order Reference",
        "customer": "Customer Information",
        "customer.customer_id": "Customer ID",
        "customer.name": "Customer Name",
        "customer.email": "Customer Email",
        "customer.phone": "Customer Phone",
        "items": "Order Items",
        "items[*].product_id": "Product ID",
        "items[*].product_name": "Product Name",
        "items[*].quantity": "Item Quantity",
        "items[*].unit_price": "Item Price",
        "items[*].options": "Product Options",
        "items[*].options.size": "Size Selection",
        "items[*].options.color": "Color Selection",
        "items[*].options.gift_wrap": "Gift Wrap Option",
        "shipping_address": "Shipping Address",
        "shipping_address.street": "Shipping Street",
        "shipping_address.city": "Shipping City",
        "shipping_address.postal_code": "Shipping Postal Code",
        "shipping_address.country": "Shipping Country",
        "billing_address": "Billing Address",
        "billing_address.street": "Billing Street",
        "billing_address.city": "Billing City",
        "billing_address.postal_code": "Billing Postal Code",
        "billing_address.country": "Billing Country",
        "discount_code": "Discount Code",
        "notes": "Order Notes",
    }
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_path(path_parts: list) -> str:
    """Convert a deque of path parts to a dotted JSON path."""
    parts: list[str] = []
    for p in path_parts:
        if isinstance(p, int):
            # Replace actual index with [*] for lookup, keep index for display
            parts.append(f"[{p}]")
        else:
            parts.append(str(p))
    return ".".join(parts).replace(".[", "[")


def _lookup_business_label(schema_key: str, json_path: str) -> str | None:
    """Try to find a business label for the given path.

    Supports exact match and wildcard matching (replacing [N] with [*]).
    """
    ctx = BUSINESS_CONTEXT.get(schema_key, {})
    if json_path in ctx:
        return ctx[json_path]
    # Try wildcard: items[0].quantity -> items[*].quantity
    import re
    wildcard_path = re.sub(r"\[\d+\]", "[*]", json_path)
    if wildcard_path in ctx:
        return ctx[wildcard_path]
    return None


def _friendly_message(error: ValidationError) -> str:
    """Turn a jsonschema ValidationError into a human-readable message."""
    if error.validator == "required":
        missing = error.message.split("'")[1] if "'" in error.message else error.message
        return f"Missing required field: '{missing}'"
    if error.validator == "type":
        return f"Expected type '{error.validator_value}', got '{type(error.instance).__name__}'"
    if error.validator == "pattern":
        return f"Value '{error.instance}' does not match the expected format: {error.validator_value}"
    if error.validator == "enum":
        return f"Value '{error.instance}' is not allowed. Accepted values: {error.validator_value}"
    if error.validator == "minItems":
        return f"At least {error.validator_value} item(s) required"
    if error.validator == "minLength":
        return f"Value is too short (minimum {error.validator_value} character(s))"
    if error.validator == "maxLength":
        return f"Value is too long (maximum {error.validator_value} character(s))"
    if error.validator == "minimum":
        return f"Value {error.instance} is below the minimum of {error.validator_value}"
    if error.validator == "maximum":
        return f"Value {error.instance} exceeds the maximum of {error.validator_value}"
    if error.validator == "additionalProperties":
        return f"Unexpected field found: {error.message}"
    if error.validator == "format":
        return f"Value '{error.instance}' is not a valid {error.validator_value}"
    return error.message


def _build_error_detail(
    error: ValidationError,
    schema_key: str,
) -> dict[str, Any]:
    """Build a single error detail dict from a ValidationError."""
    path = _json_path(list(error.absolute_path))
    business_label = _lookup_business_label(schema_key, path) if path else None

    # Determine which sub-schema the error belongs to
    schema_path_parts = list(error.absolute_schema_path)
    sub_schema = None
    for i, part in enumerate(schema_path_parts):
        if part == "$defs" and i + 1 < len(schema_path_parts):
            sub_schema = schema_path_parts[i + 1]
            break

    detail: dict[str, Any] = {
        "json_path": path or "(root)",
        "message": _friendly_message(error),
        "validator": error.validator,
    }
    if business_label:
        detail["business_field"] = business_label
    if sub_schema:
        detail["sub_schema"] = sub_schema
    if error.instance is not None and not isinstance(error.instance, (dict, list)):
        detail["invalid_value"] = error.instance

    return detail


def validate_payload(schema_key: str, data: Any) -> list[dict[str, Any]]:
    """Validate *data* against the schema identified by *schema_key*.

    Returns a list of error detail dicts (empty list ➜ valid).
    Sub-schema errors are fully expanded so every leaf error is reported.
    """
    schema = _schema_registry.get(schema_key)
    if schema is None:
        raise ValueError(f"Unknown schema: '{schema_key}'")

    resolver = RefResolver.from_schema(schema)
    validator = Draft7Validator(schema, resolver=resolver, format_checker=None)

    errors: list[dict[str, Any]] = []
    for error in validator.iter_errors(data):
        # If the error has sub-errors (e.g. from anyOf/oneOf), expand them
        if error.context:
            for sub_error in error.context:
                errors.append(_build_error_detail(sub_error, schema_key))
        else:
            errors.append(_build_error_detail(error, schema_key))

    # Sort errors by json_path for deterministic output
    errors.sort(key=lambda e: e["json_path"])
    return errors


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ValidationRequest(BaseModel):
    schema_name: str
    payload: dict[str, Any]


class ErrorDetail(BaseModel):
    json_path: str
    message: str
    validator: str
    business_field: str | None = None
    sub_schema: str | None = None
    invalid_value: Any | None = None


class ValidationResponse(BaseModel):
    valid: bool
    schema_name: str
    error_count: int
    errors: list[ErrorDetail]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/schemas")
def list_schemas() -> dict[str, list[str]]:
    """List all available schema names."""
    return {"schemas": list(_schema_registry.keys())}


@app.post("/validate", response_model=ValidationResponse)
def validate(request: ValidationRequest) -> ValidationResponse:
    """Validate a JSON payload against a named schema."""
    if request.schema_name not in _schema_registry:
        raise HTTPException(
            status_code=404,
            detail=f"Schema '{request.schema_name}' not found. "
                   f"Available: {list(_schema_registry.keys())}",
        )

    errors = validate_payload(request.schema_name, request.payload)

    return ValidationResponse(
        valid=len(errors) == 0,
        schema_name=request.schema_name,
        error_count=len(errors),
        errors=[ErrorDetail(**e) for e in errors],
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Run with:  python api.py  (or uvicorn api:app --reload)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
