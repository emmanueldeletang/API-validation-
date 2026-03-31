"""
Client program that consumes the JSON Schema Validation API.

Sends sample payloads (valid and invalid, including sub-schema errors)
and displays the business-friendly error information returned by the API.
"""

import json
import sys
import requests

API_URL = "http://127.0.0.1:8000"

# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------

VALID_ORDER = {
    "order_id": "ORD-123456",
    "customer": {
        "customer_id": "CUST-00001",
        "name": "Alice Martin",
        "email": "alice@example.com",
        "phone": "+33 6 12 34 56 78",
    },
    "items": [
        {
            "product_id": "PROD-0001",
            "product_name": "Wireless Headphones",
            "quantity": 2,
            "unit_price": 79.99,
            "options": {"color": "Black", "gift_wrap": True},
        }
    ],
    "shipping_address": {
        "street": "10 Rue de Rivoli",
        "city": "Paris",
        "postal_code": "75001",
        "country": "FR",
    },
}

INVALID_ORDER_MANY_ERRORS = {
    # order_id wrong format
    "order_id": "BAD-ID",
    # customer sub-schema errors
    "customer": {
        "customer_id": "123",           # wrong pattern
        "name": "",                      # too short (minLength: 1)
        # missing "email" (required)
        "phone": "abc",                  # wrong pattern
    },
    # items[0] sub-schema errors
    "items": [
        {
            "product_id": "NOPE",        # wrong pattern
            "product_name": "Keyboard",
            "quantity": 0,               # below minimum (1)
            "unit_price": -5,            # below minimum (0.01)
            "options": {
                "size": "XXXL",          # not in enum
                "color": "",             # too short
                "gift_wrap": "yes",      # wrong type (should be boolean)
            },
        },
        {
            # missing product_id, product_name (required)
            "quantity": 1000,            # above maximum (999)
            "unit_price": 10.00,
        },
    ],
    # shipping_address sub-schema errors
    "shipping_address": {
        "street": "123 Main St",
        "city": "Springfield",
        "postal_code": "!!!!!",          # wrong pattern
        "country": "XX",                 # not in enum
    },
    # extra field that shouldn't be here
    "unknown_field": True,
    # discount_code wrong format
    "discount_code": "bad",
    # notes too long
    "notes": "x" * 501,
}

MISSING_REQUIRED_FIELDS = {
    # Missing order_id, customer, items, shipping_address
}

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

SEPARATOR = "=" * 72
SUB_SEP = "-" * 72


def print_header(title: str) -> None:
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def print_error(i: int, err: dict) -> None:
    print(f"\n  Error #{i + 1}")
    print(f"    Path            : {err['json_path']}")
    if err.get("business_field"):
        print(f"    Business Field  : {err['business_field']}")
    if err.get("sub_schema"):
        print(f"    Sub-Schema      : {err['sub_schema']}")
    print(f"    Issue           : {err['message']}")
    print(f"    Validator       : {err['validator']}")
    if err.get("invalid_value") is not None:
        print(f"    Invalid Value   : {err['invalid_value']}")


def send_and_display(label: str, payload: dict) -> None:
    """Send a validation request and display results."""
    print_header(label)

    try:
        resp = requests.post(
            f"{API_URL}/validate",
            json={"schema_name": "order_schema", "payload": payload},
            timeout=10,
        )
    except requests.ConnectionError:
        print("  [ERROR] Cannot connect to the API. Is it running on port 8000?")
        return

    if resp.status_code == 404:
        print(f"  [ERROR] {resp.json()['detail']}")
        return

    data = resp.json()
    status = "VALID" if data["valid"] else "INVALID"
    print(f"\n  Result       : {status}")
    print(f"  Schema       : {data['schema_name']}")
    print(f"  Error count  : {data['error_count']}")

    if data["errors"]:
        print(f"\n{SUB_SEP}")
        print("  Detailed Errors:")
        print(SUB_SEP)
        for i, err in enumerate(data["errors"]):
            print_error(i, err)
    else:
        print("\n  No errors found — payload is fully valid.")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # 1) Check API health
    try:
        health = requests.get(f"{API_URL}/health", timeout=5)
        health.raise_for_status()
    except requests.ConnectionError:
        print("[ERROR] API is not running. Start it with:  python api.py")
        sys.exit(1)

    # 2) List available schemas
    schemas = requests.get(f"{API_URL}/schemas", timeout=5).json()
    print(f"Available schemas: {schemas['schemas']}")

    # 3) Send test payloads
    send_and_display("Test 1: Valid Order", VALID_ORDER)
    send_and_display("Test 2: Many Errors (including sub-schema)", INVALID_ORDER_MANY_ERRORS)
    send_and_display("Test 3: Missing All Required Fields", MISSING_REQUIRED_FIELDS)


if __name__ == "__main__":
    main()
