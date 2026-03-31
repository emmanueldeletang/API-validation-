# JSON Schema Validation API

A Python API that validates JSON payloads against predefined schemas and returns business-friendly error messages, including deep sub-schema error detection.

## Project Structure

```
API validation/
├── api.py                      # FastAPI server
├── client.py                   # Client program that consumes the API
├── schemas/
│   └── order_schema.json       # Sample order schema with nested sub-schemas
├── requirements.txt
└── README.md
```

## Setup

```bash
pip install -r requirements.txt
```

## Usage

### Start the API

```bash
python api.py
```

The server starts on `http://127.0.0.1:8000`. Interactive docs available at `http://127.0.0.1:8000/docs`.

### Run the Client

```bash
python client.py
```

Sends three test payloads (valid, invalid with sub-schema errors, empty) and displays the results.

## API Endpoints

| Method | Endpoint     | Description                                  |
|--------|-------------|----------------------------------------------|
| POST   | `/validate` | Validate a JSON payload against a schema     |
| GET    | `/schemas`  | List all available schema names              |
| GET    | `/health`   | Health check                                 |

### POST /validate

**Request body:**

```json
{
  "schema_name": "order_schema",
  "payload": { ... }
}
```

**Response:**

```json
{
  "valid": false,
  "schema_name": "order_schema",
  "error_count": 2,
  "errors": [
    {
      "json_path": "customer.email",
      "message": "Missing required field: 'email'",
      "validator": "required",
      "business_field": "Customer Email",
      "sub_schema": "customer"
    },
    {
      "json_path": "items[0].quantity",
      "message": "Value 0 is below the minimum of 1",
      "validator": "minimum",
      "business_field": "Item Quantity",
      "sub_schema": "order_item",
      "invalid_value": 0
    }
  ]
}
```

## Error Detail Fields

| Field            | Description                                                    |
|-----------------|----------------------------------------------------------------|
| `json_path`      | Dotted path to the invalid field (e.g. `items[0].options.size`) |
| `message`        | Human-readable error description                               |
| `validator`      | JSON Schema validator that failed (`required`, `pattern`, `enum`, etc.) |
| `business_field` | Business-friendly label (e.g. "Item Quantity", "Shipping City") |
| `sub_schema`     | Name of the sub-schema where the error occurred (`customer`, `address`, `order_item`, `item_options`) |
| `invalid_value`  | The rejected value (scalar values only)                        |

## Schema: Order

The included `order_schema.json` defines an order with four nested sub-schemas:

- **customer** — `customer_id`, `name`, `email`, `phone`
- **address** — `street`, `city`, `state`, `postal_code`, `country`
- **order_item** — `product_id`, `product_name`, `quantity`, `unit_price`, `options`
- **item_options** — `size`, `color`, `gift_wrap`

### Adding New Schemas

Drop a `.json` file in the `schemas/` folder. It will be auto-loaded at startup using the filename (without extension) as the schema name. Add business field mappings in `BUSINESS_CONTEXT` in `api.py` for human-readable labels.
