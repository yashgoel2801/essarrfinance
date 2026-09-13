# Overdraft Loan Type + Officer/Defaulter Collections Report

Date: 2026-09-13
Branch: feat/detail-redesign (or a follow-on feature branch)
Status: Approved for implementation planning

## Summary

Add a new "OverDraft" loan type alongside the existing Daily/Weekly/Monthly
loans. Overdraft loans charge interest monthly on the *outstanding*
principal rather than a flat amount fixed at creation; any payment beyond
that month's interest reduces principal immediately (dated to the day it's
paid), and future interest is prorated day-by-day across principal changes
within a cycle. Overdraft loans also get a per-loan configurable
late-payment penalty rate (existing loan types keep their current
default-2%-via-`Penalty`-model behavior, unchanged).

Separately, extend the existing Overdue Loans screen into a combined
officer/collections view: loans grouped by collecting officer, with a
short per-loan summary, plus a defaulters section reusing the existing
overdue/behind-schedule classification.

## Background / current state

- All loan domain logic lives in `microfinance/models.py` and
  `microfinance/views.py`. There is no Celery/cron in this app — nothing
  runs on a schedule.
- `Loans.Frequency` (`microfinance/models.py:43-48`, `LOAN_CHOICES`)
  currently has a bug: `(3, 'Monthly')` and `(3, 'OverDraft')` share the
  same stored value. Selecting "OverDraft" in any form silently saves
  `Frequency=3` and is treated as Monthly everywhere — no code branches on
  a 4th frequency today. This is a dangling, non-functional label, not a
  feature in use.
- Regular loans use **flat interest**: `total_payable = principal +
  principal × rate/100`, fixed at creation, split evenly across
  `No_Of_Installments` (`views.py:316-368`, duplicated at
  `views.py:2531-2620` for the edit path).
- `Installments` rows are pre-generated in full at loan creation for
  regular loans.
- `Penalty` (`models.py:226-242`) accrues on unpaid installment amounts at
  a daily rate derived from `Percent` (default 2, `_get_penalty_rate`,
  `views.py:3118-3121`), computed via
  `_calculate_individual_installment_penalties` /
  `_calculate_total_penalty` (`views.py:3102-3116`).
- `Staff` (`models.py:16-26`) is the officer/collector entity;
  `Loans.Loan_Collector` FKs to it.
- `Overdue_Loans` (`views.py:1408-1473`) is the existing overdue report:
  staff-only, filterable by officer, backed by `bulk_overdue_map`
  (`views.py:46-83`) and the shared classifier `loan_repayment_status`
  (`views.py:86-157`).
- Dashboard (`views.py:3156` onward) reverse-derives an interest/principal
  split from the flat-rate assumption at `views.py:3260-3266`.

## Decisions locked in during design

1. Overdraft has a fixed monthly due date (like other loans), not a
   dateless running accrual.
2. Late-payment penalty % is configurable per-loan at creation, for
   **overdraft loans only**. Regular loans are untouched.
3. Penalty base is that month's **unpaid interest**, not principal.
4. Interest is a **simple monthly rate** applied to outstanding principal
   (not an annual rate prorated down).
5. Overdraft loans are **open-ended** — no `No_Of_Installments`/fixed
   tenure. They close when outstanding principal reaches zero and all
   billed interest/penalty is settled.
6. Interest accrues with **daily proration inside each cycle**: when an
   excess payment lands mid-cycle, the days before that payment accrue on
   the old principal and the days after accrue on the reduced principal,
   within the same materialized installment.
7. Daily rate = `Intrest_Rate / (actual days in that cycle)` — not a fixed
   ÷30. A 31-day cycle and a 28-day cycle both charge the full monthly
   rate overall, just spread proportionally.
8. The "defaulter" definition in the new report reuses the existing
   `loan_repayment_status` overdue/behind classification — no new
   threshold.
9. The report is an **enhancement of the existing Overdue Loans screen**,
   not a new page.

## Model changes

### `LOAN_CHOICES` (models.py:43-48)

```python
LOAN_CHOICES = (
   (1, 'Daily'),
   (2, 'Weekly'),
   (3, 'Monthly'),
   (4, 'OverDraft'),
)
```

Removing the dangling duplicate `(3, 'OverDraft')` is safe: any row ever
saved through it is already stored as `Frequency=3` (Monthly) in the
database, and no code path branches on a distinct overdraft value today.
No data migration needed — this is a pure choices-tuple fix plus a new
value.

