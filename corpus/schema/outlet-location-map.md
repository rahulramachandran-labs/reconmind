---
title: outlet_location_map and outlet_alias
type: schema
tags: [schema, reference, outlet_id, location_id]
---

# outlet_location_map and outlet_alias

`outlet_location_map` is the canonical mapping between store ids and physical locations. There are 40 active locations, `LOC-0501` to `LOC-0540`, mapped one to one to `OUT-1001` to `OUT-1040`.

| Column | Type | Notes |
|---|---|---|
| outlet_id | text | Primary key. |
| location_id | text | Unique among active rows. |
| valid_from | date | |
| valid_to | date | Null while active. |

`outlet_alias` holds known bad ids that should be remapped during staging:

| Column | Type | Notes |
|---|---|---|
| alias_outlet_id | text | The id submitters wrongly sent. |
| outlet_id | text | The canonical id it maps to. |
| valid_from / valid_to | date | Window the alias applies to. |
| incident_id | text | The incident that introduced the alias. |

`stg_transactions` resolves `coalesce(alias.outlet_id, t.outlet_id)`. If an id is in neither table, the dbt `relationships` test on `stg_transactions.outlet_id` fails.
