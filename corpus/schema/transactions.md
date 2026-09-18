---
title: transactions (raw)
type: schema
tags: [schema, transactions, raw]
---

# transactions (raw)

One row per line item, as delivered by submitters. Loaded by `load_raw_transactions`. Nothing in this table is ever updated in place.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| outlet_id | text | no | Store id as reported by the submitter, format `OUT-NNNN`. Can drift from the canonical mapping, see key-drift runbook. |
| location_id | text | no | Physical location, format `LOC-NNNN`. Stable; this is the key to trust when the two disagree. |
| transaction_id | text | no | Submitter transaction id, format `TXN-NNNNNNNN`. Part of the dedup key. |
| upc_code | text | no | 12-digit UPC. Part of the dedup key. |
| channel_basket_id | text | no | Basket id, format `BSK-XXXXXXXX`. Part of the dedup key. |
| submitter_file_name | text | no | Source file, `SUBMITTERID_YYYYMMDD_HHMM_NAME.txt`. Added by the loader. |
| qty | integer | no | Units. Negative for returns. |
| amount | numeric(12,2) | no | Line amount in the store currency, after discounts. |
| event_ts | timestamptz | no | When the sale happened. The business date is `event_ts::date` in UTC. |

Dedup key: (`transaction_id`, `channel_basket_id`, `upc_code`), latest submitter file wins.

Indexes: `(event_ts)`, `(location_id, event_ts)`, `(transaction_id, channel_basket_id, upc_code)`.
