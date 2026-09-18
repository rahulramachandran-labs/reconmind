"""The dbt-style project the synthetic warehouse pretends to have.

One definition feeds both the model YAML under ``dbt/models`` and the fake
``dbt/target/manifest.json``, so the two can never disagree.
"""

from typing import Any

PROJECT = "retail_recon"

RAW_COLUMNS: list[dict[str, Any]] = [
    {
        "name": "outlet_id",
        "data_type": "text",
        "description": "Store id as sent by the submitter (OUT-NNNN).",
        "tests": ["not_null"],
    },
    {
        "name": "location_id",
        "data_type": "text",
        "description": (
            "Physical location (LOC-NNNN). The id to trust when it disagrees with outlet_id."
        ),
        "tests": ["not_null"],
    },
    {
        "name": "transaction_id",
        "data_type": "text",
        "description": "Submitter transaction id. Dedup key part 1.",
        "tests": ["not_null"],
    },
    {
        "name": "upc_code",
        "data_type": "text",
        "description": "12-digit UPC. Dedup key part 3.",
        "tests": ["not_null"],
    },
    {
        "name": "channel_basket_id",
        "data_type": "text",
        "description": "Basket id (BSK-XXXXXXXX). Dedup key part 2.",
        "tests": ["not_null"],
    },
    {"name": "qty", "data_type": "integer", "description": "Units, negative for returns."},
    {"name": "amount", "data_type": "numeric(12,2)", "description": "Line amount after discounts."},
    {
        "name": "event_ts",
        "data_type": "timestamptz",
        "description": "When the sale happened (UTC).",
    },
    {
        "name": "submitter_file_name",
        "data_type": "text",
        "description": "Source file, SUBMITTERID_YYYYMMDD_HHMM_NAME.txt. Added by the loader.",
    },
]

MODELS: list[dict[str, Any]] = [
    {
        "name": "stg_transactions",
        "path": "staging/stg_transactions.yml",
        "description": (
            "Deduplicated line items. Latest submitter file wins on "
            "(transaction_id, channel_basket_id, upc_code); outlet ids are remapped through "
            "outlet_alias."
        ),
        "depends_on": ["source.retail_recon.raw.transactions", "model.retail_recon.dim_outlet"],
        "columns": [
            {
                "name": "outlet_id",
                "data_type": "text",
                "tests": [{"relationships": {"to": "ref('dim_outlet')", "field": "outlet_id"}}],
            },
            {"name": "location_id", "data_type": "text", "tests": ["not_null"]},
            {"name": "transaction_id", "data_type": "text", "tests": ["not_null"]},
            {"name": "upc_code", "data_type": "text", "tests": ["not_null"]},
            {"name": "channel_basket_id", "data_type": "text", "tests": ["not_null"]},
            {"name": "qty", "data_type": "integer"},
            {"name": "amount", "data_type": "numeric(12,2)"},
            {"name": "event_ts", "data_type": "timestamptz"},
            {"name": "business_date", "data_type": "date"},
            {"name": "submitter_id", "data_type": "text"},
            {"name": "submitter_file_name", "data_type": "text"},
        ],
        "tests": [
            {
                "dbt_utils.unique_combination_of_columns": {
                    "combination_of_columns": ["transaction_id", "channel_basket_id", "upc_code"]
                }
            }
        ],
    },
    {
        "name": "dim_outlet",
        "path": "marts/dim_outlet.yml",
        "description": "One row per active outlet, from outlet_location_map.",
        "depends_on": [],
        "columns": [
            {"name": "outlet_id", "data_type": "text", "tests": ["unique", "not_null"]},
            {"name": "location_id", "data_type": "text", "tests": ["unique", "not_null"]},
            {"name": "valid_from", "data_type": "date"},
            {"name": "valid_to", "data_type": "date"},
        ],
        "tests": [],
    },
    {
        "name": "fct_daily_sales",
        "path": "marts/fct_daily_sales.yml",
        "description": "Grain: business_date x outlet_id. What the morning dashboard reads.",
        "depends_on": ["model.retail_recon.stg_transactions"],
        "columns": [
            {"name": "business_date", "data_type": "date", "tests": ["not_null"]},
            {"name": "outlet_id", "data_type": "text", "tests": ["not_null"]},
            {"name": "location_id", "data_type": "text"},
            {"name": "line_items", "data_type": "integer"},
            {"name": "units", "data_type": "integer"},
            {"name": "revenue", "data_type": "numeric(14,2)"},
        ],
        "tests": [],
    },
]


def sources_yaml() -> dict[str, Any]:
    return {
        "version": 2,
        "sources": [
            {
                "name": "raw",
                "description": "Submitter files as loaded, one row per line item.",
                "tables": [
                    {
                        "name": "transactions",
                        "description": (
                            "Contract for every submitter file. validate_schema compares each "
                            "batch header with these columns."
                        ),
                        "config": {"contract": {"enforced": True}},
                        "columns": RAW_COLUMNS,
                    }
                ],
            }
        ],
    }


def model_yaml(model: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": model["name"],
        "description": model["description"],
        "columns": model["columns"],
    }
    if model["tests"]:
        entry["tests"] = model["tests"]
    return {"version": 2, "models": [entry]}


def manifest(generated_at: str) -> dict[str, Any]:
    def cols(columns: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            c["name"]: {
                "name": c["name"],
                "data_type": c["data_type"],
                "description": c.get("description", ""),
            }
            for c in columns
        }

    nodes = {
        f"model.{PROJECT}.{m['name']}": {
            "resource_type": "model",
            "name": m["name"],
            "package_name": PROJECT,
            "original_file_path": f"models/{m['path'].replace('.yml', '.sql')}",
            "description": m["description"],
            "columns": cols(m["columns"]),
            "depends_on": {"nodes": m["depends_on"]},
            "config": {"materialized": "table" if m["name"] != "stg_transactions" else "view"},
        }
        for m in MODELS
    }
    sources = {
        f"source.{PROJECT}.raw.transactions": {
            "resource_type": "source",
            "source_name": "raw",
            "name": "transactions",
            "package_name": PROJECT,
            "description": sources_yaml()["sources"][0]["tables"][0]["description"],
            "columns": cols(RAW_COLUMNS),
            "config": {"contract": {"enforced": True}},
        }
    }
    return {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json",
            "dbt_version": "1.9.0",
            "generated_at": generated_at,
            "project_name": PROJECT,
        },
        "nodes": nodes,
        "sources": sources,
    }
