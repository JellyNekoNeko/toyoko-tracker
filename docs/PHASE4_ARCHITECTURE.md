# Phase 4 Decision Intelligence Architecture

Phase 4 adds explainable price decisions, split-stay optimization and durable
travel lists without changing the public `0.7.0` version.

## 1. Historical-price contract

The decision repository reads three local evidence sources:

1. `scan_observations`: recurring and one-time monitor results.
2. `price_calendar_days`: the latest stored quote for each calendar day.
3. `flexible_stay_nights`: Provider observations collected by Phase 3 jobs.

Samples are filtered to the active hotel and price-affecting stay conditions.
A mirrored observation with the same hotel, stay date and price inside a
60-second interval is counted once.

### Retention and anomalies

- API history windows are bounded to 7–730 days.
- The default decision window is 180 days.
- With fewer than eight raw samples, no anomaly filter is applied.
- With eight or more samples, values outside `P25 - 1.5 × IQR` and
  `P75 + 1.5 × IQR` are excluded.
- Responses expose raw count, retained count, excluded count and bounds.

### Statistics and labels

Percentiles use deterministic R-7 linear interpolation. Each hotel exposes:

- minimum, average, maximum and median;
- P10, P25, P75 and P90;
- current price and approximate percentile position;
- first/last observation, requested window and evidence sources;
- the full dedupe, anomaly and label method.

A label requires at least four retained samples:

- `low`: current price is at or below P25;
- `normal`: current price is between P25 and P75;
- `high`: current price is at or above P75;
- `insufficient` or `no_current_price`: no directional conclusion.

## 2. Split-stay optimizer

The optimizer consumes one Phase 3 flexible-stay job and its stored nightly
Provider observations. A plan is produced only when every night has at least
one available hotel with a usable price.

The deterministic score is:

```text
room total
+ hotel move count × move penalty
+ known move distance × per-kilometre cost
+ unknown-distance move count × unknown-distance penalty
- accumulated hotel priority × priority bonus
```

The defaults are visible in the API and UI:

- move penalty: JPY 2,500;
- distance cost: JPY 200/km;
- unknown-distance penalty: JPY 1,000;
- priority bonus: JPY 300 per priority point and night.

Hotel-to-hotel distance uses the Haversine formula when both coordinates are
known. A bounded dynamic program retains the best paths per ending hotel, then
sorts by score, room total, moves, distance and hotel sequence. Every result
contains its nightly evidence, contiguous hotel segments and score breakdown.

## 3. Workspace schema v4

Schema v4 extends `travel_lists` and adds durable associations:

```text
travel_lists
  list_id, name, dates, budget_limit, notes, currency, status, revision

travel_list_hotels
  list_id, hotel_code, provider, hotel_json, priority, sort_order, notes

travel_list_links
  list_id, resource_type, resource_id, metadata_json
```

Supported resource types are `task`, `alert_rule` and `comparison`.
Associations store stable IDs and redacted display metadata. They do not add a
foreign-key cascade to the linked resource, so deleting a travel list removes
only its own hotels and links.

Travel-list writes increment an optimistic `revision`. Existing development
databases are migrated idempotently by adding the new columns and association
table.

## 4. API surface

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/decision/prices` | Historical statistics and price labels |
| `GET/POST` | `/api/v1/flexible-stays/<job_id>/split-stays` | Ranked stay plans |
| `GET/POST` | `/api/v1/travel-lists` | List or create travel lists |
| `GET/PATCH/DELETE` | `/api/v1/travel-lists/<list_id>` | Read, edit or delete |
| `PUT/DELETE` | `/api/v1/travel-lists/<list_id>/hotels/<hotel_code>` | Hotel priority and notes |
| `POST/DELETE` | `/api/v1/travel-lists/<list_id>/links` | Link or unlink a resource |
| `GET` | `/api/v1/travel-lists/<list_id>/summary` | JSON, Markdown or HTML summary |

## 5. Export and privacy

Trip summaries contain:

- dates, status, budget and remaining amount;
- priority hotels and notes;
- linked resource identifiers;
- the best complete split-stay plan;
- historical price assessments.

JSON is versioned with `schema_version`. Markdown and HTML are downloadable.
Keys containing token, secret, password, SMTP password, Bark key, SendKey or
chat ID fragments are recursively removed before persistence and export.

## 6. Failure semantics

- Missing historical samples produce an explicit non-directional label.
- A missing night produces no split-stay claim and lists the missing dates.
- Missing hotel coordinates use the visible unknown-distance penalty.
- Missing linked resources remain isolated to summary generation and are
  recorded in the runtime log.
- Travel-list revision conflicts return HTTP 409.
- Unsupported export formats and invalid inputs return HTTP 400.

