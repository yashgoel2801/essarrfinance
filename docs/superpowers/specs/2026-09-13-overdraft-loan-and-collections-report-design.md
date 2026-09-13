# Overdraft Loan Type + Officer/Defaulter Collections Report

Date: 2026-09-13
Branch: feat/detail-redesign (or a follow-on feature branch)
Status: Approved for implementation planning

## Summary

Add a new "OverDraft" loan type alongside the existing Daily/Weekly/Monthly
loans. Overdraft loans charge interest monthly on the *outstanding*
principal rather than a flat amount fixed at creation. After a payment
clears all currently unpaid interest, the leftover only reduces principal
if it meets a per-loan minimum threshold (a % of outstanding principal,
set at loan creation) — a leftover below that threshold does not touch
principal at all; instead it is banked as an advance-interest credit
automatically applied against the next cycle's interest. Interest is
prorated day-by-day across any principal reductions within a cycle.
Overdraft loans also get a per-loan configurable late-payment penalty
rate (existing loan types keep their current default-2%-via-`Penalty`-model
behavior, unchanged).

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
  `No_Of_Installments`. This generation logic is duplicated verbatim in
  two places — `Add_Loan` (`views.py:315-368`) and the `EditLoan`
  recreate-on-due-date-change path (`views.py:2483-2639`) — both already
  diverging copies of the same Daily/Weekly/Monthly branching.
- `Installments` rows are pre-generated in full at loan creation for
  regular loans.
- `Penalty` (`models.py:226-242`) accrues via the **live** call chain
  `pay_installment` (`views.py:701-739`) / `Recalculate_Penalty`
  (`views.py:646-667`) → `_calculate_individual_penalties`
  (`views.py:2869-2870`, a thin wrapper) →
  `_calculate_individual_installment_penalties` (`views.py:3789-4009`,
  the function that actually walks unpaid installments and creates
  `Penalty` rows). That function **hardcodes `penalty_rate =
  Decimal('2')`** at its own line 3944 — it does not read
  `Penalty.Percent` at all today, so regular loans' penalty rate is
  effectively fixed at 2%/day regardless of what's stored on any
  `Penalty` row.
- There is a **second, entirely separate penalty engine** in the same
  file (`calculate_penalties` → `_perform_calculation` →
  `_calculate_with_running_balance` → `_process_date_sequence` →
  `_calculate_total_penalty` / `_get_penalty_rate`, roughly
  `views.py:2703-3150`) that *does* read `Penalty.Percent` via
  `_get_penalty_rate`. Confirmed via grep of every call site: nothing in
  the live request-handling path calls `calculate_penalties` or
  `batch_calculate_penalties` — this entire cluster is **dead code**,
  unreachable from any view. **This feature does not touch it** and it
  is not the place to hook the configurable penalty rate.
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
   **all loan types** (Daily/Weekly/Monthly/OverDraft alike) — this
   supersedes an earlier, narrower "overdraft only" scoping decided
   mid-design. Loans created without a value keep the current hardcoded
   2%/day default.
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
10. A fully missed month's interest does **not** compound into
    principal — it stays a flat unpaid installment that only accrues
    penalty until paid; later payments clear unpaid interest oldest-first.
11. After interest is fully cleared, a payment's leftover only reduces
    principal if it is **≥ a per-loan threshold %** of outstanding
    principal (set at creation, all-or-nothing — not just the amount
    above the threshold). A leftover below the threshold is banked as an
    **advance-interest credit** and auto-applied against the next cycle's
    interest instead of touching principal — "paying in advance less
    than the threshold isn't beneficial, it just prepays next month's
    interest."
