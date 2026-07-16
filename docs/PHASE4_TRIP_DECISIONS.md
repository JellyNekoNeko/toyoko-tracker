# Phase 4 Trip Decisions Guide

The **Trip Decisions / 行程决策** page combines historical prices, split-stay
planning, travel lists and an exportable itinerary.

## 1. Price level assessment

1. Select a monitor task from **Monitor Tasks**.
2. Open **Trip Decisions** in the sidebar.
3. Choose a 30, 90, 180 or 365-day history window.
4. Review the current price, historical range, P25/median/P75 and label.

The sample count and excluded anomaly count are shown for every hotel. Hover
the label to read the exact percentile explanation. A low/high label appears
only after at least four retained observations.

## 2. Generate split-stay suggestions

1. Complete a flexible-date comparison in **Price Calendar**.
2. In **Split-stay suggestions**, choose the comparison job and stay window.
3. Adjust the cost assigned to each hotel move and kilometre.
4. Select **Generate suggestions**.

Each card shows the real room total, number of hotel moves, travel distance,
ranking score and date segments. The optimizer uses only complete nightly
evidence. A date without any available priced hotel produces an explicit
missing-evidence state instead of a suggested plan.

## 3. Create a travel list

1. Select **New**.
2. Enter the list name, dates, JPY budget, status and notes.
3. Select **Add selected hotels** to copy hotels from the current search.
4. Set each hotel priority from 0 to 5 and add hotel-specific notes.
5. Save the list.

Higher priority can improve a hotel's split-stay score. It never replaces the
nightly price or availability evidence.

## 4. Link decision resources

A travel list can link:

- the active monitor task;
- the selected flexible-date comparison;
- a price-alert rule belonging to the active task.

Linked resources feed the itinerary summary. Removing a link or deleting the
travel list leaves the original task, rule and comparison data in place.

## 5. Budget and itinerary summary

The summary uses the best complete linked split-stay plan as the estimated
stay total. If no split plan exists, it uses the lowest complete linked
comparison total. The budget panel shows:

- budget limit;
- estimated stay total;
- remaining amount or over-budget amount.

Select **Refresh summary** after changing links, prices or priorities.

## 6. Export

Use the export buttons for:

- `JSON`: structured, versioned data;
- `Markdown`: readable notes and plan segments;
- `HTML`: a standalone printable summary.

Exports exclude stored notification credentials and private token fields.
Prices and availability remain stored observations, so recheck the Provider
booking page before completing a reservation.