### `Loans` (models.py:183-204)

Add:

```python
Penalty_Rate = models.FloatField(null=True, blank=True)
```

- Nullable; only meaningful/populated for `Frequency == 4` (OverDraft).
- `_get_penalty_rate` (`views.py:3118-3121`) will check
  `loan.Penalty_Rate` first when `loan.Frequency == 4`, falling back to
  existing `Penalty`-row/default-2 behavior otherwise (unchanged for
  non-overdraft loans).

No `Outstanding_Principal` field is added — see below.

### `Payments` (models.py:247-260)

Add:

```python
Principal_Portion = models.FloatField(default=0)
```

- For non-overdraft loans this stays `0` and is unused.
- For overdraft loans, this is the amount of a given payment that went
  toward reducing principal (i.e. the excess beyond that cycle's billed
  interest), dated by the payment's existing `Date_Paid`.

### Outstanding principal — derived, not stored

Outstanding principal as of any date `D` for an overdraft loan is:

```
Principle_Amount − Σ(Principal_Portion of Payments for this loan with Date_Paid ≤ D)
```

This is computed on demand (query volume here is small — per-loan
payment counts are modest) rather than cached in a running field. A
single writable source of truth (the payment ledger) avoids a cached
`Outstanding_Principal` field silently drifting out of sync with reality,
which would be the likely failure mode of maintaining both.

A small helper, `overdraft_outstanding_principal(loan, as_of=None)`, wraps
this query and is the only place this computation lives.

## Interest engine

### Lazy monthly materialization

No scheduler exists in this app, and each cycle's interest amount depends
on payment timing within that cycle, so `Installments` rows for overdraft
loans are **not** pre-generated at creation. Instead, a helper —
`ensure_overdraft_installments(loan)` — is called from every read/write
path that touches an overdraft loan (loan detail view, payment recording,
the collections report) and materializes any `Installment` row whose due
date has arrived but doesn't yet exist.