12. At full payoff, unbilled interest for the partial period since the
    last due date is charged as a final prorated stub before the loan
    can close (not forgiven).

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
Principal_Threshold_Percent = models.FloatField(null=True, blank=True)
```

- `Penalty_Rate` is nullable and available on **every** loan type —
  added to the loan creation form (and edit form) regardless of
  `Frequency`. It's read directly inside
  `_calculate_individual_installment_penalties` (`views.py:3944`, the
  live penalty engine — see Background), replacing that function's
  hardcoded `Decimal('2')` with: `Decimal(str(loan.Penalty_Rate))` when
  `loan.Penalty_Rate is not None`, else `Decimal('2')` (preserving
  today's behavior for any loan created without a value, e.g. loans that
  existed before this migration).
- `Principal_Threshold_Percent` is nullable and only meaningful/populated
  for `Frequency == 4` (OverDraft) — this field stays scoped to
  overdraft loans; only the penalty rate was generalized to all types.
  It's the minimum leftover-as-%-of-outstanding a payment must clear
  (after interest is fully paid) before that leftover counts toward
  principal at all. Set at loan creation, alongside `Intrest_Rate` and
  `Penalty_Rate`.

No `Outstanding_Principal` field is added — see below.

### `Payments` (models.py:247-260)

Add:

```python
Principal_Portion = models.FloatField(default=0)
Interest_Portion = models.FloatField(default=0)
```

- For non-overdraft loans both stay `0` and are unused.
- For overdraft loans: `Interest_Portion` is the amount of a given payment
  applied to unpaid interest installments; `Principal_Portion` is the
  amount that met the threshold test and reduced principal, dated by the
  payment's existing `Date_Paid`. A payment's advance-interest-credit
  contribution is implicit: `Amount_Paid − Interest_Portion −
  Principal_Portion` (see credit balance below) — no separate stored
  field for it.

### Outstanding principal and credit balance — derived, not stored

Both are outputs of the same chronological replay (see "Interest engine"
below), not independently stored fields:

```
outstanding principal as of date D =
    Principle_Amount − Σ(Principal_Portion of Payments with Date_Paid ≤ D)

advance-interest credit as of date D =
    Σ(Amount_Paid − Interest_Portion − Principal_Portion, for Payments
      with Date_Paid ≤ D) − Σ(credit already consumed by materialized
      installments due ≤ D)
