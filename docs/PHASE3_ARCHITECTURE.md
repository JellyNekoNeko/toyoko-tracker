# Phase 3 flexible-stay architecture

## Domain contract

`latest_date` is the latest permitted checkout date. A search contains an
earliest check-in, latest checkout, stay length, shortcut mode, task, hotels
and price-affecting conditions. `generate_stay_windows()` produces stable,
unique combinations and `required_stay_dates()` reduces them to reusable
hotel-night work items.

Supported shortcuts:

- `custom`: every bounded combination.
- `weekend`: Friday and Saturday check-ins.
- `next_30`: deterministic expansion after the UI applies a 30-day window.

## Persistence and recovery

Workspace schema v3 adds:

- `flexible_stay_jobs`
- `flexible_stay_nights`
- `flexible_stay_results`

Night rows are the durable evidence boundary. Available and unavailable rows
count as completed work. Unknown rows remain visible but are eligible for a
later resume. Process-local queued/running states recover as paused after a
restart. Terminal searches older than 180 days are pruned when a new search is
created; active and paused searches are retained.

## Scheduling

Only one flexible-stay worker runs per process. Every hotel-night check enters
the installation-wide Provider pacer with a `flexible-stay:JOB_ID` identity.
The worker also respects Provider health cooldown and records successful
nightly observations into the existing single-hotel price calendar.

## Continuous-stay evaluation

The evaluator first classifies the full stay:

1. Missing night → `incomplete`.
2. Any explicit sold-out night → `unavailable`.
3. Any unknown night → `unknown`.
4. Every night available → `available`.

Offer room names are normalized per night. When their intersection is not
empty, the evaluator selects the common room with the lowest total. Otherwise
it sums nightly minimum prices and reports `room_change_required`. Member
totals are emitted only when every night has member-price evidence.

Every result states:

- `evidence_type = nightly_composite`
- `provider_verified_full_stay = false`
- `currency = JPY`
- `tax_basis = provider_display`

## Comparison aggregation

The comparison matrix is hotel-by-stay-window. For each column:

- member total is preferred when the task requests member pricing;
- unavailable, incomplete, unknown and missing-price cells are excluded;
- every tied cheapest hotel is marked;
- priced cells receive a deterministic heat level from 1 to 5.

The response also exposes minimum hotels for every raw night, making the daily
minimum independent from the multi-night total comparison.

## Runtime API

The collection route creates and lists jobs. Detail returns job state,
comparison rows, daily minima and limitations. Pause, resume and cancel are
durable controls; delete is restricted to inactive jobs.

The WebUI uses the same selected task and unsaved hotel draft as the price
calendar, then polls only while the job is queued or running.