Because materialization only ever happens for cycles that are already
fully in the past (today ≥ the cycle's due date), all payments within
that cycle are already recorded — no circularity, no need to guess future
payment behavior.

### Piecewise proration within a cycle

For cycle `[previous_due_date, this_due_date)`, with `cycle_days = 
(this_due_date - previous_due_date).days`:

1. Find every `Payment` in that window with `Principal_Portion > 0`,
   ordered by `Date_Paid` — these are the segment boundaries.
2. Walk the cycle as segments split at those dates. For each segment:
   `segment_days × outstanding_at_start_of_segment × (Intrest_Rate / 100 / cycle_days)`
3. Sum the segments to get that cycle's `Installment_Due`.

Worked example: due dates on the 10th, 30-day cycle, principal such that
full-cycle interest = 5000. Borrower pays 5000 on the 10th (exactly
covers that cycle's interest, `Principal_Portion=0` — no segment change).
Borrower then pays another 5000 on the 20th (`Principal_Portion=5000`).
The *next* cycle (10th → 10th) is split into: day 10–19 (10 days, full
principal) + day 20–next due (20 days, principal − 5000).

### Payment allocation (applied when a payment is recorded)

Extending `pay_installment` (`views.py:701-739`) with an overdraft branch:

1. Apply the payment against the oldest unpaid materialized interest
   installment(s) first, in order.
2. Any amount remaining after all currently-billed interest is satisfied
   becomes that payment's `Principal_Portion`, dated at the payment's
   `Date_Paid`.
3. This also correctly handles paying before a cycle's interest has even
   been billed yet (e.g. paying on the 5th ahead of a 10th due date):
   with no unpaid billed interest to apply against, the whole amount
   becomes `Principal_Portion` immediately, effective that date, and
   prorates the next materialization accordingly.

### Backdated payments

If a payment is recorded with a `Date_Paid` earlier than today, and it
falls inside a cycle whose `Installment_Due` was already materialized,
that installment's stored amount is now stale. Mirroring the existing
`Recalculate_Penalty` pattern, a new `recalculate_overdraft_interest(loan)`
re-derives amounts for **unpaid** materialized installments only, called
after every overdraft payment. Already-paid installments are left frozen
as historical record — not retroactively corrected. This is the simplest
consistent behavior and matches how the existing penalty system already
treats settled history.

## Places requiring an overdraft-aware branch

Flat-interest assumptions baked into existing code, each needing a
`Frequency == 4` branch:

- **`Loans.Total` property** (models.py) — for overdraft, returns
  `overdraft_outstanding_principal(loan) + unpaid interest + unpaid
  penalty` instead of the flat `principal + principal×rate/100`.
- **`bulk_overdue_map`** (`views.py:46-83`) — overdue cap uses derived
  outstanding + unpaid interest/penalty instead of the flat total.
- **`loan_repayment_status`** (`views.py:86-157`) — needs to understand
  that overdraft loans have no fixed schedule to be "ahead" on; status is
  based on whether the current materialized installment(s) are paid.
- **Dashboard's reverse-derived interest/principal split**
  (`views.py:3260-3266`) — for overdraft payments, read
  `Payments.Principal_Portion` directly (already known) instead of
  reverse-deriving from a flat-rate assumption.
- **Both installment-generation code paths** (`views.py:316-368` and
  `views.py:2531-2620`) — for overdraft loans, skip flat upfront
  generation entirely; rely on lazy materialization instead.
- **Loan edit**: `Principle_Amount` is not directly editable on an
  overdraft loan after creation (the ledger-derived outstanding balance
  is the source of truth) — edit form shows a clear message instead of
  allowing the field to be changed.

## Penalty calculation for overdraft

- Base: that cycle's unpaid interest amount (the materialized
  `Installment_Due`), not principal.
- Rate: `Loans.Penalty_Rate` when `Frequency == 4`, read via the extended
  `_get_penalty_rate`.
- Mechanically reuses the existing `Penalty` model and existing daily
  daily-accrual walk (`_calculate_individual_installment_penalties`) —
  only the "amount penalty accrues on" and "rate source" branch by
  frequency; the overdue-period detection and daily-rate penalty math are
  unchanged.

## Loan creation / edit form

- "OverDraft" becomes a real, distinct, selectable `Frequency` option.
- `Penalty_Rate` input is shown only when Frequency = OverDraft.
- `No_Of_Installments` is hidden/disabled for OverDraft (open-ended, no
  fixed count).
- Editing an existing OverDraft loan disallows changing `Principle_Amount`
  directly (see above).

## Report: Overdue Loans screen enhancement

Extends the existing `Overdue_Loans` view/template (`views.py:1408-1473`)
rather than adding a new page:

- **Officer grouping**: loans grouped under each `Loan_Collector`
  (`Staff`), each with a short summary (client name, amount overdue, last
  payment date) — mostly already computed per-loan by `bulk_overdue_map`,
  just re-organized by officer instead of (or in addition to) the current
  flat/filtered list.
- **Defaulters section**: a highlighted section/toggle listing loans
  currently classified as "behind" by `loan_repayment_status`, also
  grouped by officer. No new defaulter definition — reuses the existing
  classification exactly.
- Overdraft loans participate through the same code paths as regular
  loans once `bulk_overdue_map` and `loan_repayment_status` are
  overdraft-aware (see branch inventory above) — the report itself needs
  no separate overdraft-specific logic.

## Out of scope

- No changes to `FloatField` money fields to `DecimalField` — staying
  consistent with the existing codebase convention, not introducing a
  mixed float/Decimal risk (note: `_get_penalty_rate` already returns
  `Decimal` in some paths — the overdraft additions will match whichever
  type that call site already expects, not introduce new mixing).
  Consider a future numeric-precision cleanup as a fully separate,
  unrelated task.
  - **Nuance the implementer must handle:** the existing `Penalty` model
    and `_get_penalty_rate` mix `Decimal` and `float` already in places;
    the new `Penalty_Rate` field is a plain `FloatField` like other rate
    fields on `Loans` (`Intrest_Rate`, `File_Charge_Percent`), so any
    arithmetic combining it with a `Decimal`-typed value from existing
    penalty code must explicitly convert one side to avoid a `TypeError`
    at runtime.
- No cron/scheduler is introduced — materialization stays lazy/on-demand,
  matching the rest of the app's architecture.
- No changes to Daily/Weekly/Monthly loan behavior, interest calculation,
  or penalty defaults.
- No new "Officer" model — continues using `Staff` as-is.
- No PDF variant of the enhanced Overdue Loans report in this pass (the
  codebase has a separate `report_pdf_views` pattern for PDFs elsewhere,
  but it's not requested here — can be added later as a separate task if
  needed).