```

Query volume here is small (per-loan payment counts are modest), so both
are computed on demand rather than cached. A single writable source of
truth (the payment ledger, `Interest_Portion` + `Principal_Portion` per
payment) avoids two derived numbers drifting out of sync with each other
or with reality — the likely failure mode of maintaining separate running
fields. If replay performance ever becomes a concern, a cached balance on
`Loans` is acceptable specifically *because* it stays recomputable from
the ledger — not as a second independent source of truth.

## Interest engine

### Core mechanism: chronological replay

The threshold rule means allocation decisions depend on state *at the
moment of each payment* (outstanding principal then, what interest is
billed-but-unpaid then, the accumulated credit then) — allocation is no
longer a one-shot decision made independently at each payment's entry
time. So the engine is a single pure function,
`replay_overdraft_loan(loan)`, that walks a loan's due dates and payments
in date order and derives everything else as its output:

- At each due date reached (≤ today): materialize the cycle's
  `Installment_Due` from that cycle's segments (see proration below),
  then immediately apply any available advance-interest credit against
  it.
- At each payment (in `Date_Paid` order): allocate interest-first against
  oldest unpaid materialized installment(s) (`Interest_Portion`), then
  threshold-test the leftover against outstanding principal *as of that
  payment's date* — leftover ≥ threshold% → all of it becomes
  `Principal_Portion`; leftover < threshold% → none of it becomes
  `Principal_Portion`, and it is added to the running advance-interest
  credit balance instead.

Everything else — each payment's stored split, each installment's
due/paid amounts, current outstanding principal, current credit balance —
is read off this replay's output, not computed independently. This also
subsumes backdated-payment recalculation (below): a backdated payment is
handled by simply re-running the replay for that loan and re-deriving
unpaid installment amounts; there is no separate bespoke recalc
algorithm.

Because replay only materializes cycles whose due date has already
passed (today ≥ due date), and only replays payments that already exist,
there's no circularity — nothing depends on guessing future behavior.

### Lazy invocation

No scheduler exists in this app. `ensure_overdraft_installments(loan)` is
a new, standalone function called from every read/write path that
touches a loan (loan detail view, `pay_installment`, the collections
report), guarded by `if loan.Frequency == 4:` at each call site — a thin
early dispatch, not a modification to what those views currently do for
other frequencies. It runs the replay and persists any
newly-materialized `Installment` rows and updated unpaid-installment
amounts. Similarly, `pay_installment`'s overdraft-specific allocation
(interest-first, then threshold test, from the replay) lives in its own
function, called only when `loan.Frequency == 4`; the existing payment
logic for other frequencies in `pay_installment` is not altered.

### Piecewise proration within a cycle

For cycle `[previous_due_date, this_due_date)`, with `cycle_days =
(this_due_date - previous_due_date).days`:

1. Within the replay, find every payment in that window whose allocation
   produced `Principal_Portion > 0` — these are the segment boundaries.
   (A leftover that was banked as credit, not applied to principal, does
   **not** create a segment — the principal didn't change.)
2. Walk the cycle as segments split at those dates. For each segment:
   `segment_days × outstanding_at_start_of_segment × (Intrest_Rate / 100 / cycle_days)`
3. Sum the segments, **then subtract any advance-interest credit
   available at this due date** (down to a floor of 0), to get that
   cycle's `Installment_Due`.

Worked example (threshold 20%, full-cycle interest 5000 on a 250,000
principal): borrower pays 5000 on the 10th (clears interest exactly,
leftover 0 — no segment, no credit). Borrower then pays 55,000 on the
20th: 5000 already cleared this cycle's interest via the first payment,
so the entire 55,000 is leftover — that's ≥ 20% of 250,000 (50,000), so
the **full** 55,000 becomes `Principal_Portion`. Next cycle splits into
day 10–19 (10 days, principal 250,000) + day 20–next due (20 days,
principal 195,000).

Contrast: borrower instead pays 30,000 on the 20th. Leftover 30,000 is
below the 50,000 threshold, so none of it reduces principal — it's banked
as credit and applied to reduce (or fully cover) next cycle's
`Installment_Due` when that cycle materializes. Principal stays 250,000,
so next cycle's proration has no segment split from this payment.

### Missed months — unpaid interest does not compound

If a cycle's interest goes completely unpaid, the next cycle's interest
is still computed purely on outstanding **principal** — unpaid interest
is never added to principal and never itself accrues further interest.
It remains a separate unpaid materialized `Installment` row and accrues
**penalty** from its due date via the existing `Penalty` model (see
"Penalty calculation (configurable rate, all loan types)" below) for as
long as it's unpaid.

Oldest-first allocation (above) means a late payment clears month 1's
unpaid interest before month 2's, and so on — and only a leftover *after
every currently-billed interest installment is satisfied* is subject to
the threshold test at all. A borrower who skips a month and then pays
exactly one cycle's worth of interest the next month clears the old
debt, not the new one; the newer cycle's interest remains outstanding
(continuing to accrue penalty) until paid.

### Payoff and closure

An overdraft loan closes when outstanding principal reaches zero and all
billed interest/penalty is settled. Since interest is only billed at due
dates, a mid-cycle full payoff (e.g. paying off on the 25th, next due
date the 10th) requires charging a final **prorated stub**: at payoff,
compute interest for the partial period from the last due date to the
payoff date using the same daily formula, and require it paid (net of
any available advance-interest credit) before the loan can close. This is
not forgiven.

Full payoff naturally passes the threshold test (the leftover equals
100% of outstanding, which is ≥ any percentage threshold), so there's no
conflict between the threshold rule and being able to close a loan.

### Backdated payments

If a payment is recorded with a `Date_Paid` earlier than today, re-running
`replay_overdraft_loan(loan)` naturally re-derives correct amounts for any
**unpaid** materialized installments — this is not a separate algorithm,
just the same replay re-executed after the new payment is inserted into
the ledger. Already-paid installments are left frozen as historical
record — not retroactively corrected. This matches how the existing
penalty system already treats settled history.

## Design principle: new functions for overdraft, not branches in existing ones

To minimize risk to existing Daily/Weekly/Monthly behavior, overdraft
logic is implemented as **new, separately-named functions** that regular
loans never call, rather than threading `if Frequency == 4` branches
into the existing (already duplicated) installment-generation code. Each
place below either dispatches to a new function early (leaving the
existing code path for other frequencies completely unmodified) or reads
a value that's naturally correct for both cases without needing a
frequency check at all:

- **`Add_Loan`** (`views.py:315-368`) and the **`EditLoan` recreate path**
  (`views.py:2483-2639`): add one `if instance.Frequency == 4: return
  <call new function>; ...` (or equivalent early-dispatch) at the top of
  the installment-generation block in each, calling a new
  `create_overdraft_loan(...)` / `regenerate_overdraft_installments(...)`
  helper that does nothing like the existing flat-schedule loop — it just
  ensures the first cycle's row exists (or defers entirely to lazy
  materialization). The existing Daily/Weekly/Monthly code below that
  dispatch point is untouched, byte-for-byte, for every other frequency.
  Any duplication between the new overdraft function and future cleanup
  of the existing Daily/Weekly/Monthly duplication is left for a
  separate, later refactor — not part of this feature.
- **`Loans.Total` property** (models.py) — add a frequency check at the
  top: `if self.Frequency == 4: return <overdraft total from the replay
  helper>`, else fall through to the existing unmodified flat-rate
  calculation.
- **`bulk_overdue_map`** (`views.py:46-83`) and **`loan_repayment_status`**
  (`views.py:86-157`) — both need an early per-loan dispatch: overdraft
  loans route to new helper logic built on `replay_overdraft_loan`;
  non-overdraft loans fall through to the existing query/calculation
  code completely unchanged (the existing flat-total math is not
  touched, only guarded behind a frequency check so it's simply never
  reached for overdraft rows).
- **Dashboard's interest/principal split** (`views.py:3260-3266`) — add a
  branch: for `Payment.Loan.Frequency == 4`, read
  `Payments.Principal_Portion`/`Interest_Portion` directly (already
  known, no reverse-derivation needed); for every other frequency, keep
  the existing reverse-split line exactly as it is today.
- **Loan edit**: `Principle_Amount` is not directly editable on an
  overdraft loan after creation (the ledger-derived outstanding balance
  is the source of truth) — the edit view adds an overdraft-specific
  guard that shows a message and refuses the change; the existing edit
  behavior for other frequencies is unaffected.

In every case above, the rule is: **check `Frequency == 4` first, dispatch
to new overdraft-only code, and otherwise fall through to the existing
code path unmodified.** No existing Daily/Weekly/Monthly branch, query,
or formula is edited in place.

## Penalty calculation (configurable rate, all loan types)

- Base: for regular loans, unchanged — the unpaid remainder of each
  overdue `Installment` row, exactly as computed today. For overdraft,
  this is naturally that cycle's unpaid **interest** amount, since
  materialized overdraft installments are pure interest — no separate
  "what amount does penalty accrue on" branch is needed; it falls out of
  reusing the same `Installment` rows unchanged.
- Rate: `_calculate_individual_installment_penalties`
  (`views.py:3789-4009`) currently hardcodes `penalty_rate =
  Decimal('2')` at line 3944. Change this single line to:
  `Decimal(str(loan.Penalty_Rate)) if loan.Penalty_Rate is not None else
  Decimal('2')`. This is the **only** code change this feature makes to
  that function's penalty-rate handling — the rest of the function
  (overdue-period detection, FIFO payment allocation, waiver/paid-pool
  handling, daily-rate math) is untouched.
- **Non-regression guarantee**: every loan in the database today has
  `Penalty_Rate = NULL` after the migration (it's a new nullable field
  with no default), so the `else Decimal('2')` branch fires for all of
  them — penalty calculation for every existing loan is byte-for-byte
  identical to current behavior. Only newly-created loans that
  explicitly set a `Penalty_Rate` see different math.
- The dead second penalty engine (`calculate_penalties` and friends,
  `views.py:2703-3150`) is not modified, not called, and not relied upon
  — confirmed unreachable from any view (see Background).

## Loan creation / edit form

- "OverDraft" becomes a real, distinct, selectable `Frequency` option.
- `Penalty_Rate` input is shown for **every** Frequency (Daily, Weekly,
  Monthly, OverDraft) — optional; leaving it blank keeps the current
  2%/day default for that loan.
- `Principal_Threshold_Percent` input is shown only when Frequency =
  OverDraft.
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

## Edge cases

Stated as assumptions; the implementer should flag if any of these turn
out to conflict with something discovered in the existing code:

- **Waivers.** The existing `Waiver` model (Penalty=1 / Interest=2) is
  netted throughout `bulk_overdue_map` and status calculations. For
  overdraft: an interest waiver reduces the oldest unpaid interest
  installment's outstanding amount — it never touches principal and never
  contributes to the advance-interest credit balance.
- **Overpayment beyond everything owed.** If a payment's leftover, after
  clearing all unpaid interest, exceeds the full outstanding principal
  (e.g. an intentional payoff-plus-extra), `Principal_Portion` is capped
  at the remaining outstanding principal; any true residual beyond that
  is rejected at entry (the form should not accept a payment larger than
  total owed) rather than silently producing a negative outstanding
  balance.
- **Payment edit/delete.** If the existing UI allows editing or deleting
  a `Payments` row, that must trigger the same replay used for backdated
  payments (a stale `Interest_Portion`/`Principal_Portion` otherwise
  corrupts every downstream figure) — or overdraft payments disallow
  edit/delete entirely if that's simpler given how the existing payment
  edit flow works.
- **Penalty payments excluded from allocation.** `Payments.Payment_Type`
  already distinguishes installment payments (1) from penalty payments
  (2) in the same table; the replay's interest/principal allocation only
  ever considers `Payment_Type=1` rows.
- **First cycle.** `[Loan_Date, First_Due_Date)` can be any length —
  proration-by-actual-days handles it without special-casing, but the
  loan creation form should validate `First_Due_Date > Loan_Date`.
- **Cycle boundary convention.** A cycle is `[previous_due_date,
  this_due_date)` (inclusive start, exclusive end); a payment dated
  exactly on a due date belongs to the *new* cycle as day 0. This applies
  consistently to both proration segments and replay ordering.
- **Month-end drift.** Due dates computed via repeated
  `relativedelta(months=1)` (same mechanism regular Monthly loans already
  use, `views.py:355-361`) can drift for a loan whose first due date is
  the 29th–31st, landing on shorter months. Overdraft uses the same
  drift behavior as existing Monthly loans for consistency — not a new
  problem introduced by this feature.
- **Materialization idempotency.** Because `ensure_overdraft_installments`
  runs on every relevant request, two concurrent requests must not double-
  create the same cycle's `Installment` row — implement via `get_or_create`
  keyed on `(Loan, Date_Due)` inside a transaction.
- **Stop materializing after closure**, and don't create a zero-amount
  installment once principal is fully paid off but an older unpaid
  interest installment still exists (interest on zero principal is zero).
- **Future-dated payments.** A `Date_Paid` in the future is rejected at
  entry — allowing it would let a payment affect proration of a cycle
  that hasn't been materialized yet while today's derived "outstanding as
  of now" figure confusingly wouldn't reflect it yet.

## Out of scope

- No changes to `FloatField` money fields to `DecimalField` — staying
  consistent with the existing codebase convention, not introducing a
  mixed float/Decimal risk. Consider a future numeric-precision cleanup
  as a fully separate, unrelated task.
  - **Nuance the implementer must handle:** `_calculate_individual_installment_penalties`
    (the live penalty engine) does all of its arithmetic in `Decimal`
    (e.g. `period['amount'] * penalty_rate / Decimal('100') * period['days']`
    at `views.py:3962`). `Penalty_Rate` is a plain `FloatField`, like
    every other rate field on `Loans` (`Intrest_Rate`,
    `File_Charge_Percent`), so it must be converted with
    `Decimal(str(loan.Penalty_Rate))` — never used directly in that
    Decimal expression — to avoid a `TypeError` at runtime. The
    `Decimal(str(...))` conversion (not `Decimal(loan.Penalty_Rate)`
    directly) avoids float binary-representation artifacts, matching how
    the rest of the file already converts floats (e.g.
    `Decimal(str(pay['Amount_Paid']))` at `views.py:3803`).
- No cron/scheduler is introduced — materialization stays lazy/on-demand,
  matching the rest of the app's architecture.
- No changes to Daily/Weekly/Monthly loan behavior, interest calculation,
  or penalty defaults.
- No new "Officer" model — continues using `Staff` as-is.
- No PDF variant of the enhanced Overdue Loans report in this pass (the
  codebase has a separate `report_pdf_views` pattern for PDFs elsewhere,
  but it's not requested here — can be added later as a separate task if
  needed).
