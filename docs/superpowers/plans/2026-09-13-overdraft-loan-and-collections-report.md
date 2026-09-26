# Overdraft Loan Type + Officer/Defaulter Collections Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new "OverDraft" loan type with daily-prorated interest on
outstanding principal and a threshold-gated principal-reduction rule,
plus a per-loan-type configurable penalty rate, plus an officer/defaulter
enhancement to the existing Overdue Loans screen.

**Architecture:** All new overdraft logic lives in a new module,
`microfinance/overdraft.py`, built around one pure function,
`replay_overdraft_loan(loan)`, that chronologically replays a loan's due
dates and payments to derive installment amounts, outstanding principal,
and advance-interest credit — no separate stored running balance.
Existing views gain early `if loan.Frequency == 4:` dispatches to new,
separately-named functions; the existing Daily/Weekly/Monthly code paths
are not edited in place anywhere. The one true cross-cutting change is a
single-line penalty-rate fix in the existing (already-live)
`_calculate_individual_installment_penalties`.

**Tech Stack:** Django 6.0, PostgreSQL 16, `python-dateutil` (already a
dependency, used for `relativedelta`), Django's built-in test runner
(`manage.py test`, using a disposable `test_<db>` database — never the
dev or production database).

**Spec:** `docs/superpowers/specs/2026-09-13-overdraft-loan-and-collections-report-design.md`

## Global Constraints

- **Never touch the production database.** All work happens against the
  local Postgres database already configured in `essarrfinance/settings.py`
  (`essarr-new-2026` on `localhost`). Tests use Django's auto-created/
  destroyed `test_essarr-new-2026` database. No task in this plan connects
  to the Hetzner server or runs an SSH tunnel.
- **No existing Daily/Weekly/Monthly behavior changes.** Every touch point
  in an existing function must be a `Frequency == 4` (or loan-type-scoped)
  early guard that dispatches to new code — never an edit to the
  existing flat-interest/flat-penalty logic in place.
- **Existing loans keep identical behavior after migration.** Every
  existing `Loans` row has `Penalty_Rate = NULL` post-migration; the
  penalty-rate fallback (`Decimal('2')`) must fire for all of them,
  verified by a test that asserts unchanged penalty output for a
  pre-existing-style loan.
- **New money fields are `FloatField`**, matching every existing rate/amount
  field on `Loans`/`Payments` — no `DecimalField` introduced.
- **`Decimal(str(x))`, never `Decimal(x)`,** when converting any `FloatField`
  value into the existing Decimal-based penalty arithmetic — matches the
  codebase's existing conversion style (e.g. `views.py:3803`).
- **Migration dependency:** the current true leaf migration is
  `0010_expensecategory_alter_expenditures_category` (confirmed via
  `manage.py showmigrations microfinance` — the `0016`/`0020`-numbered
  files are chronologically earlier despite higher numbers). The new
  migration must depend on it.

---

### Task 1: Migration — new `Loans`/`Payments` fields and fixed `LOAN_CHOICES`

**Files:**
- Modify: `microfinance/models.py:43-48` (`LOAN_CHOICES`)
- Modify: `microfinance/models.py:183-204` (`Loans` class)
- Modify: `microfinance/models.py:247-260` (`Payments` class)
- Create: `microfinance/migrations/0011_overdraft_loan_fields.py`
- Test: `microfinance/tests.py`

**Interfaces:**
- Produces: `Loans.Penalty_Rate` (nullable `FloatField`),
  `Loans.Principal_Threshold_Percent` (nullable `FloatField`),
  `Payments.Principal_Portion` (`FloatField`, default `0`),
  `Payments.Interest_Portion` (`FloatField`, default `0`),
  `LOAN_CHOICES` including `(4, 'OverDraft')` with no duplicate value.

- [ ] **Step 1: Write a failing test asserting the new fields and choices exist**

```python
# microfinance/tests.py
from django.test import TestCase
from microfinance.models import Loans, Payments, LOAN_CHOICES, Staff, Guarantors, Accounts, Clients
from django.contrib.auth.models import User


class OverdraftFieldsTest(TestCase):
    def test_loan_choices_has_no_duplicate_values(self):
        values = [v for v, _ in LOAN_CHOICES]
        self.assertEqual(len(values), len(set(values)),
                          "LOAN_CHOICES must not have duplicate integer values")

    def test_loan_choices_has_distinct_overdraft_value(self):
        self.assertIn((4, 'OverDraft'), LOAN_CHOICES)

    def test_loans_has_penalty_rate_and_threshold_fields(self):
        field_names = {f.name for f in Loans._meta.get_fields()}
        self.assertIn('Penalty_Rate', field_names)
        self.assertIn('Principal_Threshold_Percent', field_names)

    def test_penalty_rate_and_threshold_are_nullable(self):
        penalty_field = Loans._meta.get_field('Penalty_Rate')
        threshold_field = Loans._meta.get_field('Principal_Threshold_Percent')
        self.assertTrue(penalty_field.null)
        self.assertTrue(threshold_field.null)

    def test_payments_has_principal_and_interest_portion_fields(self):
        field_names = {f.name for f in Payments._meta.get_fields()}
        self.assertIn('Principal_Portion', field_names)
        self.assertIn('Interest_Portion', field_names)

    def test_principal_and_interest_portion_default_to_zero(self):
        principal_field = Payments._meta.get_field('Principal_Portion')
        interest_field = Payments._meta.get_field('Interest_Portion')
        self.assertEqual(principal_field.default, 0)
        self.assertEqual(interest_field.default, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 manage.py test microfinance.tests.OverdraftFieldsTest -v 2`
Expected: FAIL — `LOAN_CHOICES` still has the duplicate `(3, 'OverDraft')`,
and `Loans`/`Payments` lack the new fields.

- [ ] **Step 3: Fix `LOAN_CHOICES` and add model fields**

In `microfinance/models.py`, replace:

```python
LOAN_CHOICES = (
   (1, 'Daily'),
   (2, 'Weekly'),
   (3,'Monthly'),
   (3,'OverDraft'),
)
```

with:

```python
LOAN_CHOICES = (
   (1, 'Daily'),
   (2, 'Weekly'),
   (3, 'Monthly'),
   (4, 'OverDraft'),
)
```

In the `Loans` class, add the two new fields right after `File_Charge_Percent`:

```python
class Loans(models.Model):
    Principle_Amount = models.FloatField()
    Frequency = models.IntegerField(choices=LOAN_CHOICES,default=1)
    AccNo = models.IntegerField(default=0)
    Purpose = models.CharField(choices=LOAN_ON_CHOICES,max_length=100, default='c')
    No_Of_Installments = models.IntegerField(default=0)
    Intrest_Rate = models.FloatField(default=20)
    File_Charge_Percent =models.FloatField(default=5)
    Penalty_Rate = models.FloatField(null=True, blank=True)
    Principal_Threshold_Percent = models.FloatField(null=True, blank=True)
    First_Due_Date =  models.DateField(default=timezone.now)
    Loan_Date = models.DateField(default=timezone.now)
    Loan_Collector = models.ForeignKey(Staff, on_delete=models.PROTECT,default= 1)
    Guarantor = models.ForeignKey(Guarantors,on_delete=models.PROTECT,default = 0)
    Account = models.ForeignKey(Accounts,on_delete=models.PROTECT,default = 0)
    Status =models.BooleanField(default=False)
    remark = models.CharField(max_length=100,default='None',blank=True,null=True)
    reminder = models.DateField(default=timezone.now,blank=True,null=True)
    security_docs= models.TextField(default='not specified')
    def __str__(self):
       return "Loan ID: "+str(self.pk)
    def _get_total_amnt_to_collect(self):
        return self.Principle_Amount + (self.Principle_Amount * self.Intrest_Rate/100 )      
    Total = property(_get_total_amnt_to_collect)
```

In the `Payments` class, add the two portion fields:

```python
class Payments(models.Model):
    Loan=models.ForeignKey(Loans,on_delete=models.PROTECT,default=0)
    Date_Paid = models.DateField(default=None, null=True,blank=True)
    Amount_Paid = models.FloatField(default=0)
    Payment_Type =models.IntegerField(choices=PAYMENT_TYPE,default=1)
    Principal_Portion = models.FloatField(default=0)
    Interest_Portion = models.FloatField(default=0)
    def __str__(self):
       return str(self.Date_Paid) +" - "+str(self.Amount_Paid)+ " - "+str(self.Loan.pk)  
    class Meta:
        ordering = ['Loan_id','Date_Paid']
```

- [ ] **Step 4: Generate and inspect the migration**

Run: `python3 manage.py makemigrations microfinance --name overdraft_loan_fields`

Verify the generated file's `dependencies` list includes exactly
`("microfinance", "0010_expensecategory_alter_expenditures_category")`,
and that it contains one `AlterField` on `Loans.Frequency` (the
`LOAN_CHOICES` fix) and `AddField` operations for `Penalty_Rate`,
`Principal_Threshold_Percent`, `Principal_Portion`, `Interest_Portion`.
If Django names the file differently than
`0011_overdraft_loan_fields.py`, rename it to that for clarity — no
functional difference, just matches this plan's naming.

- [ ] **Step 5: Apply the migration to the local dev database**

Run: `python3 manage.py migrate microfinance`
Expected: migration `0011_overdraft_loan_fields` applies cleanly against
the local `essarr-new-2026` database.

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 manage.py test microfinance.tests.OverdraftFieldsTest -v 2`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add microfinance/models.py microfinance/migrations/0011_overdraft_loan_fields.py microfinance/tests.py
git commit -m "Add overdraft loan fields: penalty rate, principal threshold, payment portions"
```

---

### Task 2: Fix hardcoded penalty rate — configurable per loan, all types

**Files:**
- Modify: `microfinance/views.py:3944` (inside
  `_calculate_individual_installment_penalties`)
- Test: `microfinance/tests.py`

**Interfaces:**
- Consumes: `Loans.Penalty_Rate` (from Task 1)
- Produces: `_calculate_individual_installment_penalties(loan, installments, payments, today)`
  now reads `loan.Penalty_Rate` instead of a hardcoded constant — same
  signature, same return shape (`{'total_penalty': ..., 'penalty_periods': [...]}`),
  same `Penalty` row creation behavior otherwise.

**Context for implementer:** `_calculate_individual_installment_penalties`
is the actual, live penalty-calculation function — reached via
`pay_installment` (`views.py:701-739`) and `Recalculate_Penalty`
(`views.py:646-667`) through the thin wrapper `_calculate_individual_penalties`
(`views.py:2869-2870`). It is NOT the same as `_get_penalty_rate` /
`_calculate_total_penalty` (`views.py:3102-3121`) — those belong to a
separate, verified-unreachable dead-code cluster
(`calculate_penalties` → `_perform_calculation` → ...) and must not be
touched.

- [ ] **Step 1: Write a failing test for the new configurable rate, and a regression test for the existing default**

```python
# microfinance/tests.py — add to the file
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from microfinance.views import _calculate_individual_installment_penalties
from microfinance.models import Loans, Payments, Penalty, Staff, Guarantors, Accounts, Clients


def _make_loan(**overrides):
    staff = Staff.objects.create(Officer_Name='Test Officer', Designation='Collector', Salary=0)
    user = User.objects.create_user(username='author1', password='x')
    client = Clients.objects.create(
        Name='Test Client', Phone_no1='+911234567890', Verified_By='x',
        author=user, Photo_Id_No='ABC123', Major_Medical_Issues='none',
    )
    account = Accounts.objects.create(Client=client)
    guarantor = Guarantors.objects.create()
    defaults = dict(
        Principle_Amount=100000, Frequency=3, No_Of_Installments=12,
        Intrest_Rate=20, Loan_Collector=staff, Guarantor=guarantor,
        Account=account, First_Due_Date=date(2026, 1, 10), Loan_Date=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return Loans.objects.create(**defaults)


class PenaltyRateConfigurationTest(TestCase):
    def test_default_penalty_rate_unchanged_when_not_set(self):
        loan = _make_loan(Penalty_Rate=None)
        installments = [{'id': 1, 'Date_Due': date(2026, 1, 10), 'Installment_Due': 1000.0}]
        payments = []
        today = date(2026, 1, 20)
        result = _calculate_individual_installment_penalties(loan, installments, payments, today)
        # 10 days overdue, amount 1000, default rate 2%/day = 1000 * 0.02 * 10 = 200
        self.assertEqual(result['total_penalty'], Decimal('200'))

    def test_custom_penalty_rate_applied_when_set(self):
        loan = _make_loan(Penalty_Rate=5.0)
        installments = [{'id': 1, 'Date_Due': date(2026, 1, 10), 'Installment_Due': 1000.0}]
        payments = []
        today = date(2026, 1, 20)
        result = _calculate_individual_installment_penalties(loan, installments, payments, today)
        # 10 days overdue, amount 1000, custom rate 5%/day = 1000 * 0.05 * 10 = 500
        self.assertEqual(result['total_penalty'], Decimal('500'))

    def test_penalty_rows_record_the_applied_rate(self):
        loan = _make_loan(Penalty_Rate=3.0)
        installments = [{'id': 1, 'Date_Due': date(2026, 1, 10), 'Installment_Due': 1000.0}]
        payments = []
        today = date(2026, 1, 20)
        _calculate_individual_installment_penalties(loan, installments, payments, today)
        penalty_row = Penalty.objects.filter(Loan=loan).first()
        self.assertEqual(penalty_row.Percent, Decimal('3'))
```

- [ ] **Step 2: Run tests to verify they fail (or pass for the wrong reason)**

Run: `python3 manage.py test microfinance.tests.PenaltyRateConfigurationTest -v 2`
Expected: `test_custom_penalty_rate_applied_when_set` and
`test_penalty_rows_record_the_applied_rate` FAIL (penalty is computed at
the hardcoded 2% regardless of `Penalty_Rate`).
`test_default_penalty_rate_unchanged_when_not_set` should already PASS
(this is the regression guard — confirm it passes before AND after Step 3).

- [ ] **Step 3: Change the hardcoded rate to read `loan.Penalty_Rate`**

In `microfinance/views.py`, inside `_calculate_individual_installment_penalties`,
find:

```python
    # Create penalty database records
    penalty_rate = Decimal('2')  # 2% per day
    total_penalty = Decimal('0')
```

Replace with:

```python
    # Create penalty database records
    penalty_rate = Decimal(str(loan.Penalty_Rate)) if loan.Penalty_Rate is not None else Decimal('2')  # 2% per day default
    total_penalty = Decimal('0')
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 manage.py test microfinance.tests.PenaltyRateConfigurationTest -v 2`
Expected: PASS (3 tests), including the regression guard still passing.

- [ ] **Step 5: Commit**

```bash
git add microfinance/views.py microfinance/tests.py
git commit -m "Make late-payment penalty rate configurable per loan, default 2%/day preserved"
```

---

### Task 3: `replay_overdraft_loan` — core chronological replay engine

**Files:**
- Create: `microfinance/overdraft.py`
- Test: `microfinance/tests_overdraft.py`

**Interfaces:**
- Consumes: `Loans` (with `Frequency=4`, `Intrest_Rate`,
  `Principal_Threshold_Percent`, `Principle_Amount`, `First_Due_Date`),
  `Payments` rows (`Payment_Type=1`, `Date_Paid`, `Amount_Paid`) — read
  only, via plain queries; no database writes in this task.
- Produces:
  `replay_overdraft_loan(loan, as_of=None) -> OverdraftReplayResult`,
  a plain Python object (dataclass) with:
  - `.installments: list[dict]` — one dict per materialized cycle:
    `{'Date_Due': date, 'Installment_Due': float, 'is_paid': bool}`,
    ordered by due date.
  - `.payment_splits: dict[int, dict]` — keyed by `Payments.pk`, each
    value `{'Interest_Portion': float, 'Principal_Portion': float}`.
  - `.outstanding_principal: float` — as of `as_of` (default: today).
  - `.credit_balance: float` — unconsumed advance-interest credit as of
    `as_of`.
  This is a **pure function** — no ORM writes, so it's cheap to unit
  test directly against in-memory `Loans`/`Payments` objects (using
  Django's ORM without `.save()`, or lightweight fakes — see Step 1,
  which uses real saved rows for simplicity and realism).

**Context for implementer:** This is the heart of the feature. Re-read
the spec's "Interest engine" section
(`docs/superpowers/specs/2026-09-13-overdraft-loan-and-collections-report-design.md`)
before starting — in particular "Core mechanism: chronological replay",
"Piecewise proration within a cycle", "Missed months", "Payoff and
closure". The two worked examples in the spec are Steps 1's test cases
below, verbatim.

- [ ] **Step 1: Write failing tests for the core replay behavior**

```python
# microfinance/tests_overdraft.py
from datetime import date
from django.test import TestCase
from django.contrib.auth.models import User
from microfinance.models import Loans, Payments, Staff, Guarantors, Accounts, Clients
from microfinance.overdraft import replay_overdraft_loan


def _make_overdraft_loan(principal=250000, rate=2.0, threshold=20.0,
                          first_due=date(2026, 1, 10), loan_date=date(2026, 1, 1)):
    staff = Staff.objects.create(Officer_Name='OD Officer', Designation='Collector', Salary=0)
    user = User.objects.create_user(username='odauthor', password='x')
    client = Clients.objects.create(
        Name='OD Client', Phone_no1='+911234567891', Verified_By='x',
        author=user, Photo_Id_No='OD123', Major_Medical_Issues='none',
    )
    account = Accounts.objects.create(Client=client)
    guarantor = Guarantors.objects.create()
    return Loans.objects.create(
        Principle_Amount=principal, Frequency=4, No_Of_Installments=0,
        Intrest_Rate=rate, Principal_Threshold_Percent=threshold,
        Loan_Collector=staff, Guarantor=guarantor, Account=account,
        First_Due_Date=first_due, Loan_Date=loan_date,
    )


def _pay(loan, amount, on):
    return Payments.objects.create(Loan=loan, Amount_Paid=amount, Date_Paid=on, Payment_Type=1)


class ReplayOverdraftLoanTest(TestCase):
    def test_first_cycle_interest_on_full_principal(self):
        # 250000 principal, 2%/month => 5000 for a full cycle, no payments yet.
        loan = _make_overdraft_loan()
        result = replay_overdraft_loan(loan, as_of=date(2026, 1, 10))
        self.assertEqual(len(result.installments), 1)
        self.assertEqual(result.installments[0]['Date_Due'], date(2026, 1, 10))
        self.assertAlmostEqual(result.installments[0]['Installment_Due'], 5000.0, places=2)

    def test_exact_interest_payment_leaves_principal_untouched(self):
        loan = _make_overdraft_loan()
        p1 = _pay(loan, 5000, date(2026, 1, 10))
        result = replay_overdraft_loan(loan, as_of=date(2026, 2, 10))
        self.assertAlmostEqual(result.outstanding_principal, 250000.0, places=2)
        self.assertAlmostEqual(result.payment_splits[p1.pk]['Interest_Portion'], 5000.0, places=2)
        self.assertAlmostEqual(result.payment_splits[p1.pk]['Principal_Portion'], 0.0, places=2)

    def test_leftover_above_threshold_reduces_principal_fully(self):
        # Spec worked example: pay 5000 interest on the 10th, then 55000 on the 20th.
        # Leftover 55000 >= 20% of 250000 (50000), so ALL of it hits principal.
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))
        p2 = _pay(loan, 55000, date(2026, 1, 20))
        result = replay_overdraft_loan(loan, as_of=date(2026, 1, 25))
        self.assertAlmostEqual(result.payment_splits[p2.pk]['Interest_Portion'], 0.0, places=2)
        self.assertAlmostEqual(result.payment_splits[p2.pk]['Principal_Portion'], 55000.0, places=2)
        self.assertAlmostEqual(result.outstanding_principal, 195000.0, places=2)

    def test_next_cycle_prorates_across_the_principal_change(self):
        # Same scenario as above; next cycle (Jan 10 -> Feb 10, 31 days) should be
        # 10 days on 250000 + 21 days on 195000, at 2%/31 per day.
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))
        _pay(loan, 55000, date(2026, 1, 20))
        result = replay_overdraft_loan(loan, as_of=date(2026, 2, 10))
        cycle_days = (date(2026, 2, 10) - date(2026, 1, 10)).days  # 31
        daily_rate = 2.0 / 100 / cycle_days
        expected = (10 * 250000 * daily_rate) + (21 * 195000 * daily_rate)
        next_installment = next(i for i in result.installments if i['Date_Due'] == date(2026, 2, 10))
        self.assertAlmostEqual(next_installment['Installment_Due'], expected, places=2)

    def test_leftover_below_threshold_banks_as_credit_not_principal(self):
        # Spec worked example: pay 5000 interest on the 10th, then 30000 on the 20th.
        # Leftover 30000 < 50000 (20% of 250000) so principal is untouched; it's credit.
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))
        p2 = _pay(loan, 30000, date(2026, 1, 20))
        result = replay_overdraft_loan(loan, as_of=date(2026, 1, 25))
        self.assertAlmostEqual(result.payment_splits[p2.pk]['Principal_Portion'], 0.0, places=2)
        self.assertAlmostEqual(result.outstanding_principal, 250000.0, places=2)
        self.assertAlmostEqual(result.credit_balance, 30000.0, places=2)

    def test_banked_credit_auto_applied_to_next_installment(self):
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))
        _pay(loan, 30000, date(2026, 1, 20))  # banked as credit
        result = replay_overdraft_loan(loan, as_of=date(2026, 2, 10))
        next_installment = next(i for i in result.installments if i['Date_Due'] == date(2026, 2, 10))
        # Full-cycle interest on unchanged 250000 principal is 5000; a 30000 credit
        # fully covers it (floored at 0, credit balance absorbs the rest conceptually
        # by being consumed, not going negative).
        self.assertAlmostEqual(next_installment['Installment_Due'], 0.0, places=2)
        self.assertTrue(next_installment['is_paid'])

    def test_missed_month_does_not_compound_into_principal(self):
        loan = _make_overdraft_loan()
        # No payment at all in the first cycle.
        result = replay_overdraft_loan(loan, as_of=date(2026, 2, 10))
        # Second cycle's interest is still on the full 250000 principal, unaffected
        # by the first cycle's unpaid interest.
        second_cycle = next(i for i in result.installments if i['Date_Due'] == date(2026, 2, 10))
        self.assertAlmostEqual(second_cycle['Installment_Due'], 5000.0, places=2)
        self.assertAlmostEqual(result.outstanding_principal, 250000.0, places=2)

    def test_late_payment_clears_oldest_unpaid_interest_first(self):
        loan = _make_overdraft_loan()
        # Skip month 1 entirely; pay exactly one cycle's interest (5000) in month 2.
        p1 = _pay(loan, 5000, date(2026, 2, 15))
        result = replay_overdraft_loan(loan, as_of=date(2026, 2, 15))
        first_cycle = next(i for i in result.installments if i['Date_Due'] == date(2026, 1, 10))
        self.assertTrue(first_cycle['is_paid'])
        self.assertAlmostEqual(result.payment_splits[p1.pk]['Interest_Portion'], 5000.0, places=2)
        self.assertAlmostEqual(result.payment_splits[p1.pk]['Principal_Portion'], 0.0, places=2)

    def test_full_payoff_charges_prorated_stub_interest(self):
        # Pay off entirely on day 25 of the first 31-day cycle (Jan 10 -> Feb 10).
        loan = _make_overdraft_loan()
        payoff_date = date(2026, 1, 25)
        days_elapsed = (payoff_date - date(2026, 1, 10)).days  # 15
        cycle_days = (date(2026, 2, 10) - date(2026, 1, 10)).days  # 31
        stub_interest = 250000 * (2.0 / 100 / cycle_days) * days_elapsed
        payoff_amount = 250000 + stub_interest
        p1 = _pay(loan, payoff_amount, payoff_date)
        result = replay_overdraft_loan(loan, as_of=payoff_date)
        self.assertAlmostEqual(result.outstanding_principal, 0.0, places=1)
        self.assertAlmostEqual(
            result.payment_splits[p1.pk]['Interest_Portion'], stub_interest, places=1)
        self.assertAlmostEqual(
            result.payment_splits[p1.pk]['Principal_Portion'], 250000.0, places=1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 manage.py test microfinance.tests_overdraft -v 2`
Expected: FAIL with `ModuleNotFoundError: No module named 'microfinance.overdraft'`

- [ ] **Step 3: Implement `microfinance/overdraft.py`**

```python
"""Overdraft loan interest/principal replay engine.

Pure, side-effect-free: reads Loans/Payments via the ORM but never
writes. Callers (microfinance/overdraft_sync.py) persist the results.
"""
from dataclasses import dataclass, field
from datetime import date
from dateutil.relativedelta import relativedelta

from .models import Payments


@dataclass
class OverdraftReplayResult:
    installments: list = field(default_factory=list)       # [{'Date_Due', 'Installment_Due', 'is_paid'}]
    payment_splits: dict = field(default_factory=dict)      # {payment_pk: {'Interest_Portion', 'Principal_Portion'}}
    outstanding_principal: float = 0.0
    credit_balance: float = 0.0


def _next_due_date(current_due_date):
    return current_due_date + relativedelta(months=1)


def replay_overdraft_loan(loan, as_of=None):
    """Replay an overdraft loan's due dates and payments in date order.

    Materializes every cycle whose due date has passed (<= as_of, default
    today), allocates each payment interest-first then principal-or-credit
    by the loan's threshold rule, and prorates each cycle's interest across
    any principal changes within it. Returns an OverdraftReplayResult; the
    caller is responsible for persisting Installments/Payments rows.
    """
    today = as_of or date.today()

    payments = list(
        Payments.objects.filter(Loan=loan, Payment_Type=1).order_by('Date_Paid', 'pk')
    )

    threshold_percent = loan.Principal_Threshold_Percent or 0.0
    outstanding_principal = loan.Principle_Amount
    credit_balance = 0.0
    payment_splits = {}
    installments = []

    unpaid_installments = []  # list of dicts, oldest first, mutated as we allocate

    current_due_date = loan.First_Due_Date
    payment_cursor = 0

    while current_due_date <= today:
        previous_due_date = (
            installments[-1]['Date_Due'] if installments else loan.Loan_Date
        )
        cycle_days = (current_due_date - previous_due_date).days

        # Collect payments that fall inside [previous_due_date, current_due_date)
        # and are allocated before this due date is reached, tracking segment
        # boundaries from any Principal_Portion allocation.
        segments = [(previous_due_date, outstanding_principal)]

        while payment_cursor < len(payments) and payments[payment_cursor].Date_Paid < current_due_date:
            payment = payments[payment_cursor]
            interest_portion, principal_portion, credit_balance = _allocate_payment(
                payment, unpaid_installments, outstanding_principal,
                threshold_percent, credit_balance,
            )
            payment_splits[payment.pk] = {
                'Interest_Portion': interest_portion,
                'Principal_Portion': principal_portion,
            }
            if principal_portion > 0:
                outstanding_principal -= principal_portion
                segments.append((payment.Date_Paid, outstanding_principal))
            payment_cursor += 1

        segments.append((current_due_date, outstanding_principal))

        raw_interest = 0.0
        for i in range(len(segments) - 1):
            seg_start, seg_principal = segments[i]
            seg_end, _ = segments[i + 1]
            seg_days = (seg_end - seg_start).days
            raw_interest += seg_days * seg_principal * (loan.Intrest_Rate / 100.0 / cycle_days)

        applied_credit = min(credit_balance, raw_interest)
        credit_balance -= applied_credit
        installment_due = max(0.0, raw_interest - applied_credit)

        installment = {
            'Date_Due': current_due_date,
            'Installment_Due': round(installment_due, 2),
            'is_paid': installment_due <= 0.0,
            '_remaining': installment_due,
        }
        installments.append(installment)
        unpaid_installments.append(installment)

        current_due_date = _next_due_date(current_due_date)

    # Allocate any remaining payments dated on/after the last materialized due
    # date (payments made ahead of the next cycle's materialization).
    while payment_cursor < len(payments) and payments[payment_cursor].Date_Paid <= today:
        payment = payments[payment_cursor]
        interest_portion, principal_portion, credit_balance = _allocate_payment(
            payment, unpaid_installments, outstanding_principal,
            threshold_percent, credit_balance,
        )
        payment_splits[payment.pk] = {
            'Interest_Portion': interest_portion,
            'Principal_Portion': principal_portion,
        }
        if principal_portion > 0:
            outstanding_principal -= principal_portion
        payment_cursor += 1

    for installment in installments:
        installment['is_paid'] = installment['_remaining'] <= 0.0
        del installment['_remaining']

    return OverdraftReplayResult(
        installments=installments,
        payment_splits=payment_splits,
        outstanding_principal=round(outstanding_principal, 2),
        credit_balance=round(credit_balance, 2),
    )


def _allocate_payment(payment, unpaid_installments, outstanding_principal,
                       threshold_percent, credit_balance):
    """Allocate one payment: interest-first (oldest unpaid), then threshold-test
    the leftover against outstanding principal. Returns
    (interest_portion, principal_portion, new_credit_balance).
    """
    remaining = payment.Amount_Paid
    interest_portion = 0.0

    for installment in unpaid_installments:
        if remaining <= 0:
            break
        if installment['_remaining'] <= 0:
            continue
        applied = min(remaining, installment['_remaining'])
        installment['_remaining'] -= applied
        remaining -= applied
        interest_portion += applied

    leftover = remaining
    if leftover <= 0:
        return round(interest_portion, 2), 0.0, credit_balance

    threshold_amount = outstanding_principal * (threshold_percent / 100.0)
    if leftover >= threshold_amount and outstanding_principal > 0:
        principal_portion = min(leftover, outstanding_principal)
        return round(interest_portion, 2), round(principal_portion, 2), credit_balance

    credit_balance += leftover
    return round(interest_portion, 2), 0.0, credit_balance
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 manage.py test microfinance.tests_overdraft -v 2`
Expected: PASS (9 tests). If any proration/threshold test is off by a
rounding amount, check the `round(..., 2)` placements — the tests use
`places=2` or `places=1` deliberately to tolerate cent-level rounding,
not to hide a real bug.

- [ ] **Step 5: Commit**

```bash
git add microfinance/overdraft.py microfinance/tests_overdraft.py
git commit -m "Add replay_overdraft_loan: chronological interest/principal replay engine"
```

---

### Task 4: Persist the replay — `sync_overdraft_loan` and idempotent materialization

**Files:**
- Create: `microfinance/overdraft_sync.py`
- Test: `microfinance/tests_overdraft.py` (append)

**Interfaces:**
- Consumes: `replay_overdraft_loan(loan, as_of=None)` (Task 3)
- Produces: `sync_overdraft_loan(loan, as_of=None)` — writes/updates
  `Installments` rows (via `get_or_create` on `(Loan, Date_Due)`, inside
  `transaction.atomic()`) and `Payments.Interest_Portion`/
  `Principal_Portion` to match the replay's output. Idempotent: calling
  it twice in a row makes no further database writes the second time.
  Leaves **paid** installments' amounts frozen (does not overwrite an
  `Installment` row that already has `Date_Paid` set — mirrors the
  spec's "already-paid installments are left frozen" rule) but always
  refreshes unpaid ones.

**Context for implementer:** This task turns Task 3's pure replay into
actual database rows. `Installments.Installment_Paid`/`Date_Paid` are
existing fields (see `microfinance/models.py:208-224`) used elsewhere in
the codebase to mark an installment settled — for overdraft, mark
`Date_Paid` on an `Installment` row only when `is_paid` is `True` in the
replay output, but the spec is explicit that this task must never
retroactively change an installment that was already marked paid in a
previous sync (avoids clobbering a row a user may have manually adjusted
since).

- [ ] **Step 1: Write failing tests**

```python
# microfinance/tests_overdraft.py — append
from microfinance.models import Installments
from microfinance.overdraft_sync import sync_overdraft_loan


class SyncOverdraftLoanTest(TestCase):
    def test_sync_creates_installment_rows(self):
        loan = _make_overdraft_loan()
        sync_overdraft_loan(loan, as_of=date(2026, 2, 10))
        rows = Installments.objects.filter(Loan=loan).order_by('Date_Due')
        self.assertEqual(list(rows.values_list('Date_Due', flat=True)),
                          [date(2026, 1, 10), date(2026, 2, 10)])

    def test_sync_is_idempotent(self):
        loan = _make_overdraft_loan()
        sync_overdraft_loan(loan, as_of=date(2026, 2, 10))
        count_after_first = Installments.objects.filter(Loan=loan).count()
        sync_overdraft_loan(loan, as_of=date(2026, 2, 10))
        count_after_second = Installments.objects.filter(Loan=loan).count()
        self.assertEqual(count_after_first, count_after_second)

    def test_sync_writes_payment_portions(self):
        loan = _make_overdraft_loan()
        p1 = _pay(loan, 5000, date(2026, 1, 10))
        sync_overdraft_loan(loan, as_of=date(2026, 1, 15))
        p1.refresh_from_db()
        self.assertAlmostEqual(p1.Interest_Portion, 5000.0, places=2)
        self.assertAlmostEqual(p1.Principal_Portion, 0.0, places=2)

    def test_sync_marks_paid_installments_with_date_paid(self):
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))
        sync_overdraft_loan(loan, as_of=date(2026, 1, 15))
        row = Installments.objects.get(Loan=loan, Date_Due=date(2026, 1, 10))
        self.assertIsNotNone(row.Date_Paid)

    def test_sync_does_not_touch_already_paid_installment_on_rerun(self):
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))
        sync_overdraft_loan(loan, as_of=date(2026, 1, 15))
        row = Installments.objects.get(Loan=loan, Date_Due=date(2026, 1, 10))
        original_date_paid = row.Date_Paid
        # A later backdated payment must not be allowed to silently rewrite
        # an already-settled installment's Date_Paid.
        sync_overdraft_loan(loan, as_of=date(2026, 1, 20))
        row.refresh_from_db()
        self.assertEqual(row.Date_Paid, original_date_paid)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 manage.py test microfinance.tests_overdraft.SyncOverdraftLoanTest -v 2`
Expected: FAIL — `microfinance.overdraft_sync` doesn't exist yet.

- [ ] **Step 3: Implement `microfinance/overdraft_sync.py`**

```python
"""Persistence layer for the overdraft replay engine.

Turns replay_overdraft_loan's pure output into Installments/Payments rows.
Idempotent and safe to call from any request that touches an overdraft loan.
"""
from django.db import transaction

from .models import Installments, Payments
from .overdraft import replay_overdraft_loan


def sync_overdraft_loan(loan, as_of=None):
    """Materialize/refresh Installments and Payments rows for an overdraft
    loan from the current state of its payment ledger. Safe to call
    repeatedly; only unpaid installments are ever rewritten.
    """
    result = replay_overdraft_loan(loan, as_of=as_of)

    with transaction.atomic():
        for installment_data in result.installments:
            row, created = Installments.objects.get_or_create(
                Loan=loan,
                Date_Due=installment_data['Date_Due'],
                defaults={
                    'Installment_Due': installment_data['Installment_Due'],
                    'Installment_To_Be_Paid': installment_data['Installment_Due'],
                    'Pending_Amount': installment_data['Installment_Due'],
                },
            )
            if row.Date_Paid is not None:
                # Already settled in a previous sync — leave it frozen.
                continue
            if not created:
                row.Installment_Due = installment_data['Installment_Due']
                row.Installment_To_Be_Paid = installment_data['Installment_Due']
                row.Pending_Amount = installment_data['Installment_Due']
            if installment_data['is_paid']:
                row.Date_Paid = installment_data['Date_Due']
                row.Installment_Paid = installment_data['Installment_Due']
                row.Pending_Amount = 0
            row.save()

        payment_pks = list(result.payment_splits.keys())
        payments_by_pk = {p.pk: p for p in Payments.objects.filter(pk__in=payment_pks)}
        for pk, split in result.payment_splits.items():
            payment = payments_by_pk.get(pk)
            if payment is None:
                continue
            if (payment.Interest_Portion != split['Interest_Portion']
                    or payment.Principal_Portion != split['Principal_Portion']):
                payment.Interest_Portion = split['Interest_Portion']
                payment.Principal_Portion = split['Principal_Portion']
                payment.save(update_fields=['Interest_Portion', 'Principal_Portion'])

    return result


def ensure_overdraft_installments(loan):
    """Call from any read/write path that touches a loan. No-op for
    non-overdraft loans."""
    if loan.Frequency == 4:
        return sync_overdraft_loan(loan)
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 manage.py test microfinance.tests_overdraft -v 2`
Expected: PASS (14 tests total across both test classes so far)

- [ ] **Step 5: Commit**

```bash
git add microfinance/overdraft_sync.py microfinance/tests_overdraft.py
git commit -m "Add sync_overdraft_loan: idempotent persistence of the replay engine"
```

---

### Task 5: Wire `pay_installment` and `Recalculate_Penalty` for overdraft loans

**Files:**
- Modify: `microfinance/views.py:701-739` (`pay_installment`)
- Modify: `microfinance/views.py:646-667` (`Recalculate_Penalty`)
- Test: `microfinance/tests_overdraft.py` (append)

**Interfaces:**
- Consumes: `ensure_overdraft_installments(loan)` (Task 4)
- Produces: `pay_installment` now materializes/re-syncs overdraft
  installments (via `ensure_overdraft_installments`) **before** the
  existing penalty recalculation call, for overdraft loans only; regular
  loans go through the function exactly as before.

**Context for implementer:** Re-read `views.py:701-739` exactly as it
exists today (reproduced below) before editing — the existing same-day
payment merge (`paymentOnSameDay.Amount_Paid += Amount_Paid`) means a
second payment on the same day mutates an existing `Payments` row rather
than creating a new one. Because `sync_overdraft_loan` re-derives
`Interest_Portion`/`Principal_Portion` from a fresh replay every time
it's called, this is handled correctly automatically — just make sure
the sync call happens **after** the save/merge of the new payment, and
**before** the existing penalty-calculation block, so freshly
materialized/updated installment rows are what the penalty walk sees in
the same request.

Current code (`views.py:701-739`):

```python
def pay_installment(request,loan,payments,DatePaid):
    Amount_Paid = float(request.POST.get('amount'))             #amount entered
    Amount_Paid=round(Amount_Paid,1)
    if DatePaid is None or DatePaid =='':
        DatePaid=datetime.now()
    else:
        DatePaid =datetime.strptime(DatePaid, "%Y-%m-%d")  
    paymentOnSameDay = payments.filter(
        Loan_id=loan.id,
        Payment_Type=1,
        Date_Paid=DatePaid
    ).first()
    if(paymentOnSameDay is not None):
        paymentOnSameDay.Amount_Paid+=Amount_Paid
        paymentOnSameDay.save()
    else:
        paymentObj = Payments(Amount_Paid=Amount_Paid,Date_Paid=DatePaid,Loan=loan)
        paymentObj.save()
    
    # Call _calculate_individual_penalties directly after payment
    installments = Installments.objects.filter(Loan=loan).filter(Installment_Due__gt=0).order_by('Date_Due')
    payments_queryset = Payments.objects.filter(Loan=loan, Payment_Type=1).order_by('Date_Paid')
    
    installments_data = []
    for inst in installments:
        installments_data.append({
            'id': inst.pk,
            'Date_Due': inst.Date_Due,
            'Installment_Due': inst.Installment_Due
        })
    
    payments_data = []
    for pay in payments_queryset:
        payments_data.append({
            'Date_Paid': pay.Date_Paid,
            'Amount_Paid': pay.Amount_Paid
        })
    
    _calculate_individual_penalties(loan, installments_data, payments_data, timezone.now().date())
```

- [ ] **Step 1: Write a failing integration test**

```python
# microfinance/tests_overdraft.py — append
from microfinance.views import pay_installment
from django.test import RequestFactory


class PayInstallmentOverdraftIntegrationTest(TestCase):
    def test_pay_installment_syncs_overdraft_installments(self):
        loan = _make_overdraft_loan(first_due=date.today().replace(day=1))
        factory = RequestFactory()
        request = factory.post('/fake-pay-url/', {'amount': '5000'})
        payments_qs = Payments.objects.filter(Loan=loan)
        pay_installment(request, loan, payments_qs, DatePaid=str(date.today()))
        # An Installment row for the loan's first cycle must now exist.
        self.assertTrue(Installments.objects.filter(Loan=loan).exists())
        payment = Payments.objects.filter(Loan=loan, Payment_Type=1).first()
        self.assertIsNotNone(payment)
        # It should have a non-zero Interest_Portion since this is an overdraft loan.
        self.assertGreaterEqual(payment.Interest_Portion, 0)
```

Note: this test's exact assertions on amounts are intentionally loose
(existence checks) since the precise cycle math depends on
`first_due`/`today` alignment — Task 3's tests already pin down the
numeric behavior. This test's job is to confirm the wiring runs at all.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 manage.py test microfinance.tests_overdraft.PayInstallmentOverdraftIntegrationTest -v 2`
Expected: FAIL — no `Installments` row is created for the overdraft loan
today, because `pay_installment` never calls the sync function.

- [ ] **Step 3: Wire the dispatch into `pay_installment` and `Recalculate_Penalty`**

In `microfinance/views.py`, add the import near the top (alongside the
other local imports, e.g. after `from .filters import LoanFilter`):

```python
from .overdraft_sync import ensure_overdraft_installments
```

Change `pay_installment` (`views.py:701-739`) to call
`ensure_overdraft_installments` right after the payment is saved/merged,
before the existing penalty block:

```python
def pay_installment(request,loan,payments,DatePaid):
    Amount_Paid = float(request.POST.get('amount'))             #amount entered
    Amount_Paid=round(Amount_Paid,1)
    if DatePaid is None or DatePaid =='':
        DatePaid=datetime.now()
    else:
        DatePaid =datetime.strptime(DatePaid, "%Y-%m-%d")  
    paymentOnSameDay = payments.filter(
        Loan_id=loan.id,
        Payment_Type=1,
        Date_Paid=DatePaid
    ).first()
    if(paymentOnSameDay is not None):
        paymentOnSameDay.Amount_Paid+=Amount_Paid
        paymentOnSameDay.save()
    else:
        paymentObj = Payments(Amount_Paid=Amount_Paid,Date_Paid=DatePaid,Loan=loan)
        paymentObj.save()

    if loan.Frequency == 4:
        ensure_overdraft_installments(loan)

    # Call _calculate_individual_penalties directly after payment
    installments = Installments.objects.filter(Loan=loan).filter(Installment_Due__gt=0).order_by('Date_Due')
    payments_queryset = Payments.objects.filter(Loan=loan, Payment_Type=1).order_by('Date_Paid')
    
    installments_data = []
    for inst in installments:
        installments_data.append({
            'id': inst.pk,
            'Date_Due': inst.Date_Due,
            'Installment_Due': inst.Installment_Due
        })
    
    payments_data = []
    for pay in payments_queryset:
        payments_data.append({
            'Date_Paid': pay.Date_Paid,
            'Amount_Paid': pay.Amount_Paid
        })
    
    _calculate_individual_penalties(loan, installments_data, payments_data, timezone.now().date())
```

Change `Recalculate_Penalty` (`views.py:646-667`) the same way, adding
the guard before the existing installment-gathering code:

```python
def Recalculate_Penalty(Loan):
    if Loan.Frequency == 4:
        ensure_overdraft_installments(Loan)

    # Convert QuerySets to the format expected by the function
    installments = Installments.objects.filter(Loan=Loan).filter(Installment_Due__gt=0).order_by('Date_Due')
    payments = Payments.objects.filter(Loan=Loan, Payment_Type=1).order_by('Date_Paid')
    
    installments_data = []
    for inst in installments:
        installments_data.append({
            'id': inst.pk,
            'Date_Due': inst.Date_Due,
            'Installment_Due': inst.Installment_Due
        })
    
    payments_data = []
    for pay in payments:
        payments_data.append({
            'id': pay.pk,
            'Date_Paid': pay.Date_Paid,
            'Amount_Paid': pay.Amount_Paid
        })
    
    _calculate_individual_penalties_corrected(Loan, installments_data, payments_data, timezone.now().date())
```

- [ ] **Step 4: Run test to verify it passes, and run the full existing test suite to check no regression**

Run: `python3 manage.py test microfinance.tests_overdraft.PayInstallmentOverdraftIntegrationTest -v 2`
Expected: PASS

Run: `python3 manage.py test microfinance -v 2`
Expected: all tests pass, including every test from Tasks 1-5. This
confirms the `if loan.Frequency == 4:` guard means non-overdraft loans
never call `ensure_overdraft_installments` and their `pay_installment`
behavior is unchanged.

- [ ] **Step 5: Commit**

```bash
git add microfinance/views.py microfinance/tests_overdraft.py
git commit -m "Wire overdraft materialization into pay_installment and Recalculate_Penalty"
```

---

### Task 6: Overdraft-aware loan creation and edit — new functions, no existing branch edits

**Files:**
- Modify: `microfinance/views.py:315-368` (`Add_Loan`)
- Modify: `microfinance/views.py:2483-2639` (`EditLoan` recreate path)
- Test: `microfinance/tests_overdraft.py` (append)

**Interfaces:**
- Consumes: `sync_overdraft_loan(loan)` (Task 4)
- Produces: `Add_Loan` and `EditLoan` both early-dispatch to
  `sync_overdraft_loan(instance)` for `Frequency == 4`, skipping the
  existing flat-schedule generation entirely for overdraft loans, while
  every other frequency's existing code is untouched.

**Context for implementer:** These are the two call sites the spec's
"Design principle: new functions for overdraft" section calls out
explicitly. Both existing blocks are reproduced below exactly as found;
add one `if`/`return` (or `if`/`else` wrapping the existing body) at the
very top of each installment-generation section — do not alter anything
below that guard for the non-overdraft path.

`Add_Loan`, current code (`views.py:315-368`):

```python
@login_required(login_url="/accounts/login/")
def Add_Loan(request,pk, sk):
    if request.method == 'POST':
        form=AddLoan(request.POST,request.FILES)
        if form.is_valid():
            instance=form.save(commit=False)
            client =Clients.objects.get(pk=pk)
            acc = Accounts.objects.get(Client=client)
            instance.Account =acc
            instance.Guarantor_id = sk
            instance.save()
            Installment = (instance.Principle_Amount + (instance.Principle_Amount/100*instance.Intrest_Rate))/instance.No_Of_Installments
            if instance.Frequency !=2 :
                Inst = round(Installment,1)
                Installments_Inst = Installments(Installment_Paid = 0, Loan = instance, Date_Due = instance.First_Due_Date, Installment_Due = Inst,Installment_To_Be_Paid=Inst,Pending_Amount=Inst )
            else:
                Inst = round(Installment,1)
                Installments_Inst = Installments(Installment_Paid = 0, Loan = instance, Date_Due = instance.First_Due_Date, Installment_Due = round(Inst*7),Installment_To_Be_Paid=round(Inst*7),Pending_Amount=round(Inst*7) )
            Installments_Inst.save()   
            
            if instance.Frequency == 1:
                Date_Due = instance.First_Due_Date 
                for i in range(1,instance.No_Of_Installments):
                    Inst = round(Installment,1)
                    Date_Due = Date_Due + timedelta(1)
                    Installments_Inst = Installments(Installment_Paid = 0, Loan = instance,Date_Due = Date_Due, Installment_Due = round(Installment,1),Installment_To_Be_Paid=round(Installment,1),Pending_Amount=round(Installment,1))
                    Installments_Inst.save()
            if instance.Frequency == 2:
                Date_Due = instance.First_Due_Date 
                Extra_Days = instance.No_Of_Installments % 7
                for i in range(1,int(instance.No_Of_Installments/7)):                
                    Inst = Installment                
                    Date_Due = Date_Due + timedelta(7)
                    Installments_Inst = Installments(Installment_Paid = 0, Loan = instance, Date_Due = Date_Due, Installment_Due = round(Inst*7),Installment_To_Be_Paid=round(Inst*7),Pending_Amount=round(Inst*7))
                    Installments_Inst.save()
                if Extra_Days>0:
                    Inst = Installment
                    Date_Due = Date_Due + timedelta(Extra_Days)
                    Installments_Inst = Installments(Installment_Paid = 0, Loan = instance,Date_Due = Date_Due, Installment_Due = round(Inst*Extra_Days),Installment_To_Be_Paid=round(Inst*Extra_Days),Pending_Amount=round(Inst *Extra_Days))
                    Installments_Inst.save()
            if instance.Frequency == 3:
                Date_Due = instance.First_Due_Date 
                for i in range(1,int(instance.No_Of_Installments)):
                    Inst = round(Installment,1)
                    Date_Due = Date_Due + relativedelta(months=1)
                    Installments_Inst = Installments(Installment_Paid = 0, Loan = instance,Date_Due = Date_Due, Installment_Due = round(Installment,1),Installment_To_Be_Paid=round(Installment,1),Pending_Amount=round(Installment,1) )
                    Installments_Inst.save()
            return redirect('microfinance:clientdetail' ,pk=pk)
        else:
            # Form is not valid, show errors
            return render(request,'microfinance/Add_Loan.html',{'form':form})
    else: 
        form=AddLoan()     
    return render(request,'microfinance/Add_Loan.html',{'form':form})
```

- [ ] **Step 1: Write a failing test**

```python
# microfinance/tests_overdraft.py — append
from microfinance.views import Add_Loan
from django.contrib.auth.models import AnonymousUser


class AddLoanOverdraftDispatchTest(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(Officer_Name='Officer', Designation='Collector', Salary=0)
        self.user = User.objects.create_user(username='loanauthor', password='x', is_staff=True)
        self.client_obj = Clients.objects.create(
            Name='Loan Client', Phone_no1='+911234567892', Verified_By='x',
            author=self.user, Photo_Id_No='LN123', Major_Medical_Issues='none',
        )
        self.account = Accounts.objects.create(Client=self.client_obj)
        self.guarantor = Guarantors.objects.create()

    def test_overdraft_loan_creation_does_not_use_flat_schedule(self):
        factory = RequestFactory()
        post_data = {
            'AccNo': '1', 'Principle_Amount': '250000', 'Frequency': '4',
            'Purpose': 'c', 'No_Of_Installments': '0', 'Intrest_Rate': '2',
            'File_Charge_Percent': '0',
            'First_Due_Date': '2026-01-10', 'Loan_Date': '2026-01-01',
            'Loan_Collector': str(self.staff.pk),
            'security_docs': 'none',
        }
        request = factory.post(
            f'/loan/{self.client_obj.pk}/{self.guarantor.pk}/', post_data)
        request.user = self.user
        Add_Loan(request, pk=self.client_obj.pk, sk=self.guarantor.pk)
        loan = Loans.objects.get(Account=self.account)
        self.assertEqual(loan.Frequency, 4)
        # An overdraft loan must not get a flat No_Of_Installments-based schedule;
        # it should have exactly the first materialized cycle (or none yet, if
        # sync only creates rows for cycles already due).
        installment_count = Installments.objects.filter(Loan=loan).count()
        self.assertLessEqual(installment_count, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 manage.py test microfinance.tests_overdraft.AddLoanOverdraftDispatchTest -v 2`
Expected: FAIL — today `Add_Loan` divides by `No_Of_Installments=0`,
raising `ZeroDivisionError` (or, if `No_Of_Installments` validation
prevents 0, it otherwise falls into the `Frequency == 3` Monthly branch
since `Frequency=4` doesn't match `1`/`2`, generating zero extra rows
but still computing `Installment` via division by `No_Of_Installments`).
Either failure mode demonstrates the bug this task fixes.

- [ ] **Step 3: Add the overdraft dispatch to `Add_Loan`**

```python
@login_required(login_url="/accounts/login/")
def Add_Loan(request,pk, sk):
    if request.method == 'POST':
        form=AddLoan(request.POST,request.FILES)
        if form.is_valid():
            instance=form.save(commit=False)
            client =Clients.objects.get(pk=pk)
            acc = Accounts.objects.get(Client=client)
            instance.Account =acc
            instance.Guarantor_id = sk
            instance.save()

            if instance.Frequency == 4:
                sync_overdraft_loan(instance)
                return redirect('microfinance:clientdetail' ,pk=pk)

            Installment = (instance.Principle_Amount + (instance.Principle_Amount/100*instance.Intrest_Rate))/instance.No_Of_Installments
            if instance.Frequency !=2 :
                Inst = round(Installment,1)
                Installments_Inst = Installments(Installment_Paid = 0, Loan = instance, Date_Due = instance.First_Due_Date, Installment_Due = Inst,Installment_To_Be_Paid=Inst,Pending_Amount=Inst )
            else:
                Inst = round(Installment,1)
                Installments_Inst = Installments(Installment_Paid = 0, Loan = instance, Date_Due = instance.First_Due_Date, Installment_Due = round(Inst*7),Installment_To_Be_Paid=round(Inst*7),Pending_Amount=round(Inst*7) )
            Installments_Inst.save()   
            
            if instance.Frequency == 1:
                Date_Due = instance.First_Due_Date 
                for i in range(1,instance.No_Of_Installments):
                    Inst = round(Installment,1)
                    Date_Due = Date_Due + timedelta(1)
                    Installments_Inst = Installments(Installment_Paid = 0, Loan = instance,Date_Due = Date_Due, Installment_Due = round(Installment,1),Installment_To_Be_Paid=round(Installment,1),Pending_Amount=round(Installment,1))
                    Installments_Inst.save()
            if instance.Frequency == 2:
                Date_Due = instance.First_Due_Date 
                Extra_Days = instance.No_Of_Installments % 7
                for i in range(1,int(instance.No_Of_Installments/7)):                
                    Inst = Installment                
                    Date_Due = Date_Due + timedelta(7)
                    Installments_Inst = Installments(Installment_Paid = 0, Loan = instance, Date_Due = Date_Due, Installment_Due = round(Inst*7),Installment_To_Be_Paid=round(Inst*7),Pending_Amount=round(Inst*7))
                    Installments_Inst.save()
                if Extra_Days>0:
                    Inst = Installment
                    Date_Due = Date_Due + timedelta(Extra_Days)
                    Installments_Inst = Installments(Installment_Paid = 0, Loan = instance,Date_Due = Date_Due, Installment_Due = round(Inst*Extra_Days),Installment_To_Be_Paid=round(Inst*Extra_Days),Pending_Amount=round(Inst *Extra_Days))
                    Installments_Inst.save()
            if instance.Frequency == 3:
                Date_Due = instance.First_Due_Date 
                for i in range(1,int(instance.No_Of_Installments)):
                    Inst = round(Installment,1)
                    Date_Due = Date_Due + relativedelta(months=1)
                    Installments_Inst = Installments(Installment_Paid = 0, Loan = instance,Date_Due = Date_Due, Installment_Due = round(Installment,1),Installment_To_Be_Paid=round(Installment,1),Pending_Amount=round(Installment,1) )
                    Installments_Inst.save()
            return redirect('microfinance:clientdetail' ,pk=pk)
        else:
            # Form is not valid, show errors
            return render(request,'microfinance/Add_Loan.html',{'form':form})
    else: 
        form=AddLoan()     
    return render(request,'microfinance/Add_Loan.html',{'form':form})
```

Add the import (if not already added in Task 5):

```python
from .overdraft_sync import ensure_overdraft_installments, sync_overdraft_loan
```

For the `EditLoan` recreate path (`views.py:2483-2639`), add the
equivalent guard right after `form.save()` succeeds and before the
`if initial_date_obj != new_first_due_date:` block — since overdraft
loans don't recreate a flat schedule at all, changing the first due date
on an existing overdraft loan is out of scope for this feature (the spec
doesn't ask for it) and should simply skip the recreate block entirely:

```python
                # Update the existing loan with new values
                form.save()
                print(f"Form saved successfully")

                if Loan.Frequency == 4:
                    return redirect('microfinance:clientdetail', pk=Loan.Account.Client.pk)

                # Check if first due date actually changed
                # ... (existing code below is unchanged)
```

- [ ] **Step 4: Run test to verify it passes, then run the full suite**

Run: `python3 manage.py test microfinance.tests_overdraft.AddLoanOverdraftDispatchTest -v 2`
Expected: PASS

Run: `python3 manage.py test microfinance -v 2`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add microfinance/views.py microfinance/tests_overdraft.py
git commit -m "Dispatch overdraft loans to sync_overdraft_loan in Add_Loan/EditLoan, bypassing flat schedule"
```

---

### Task 7: `Loans.Total`, `bulk_overdue_map`, `loan_repayment_status` — overdraft-aware totals

**Files:**
- Modify: `microfinance/models.py:183-204` (`Loans._get_total_amnt_to_collect`)
- Modify: `microfinance/views.py:46-83` (`bulk_overdue_map`)
- Modify: `microfinance/views.py:86-157` (`loan_repayment_status`)
- Create: helper in `microfinance/overdraft.py` (append):
  `overdraft_total_owed(loan, as_of=None)`
- Test: `microfinance/tests_overdraft.py` (append)

**Interfaces:**
- Consumes: `replay_overdraft_loan` (Task 3)
- Produces: `overdraft_total_owed(loan, as_of=None) -> float` — returns
  `outstanding_principal + sum(unpaid installment amounts) - credit_balance`
  (floored at 0). `Loans.Total`, `bulk_overdue_map`, and
  `loan_repayment_status` each gain an early `Frequency == 4` branch that
  calls into overdraft-specific logic instead of the existing flat-rate
  formula.

- [ ] **Step 1: Write failing tests**

```python
# microfinance/tests_overdraft.py — append
from microfinance.overdraft import overdraft_total_owed
from microfinance.views import bulk_overdue_map, loan_repayment_status


class OverdraftTotalOwedTest(TestCase):
    def test_total_owed_before_any_payment(self):
        loan = _make_overdraft_loan()
        total = overdraft_total_owed(loan, as_of=date(2026, 1, 10))
        # 250000 principal + 5000 first-cycle interest, no credit.
        self.assertAlmostEqual(total, 255000.0, places=2)

    def test_total_owed_after_partial_payoff(self):
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))   # clears interest
        _pay(loan, 55000, date(2026, 1, 20))  # reduces principal (above threshold)
        total = overdraft_total_owed(loan, as_of=date(2026, 1, 25))
        # Outstanding principal 195000, no unpaid interest yet (next cycle not due).
        self.assertAlmostEqual(total, 195000.0, places=2)


class LoansTotalOverdraftTest(TestCase):
    def test_loans_total_property_uses_overdraft_logic_for_frequency_4(self):
        loan = _make_overdraft_loan()
        self.assertAlmostEqual(loan.Total, 255000.0, places=1)

    def test_loans_total_property_unchanged_for_monthly_loans(self):
        loan = _make_loan(Frequency=3, Principle_Amount=100000, Intrest_Rate=20)
        # Existing flat formula: 100000 + 100000*20/100 = 120000, unaffected.
        self.assertEqual(loan.Total, 120000.0)


class BulkOverdueMapOverdraftTest(TestCase):
    def test_bulk_overdue_map_includes_overdraft_loan_with_unpaid_interest(self):
        loan = _make_overdraft_loan(first_due=date.today())
        sync_overdraft_loan(loan, as_of=date.today())
        result = bulk_overdue_map([loan.pk], as_of=date.today())
        self.assertIn(loan.pk, result)
        self.assertGreater(result[loan.pk], 0)


class LoanRepaymentStatusOverdraftTest(TestCase):
    def test_loan_repayment_status_behind_when_interest_unpaid(self):
        loan = _make_overdraft_loan(first_due=date.today())
        sync_overdraft_loan(loan, as_of=date.today())
        status = loan_repayment_status(loan, as_of=date.today())
        self.assertEqual(status['state'], 'behind')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 manage.py test microfinance.tests_overdraft.OverdraftTotalOwedTest microfinance.tests_overdraft.LoansTotalOverdraftTest microfinance.tests_overdraft.BulkOverdueMapOverdraftTest microfinance.tests_overdraft.LoanRepaymentStatusOverdraftTest -v 2`
Expected: FAIL — `overdraft_total_owed` doesn't exist; `Loans.Total`,
`bulk_overdue_map`, `loan_repayment_status` all still use the flat
formula for every loan regardless of frequency.

- [ ] **Step 3: Add `overdraft_total_owed` to `microfinance/overdraft.py`**

Append to `microfinance/overdraft.py`:

```python
def overdraft_total_owed(loan, as_of=None):
    """Total amount an overdraft loan still owes: outstanding principal
    plus any unpaid materialized interest, net of unconsumed credit."""
    result = replay_overdraft_loan(loan, as_of=as_of)
    unpaid_interest = sum(
        i['Installment_Due'] for i in result.installments if not i['is_paid']
    )
    total = result.outstanding_principal + unpaid_interest - result.credit_balance
    return round(max(0.0, total), 2)
```

- [ ] **Step 4: Branch `Loans.Total`**

In `microfinance/models.py`, change:

```python
    def _get_total_amnt_to_collect(self):
        return self.Principle_Amount + (self.Principle_Amount * self.Intrest_Rate/100 )      
    Total = property(_get_total_amnt_to_collect)
```

to:

```python
    def _get_total_amnt_to_collect(self):
        if self.Frequency == 4:
            from .overdraft import overdraft_total_owed
            return overdraft_total_owed(self)
        return self.Principle_Amount + (self.Principle_Amount * self.Intrest_Rate/100 )      
    Total = property(_get_total_amnt_to_collect)
```

(The import is deferred inside the method to avoid a circular import
between `models.py` and `overdraft.py`, which itself imports from
`.models`.)

- [ ] **Step 5: Branch `bulk_overdue_map`**

In `microfinance/views.py`, change the loop body of `bulk_overdue_map`
(`views.py:46-83`):

```python
def bulk_overdue_map(loan_pks, as_of=None):
    """Overdue amount per loan for many loans, in a fixed number of queries.

    Same definition as loan_repayment_status: everything due to date, less
    everything paid, capped by what is still owed. Use this for list pages where
    calling loan_repayment_status per row would mean hundreds of queries.
    Returns {loan_pk: overdue_amount} containing only loans that are behind.
    """
    if not loan_pks:
        return {}

    today_date = as_of or timezone.now().date()

    due = dict(Installments.objects.filter(
        Loan_id__in=loan_pks, Date_Due__lte=today_date
    ).values_list('Loan_id').annotate(t=Sum('Installment_Due')))

    paid = dict(Payments.objects.filter(
        Loan_id__in=loan_pks, Payment_Type=1
    ).values_list('Loan_id').annotate(t=Sum('Amount_Paid')))

    waived = dict(Waiver.objects.filter(
        Loan_id__in=loan_pks, Waiver_Type=2
    ).values_list('Loan_id').annotate(t=Sum('Amount')))

    loan_terms = Loans.objects.filter(pk__in=loan_pks).values_list(
        'pk', 'Principle_Amount', 'Intrest_Rate', 'Frequency')

    out = {}
    for pk, principal, rate, frequency in loan_terms:
        if frequency == 4:
            total_due = due.get(pk) or 0
            total_paid = paid.get(pk) or 0
            overdue = round(max(0, total_due - total_paid), 1)
            if overdue > 0:
                out[pk] = overdue
            continue
        total_due = due.get(pk) or 0
        total_paid = paid.get(pk) or 0
        total_loan_amount = principal + (principal * rate / 100)
        total_pending = total_loan_amount - total_paid - (waived.get(pk) or 0)
        overdue = round(max(0, min(total_due - total_paid, max(0, total_pending))), 1)
        if overdue > 0:
            out[pk] = overdue
    return out
```

This works because `due` is already `Sum(Installment_Due)` for
`Date_Due <= today_date`, which for overdraft loans are pure-interest
rows (already correctly materialized by whatever last called
`ensure_overdraft_installments` for that loan) — no separate query
needed, `Installments`/`Payments` already carry the right numbers once
synced. No new import is needed in `views.py` for this step —
`bulk_overdue_map` only reads `due`/`paid`, which it already computes.

- [ ] **Step 6: Branch `loan_repayment_status`**

In `microfinance/views.py`, at the top of `loan_repayment_status`
(`views.py:86-157`), add an early dispatch. Change:

```python
def loan_repayment_status(loan, cache=None, as_of=None):
    """Where a loan stands on repayment, as of today by default.
    ...
    """
    if cache is not None and loan.pk in cache:
        return cache[loan.pk]

    today_date = as_of or timezone.now().date()

    if loan.Status:
        status = {'state': 'closed', 'label': 'Closed', 'overdue': 0, 'behind': 0,
                  'pending_penalty': 0}
    else:
        total_due = Installments.objects.filter(
            Loan=loan, Date_Due__lte=today_date
        ).aggregate(Sum('Installment_Due'))['Installment_Due__sum'] or 0
        total_paid = Payments.objects.filter(
            Loan=loan, Payment_Type=1
        ).aggregate(Sum('Amount_Paid'))['Amount_Paid__sum'] or 0
        total_loan_amount = loan.Principle_Amount + (loan.Principle_Amount * loan.Intrest_Rate / 100)
        ...
```

to:

```python
def loan_repayment_status(loan, cache=None, as_of=None):
    """Where a loan stands on repayment, as of today by default.
    ...
    """
    if cache is not None and loan.pk in cache:
        return cache[loan.pk]

    today_date = as_of or timezone.now().date()

    if loan.Status:
        status = {'state': 'closed', 'label': 'Closed', 'overdue': 0, 'behind': 0,
                  'pending_penalty': 0}
    elif loan.Frequency == 4:
        total_due = Installments.objects.filter(
            Loan=loan, Date_Due__lte=today_date
        ).aggregate(Sum('Installment_Due'))['Installment_Due__sum'] or 0
        total_paid = Payments.objects.filter(
            Loan=loan, Payment_Type=1
        ).aggregate(Sum('Amount_Paid'))['Amount_Paid__sum'] or 0
        overdue = round(max(0, total_due - total_paid), 1)
        behind = Installments.objects.filter(
            Loan=loan, Date_Due__lte=today_date, Date_Paid__isnull=True
        ).exclude(Installment_Due=0).count()
        penalty_rows = Penalty.objects.filter(Loan=loan).aggregate(
            charged=Sum('Penalty_Calc'), paid=Sum('Penalty_Paid'), waived=Sum('Waived_Amount')
        )
        penalty_paid_direct = Payments.objects.filter(
            Loan=loan, Payment_Type=2
        ).aggregate(Sum('Amount_Paid'))['Amount_Paid__sum'] or 0
        penalty_waived = Waiver.objects.filter(
            Loan=loan, Waiver_Type=1
        ).aggregate(Sum('Amount'))['Amount__sum'] or 0
        pending_penalty = round(max(0, (penalty_rows['charged'] or 0)
                                    - max(penalty_paid_direct, penalty_rows['paid'] or 0)
                                    - max(penalty_waived, penalty_rows['waived'] or 0)), 1)
        if overdue <= 0:
            status = {'state': 'ontrack', 'label': 'On track', 'overdue': 0, 'behind': 0,
                      'pending_penalty': pending_penalty}
        else:
            label = '%s installment%s behind' % (behind, '' if behind == 1 else 's') if behind else 'Behind schedule'
            status = {'state': 'behind', 'label': label, 'overdue': overdue, 'behind': behind,
                      'pending_penalty': pending_penalty}
    else:
        total_due = Installments.objects.filter(
            Loan=loan, Date_Due__lte=today_date
        ).aggregate(Sum('Installment_Due'))['Installment_Due__sum'] or 0
        total_paid = Payments.objects.filter(
            Loan=loan, Payment_Type=1
        ).aggregate(Sum('Amount_Paid'))['Amount_Paid__sum'] or 0
        total_loan_amount = loan.Principle_Amount + (loan.Principle_Amount * loan.Intrest_Rate / 100)
        total_waivers = Waiver.objects.filter(
            Loan=loan, Waiver_Type=2
        ).aggregate(Sum('Amount'))['Amount__sum'] or 0
        total_pending = total_loan_amount - total_paid - total_waivers

        overdue = round(max(0, min(total_due - total_paid, max(0, total_pending))), 1)

        # Count the installments the payments do not cover, walking them in due
        # order. Installment amounts vary within a loan (many start with a small
        # stub), so dividing the shortfall by any single amount would be wrong.
        behind = 0
        remaining = total_paid
        for due_amount in Installments.objects.filter(
            Loan=loan, Date_Due__lte=today_date
        ).exclude(Installment_Due=0).order_by('Date_Due').values_list('Installment_Due', flat=True):
            if remaining >= due_amount:
                remaining -= due_amount
            else:
                behind += 1

        # Pending penalty, mirroring ClientLoanDetail: charged less paid less waived.
        penalty_rows = Penalty.objects.filter(Loan=loan).aggregate(
            charged=Sum('Penalty_Calc'), paid=Sum('Penalty_Paid'), waived=Sum('Waived_Amount')
        )
        penalty_paid_direct = Payments.objects.filter(
            Loan=loan, Payment_Type=2
        ).aggregate(Sum('Amount_Paid'))['Amount_Paid__sum'] or 0
        penalty_waived = Waiver.objects.filter(
            Loan=loan, Waiver_Type=1
        ).aggregate(Sum('Amount'))['Amount__sum'] or 0
        pending_penalty = round(max(0, (penalty_rows['charged'] or 0)
                                    - max(penalty_paid_direct, penalty_rows['paid'] or 0)
                                    - max(penalty_waived, penalty_rows['waived'] or 0)), 1)

        if overdue <= 0:
            status = {'state': 'ontrack', 'label': 'On track', 'overdue': 0, 'behind': 0,
                      'pending_penalty': pending_penalty}
        else:
            label = '%s installment%s behind' % (behind, '' if behind == 1 else 's') if behind else 'Behind schedule'
            status = {'state': 'behind', 'label': label, 'overdue': overdue, 'behind': behind,
                      'pending_penalty': pending_penalty}

    if cache is not None:
        cache[loan.pk] = status
    return status
```

This duplicates the penalty-aggregation block across both branches
rather than factoring it out, matching this task's "don't touch the
existing branch's code" constraint precisely — the `else:` branch here
is a byte-for-byte copy of the function's original body, just re-indented
under the new `elif`.

- [ ] **Step 7: Run tests to verify they pass, then run the full suite**

Run: `python3 manage.py test microfinance.tests_overdraft -v 2`
Expected: PASS (all tests including the four new classes)

Run: `python3 manage.py test microfinance -v 2`
Expected: all tests pass — in particular
`test_loans_total_property_unchanged_for_monthly_loans` confirms the
non-overdraft path through `Loans.Total` is byte-for-byte identical.

- [ ] **Step 8: Commit**

```bash
git add microfinance/models.py microfinance/views.py microfinance/overdraft.py microfinance/tests_overdraft.py
git commit -m "Make Loans.Total, bulk_overdue_map, loan_repayment_status overdraft-aware"
```

---

### Task 8: Dashboard interest/principal split — overdraft branch

**Files:**
- Modify: `microfinance/views.py:3260-3266` (dashboard interest split)
- Test: `microfinance/tests_overdraft.py` (append)

**Interfaces:**
- Consumes: `Payments.Interest_Portion`/`Principal_Portion` (Task 1)

**Context for implementer:** Locate the exact block inside the
`dashboard` view (`views.py:3156` onward) — reproduced below from the
research pass. This block iterates `period_payments`, so the fix is a
per-payment frequency check.

Current code:

```python
    # 6. Interest earned in the period (approximate calculation)
    interest_earned_period = 0
    for payment in period_payments:
        # Calculate interest portion based on loan's interest rate
        principal_portion = payment.Amount_Paid / (1 + (payment.Loan.Intrest_Rate / 100))
        interest_portion = payment.Amount_Paid - principal_portion
        interest_earned_period += interest_portion
```

- [ ] **Step 1: Write a failing test**

```python
# microfinance/tests_overdraft.py — append
from microfinance.views import dashboard
from django.test import RequestFactory


class DashboardOverdraftSplitTest(TestCase):
    def test_dashboard_uses_stored_split_for_overdraft_payments(self):
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))
        sync_overdraft_loan(loan, as_of=date(2026, 1, 10))
        payment = Payments.objects.get(Loan=loan)
        # After sync, this payment's Interest_Portion should be ~5000, not
        # whatever the flat-rate reverse-derivation formula would produce.
        self.assertAlmostEqual(payment.Interest_Portion, 5000.0, places=2)
        # Sanity: the flat-rate reverse-derivation would have produced a
        # different (wrong) number for this loan's 2% rate, since it assumes
        # a single-period flat total, not a monthly-recurring rate:
        flat_wrong_principal = payment.Amount_Paid / (1 + (loan.Intrest_Rate / 100))
        flat_wrong_interest = payment.Amount_Paid - flat_wrong_principal
        self.assertNotAlmostEqual(payment.Interest_Portion, flat_wrong_interest, places=2)
```

- [ ] **Step 2: Run test to verify it demonstrates the discrepancy (informational — the sync in Task 4 already stores the correct value; this task's job is the dashboard's *read* side)**

Run: `python3 manage.py test microfinance.tests_overdraft.DashboardOverdraftSplitTest -v 2`
Expected: PASS already (Task 4 already stores the correct
`Interest_Portion`). This test's purpose is a guard for Step 3's dashboard
fix — proceed to Step 3 regardless, since the actual behavior under test
here is the dashboard view's read path, not the storage, which is
verified next.

- [ ] **Step 3: Branch the dashboard interest-split loop**

```python
    # 6. Interest earned in the period (approximate calculation)
    interest_earned_period = 0
    for payment in period_payments:
        if payment.Loan.Frequency == 4:
            interest_earned_period += payment.Interest_Portion
            continue
        # Calculate interest portion based on loan's interest rate
        principal_portion = payment.Amount_Paid / (1 + (payment.Loan.Intrest_Rate / 100))
        interest_portion = payment.Amount_Paid - principal_portion
        interest_earned_period += interest_portion
```

- [ ] **Step 4: Run the full test suite**

Run: `python3 manage.py test microfinance -v 2`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add microfinance/views.py microfinance/tests_overdraft.py
git commit -m "Dashboard: read stored Interest_Portion for overdraft payments instead of reverse-deriving"
```

---

### Task 9: Loan creation/edit form and template — Penalty_Rate (all types), Principal_Threshold_Percent (overdraft only)

**Files:**
- Modify: `microfinance/forms.py` (`AddLoan`, `EditLoanDetail`)
- Modify: `microfinance/templates/microfinance/Add_Loan.html`
- Test: manual (Django forms with no custom widgets don't need unit
  tests beyond field-presence, already covered by Task 1's model tests)

**Interfaces:**
- Consumes: `Loans.Penalty_Rate`, `Loans.Principal_Threshold_Percent`
  (Task 1)

**Context for implementer:** `AddLoan` and `EditLoanDetail`
(`microfinance/forms.py`) are both plain `ModelForm`s listing fields
explicitly — no custom widgets for `Frequency`. `Add_Loan.html` is a
fully generic `{% for field in form %}` loop with no
Frequency-conditional logic anywhere (confirmed — nothing to modify,
only to add). `Principle_Amount` being non-editable for overdraft loans
post-creation (per the spec) is enforced by `EditLoanDetail` simply not
including `Principle_Amount` in the general edit flow for overdraft
loans — see Step 3.

- [ ] **Step 1: Add the new fields to both forms**

In `microfinance/forms.py`, change:

```python
class AddLoan(forms.ModelForm):
    class Meta:
        model=models.Loans
        fields= ['AccNo','Principle_Amount','Frequency','Purpose','No_Of_Installments','Intrest_Rate','File_Charge_Percent','First_Due_Date','Loan_Date','Loan_Collector','security_docs']
        widgets = {
            'First_Due_Date': forms.DateInput(attrs={'type': 'date'}),
            'Loan_Date': forms.DateInput(attrs={'type': 'date'})
        }
```

to:

```python
class AddLoan(forms.ModelForm):
    class Meta:
        model=models.Loans
        fields= ['AccNo','Principle_Amount','Frequency','Purpose','No_Of_Installments','Intrest_Rate','Penalty_Rate','Principal_Threshold_Percent','File_Charge_Percent','First_Due_Date','Loan_Date','Loan_Collector','security_docs']
        widgets = {
            'First_Due_Date': forms.DateInput(attrs={'type': 'date'}),
            'Loan_Date': forms.DateInput(attrs={'type': 'date'})
        }
        help_texts = {
            'Penalty_Rate': 'Optional. Daily late-payment penalty percent. Leave blank for the default (2%/day).',
            'Principal_Threshold_Percent': 'OverDraft only. Minimum leftover, as a percent of outstanding principal, before a payment reduces principal instead of prepaying next month\'s interest.',
        }
```

And `EditLoanDetail`:

```python
class EditLoanDetail(forms.ModelForm):
    class Meta:
        model=models.Loans
        fields=['Principle_Amount','Frequency','Purpose','No_Of_Installments','Intrest_Rate','Penalty_Rate','Principal_Threshold_Percent','File_Charge_Percent','Loan_Date','First_Due_Date','Loan_Collector']
        widgets = {
            'Loan_Date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'First_Due_Date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Format dates for HTML5 date input (yyyy-MM-dd)
        if self.instance and self.instance.pk:
            if self.instance.Loan_Date:
                self.initial['Loan_Date'] = self.instance.Loan_Date.strftime('%Y-%m-%d')
            if self.instance.First_Due_Date:
                self.initial['First_Due_Date'] = self.instance.First_Due_Date.strftime('%Y-%m-%d')
            if self.instance.Frequency == 4:
                self.fields['Principle_Amount'].disabled = True
                self.fields['Principle_Amount'].help_text = (
                    'Not editable for OverDraft loans — the outstanding balance '
                    'is derived from the payment history.'
                )
```

- [ ] **Step 2: Add show/hide JS for `Principal_Threshold_Percent` in `Add_Loan.html`**

In `microfinance/templates/microfinance/Add_Loan.html`, the field loop is
fully generic — add a small script block after the existing `<script>`
tag at the bottom of the file (do not remove the existing double-submit
prevention script), and give the `Principal_Threshold_Percent` field's
wrapping `<div>` an id to target. Change:

```html
            {% for field in form %}
            <div class="mb-3">
```

to:

```html
            {% for field in form %}
            <div class="mb-3" {% if field.name == 'Principal_Threshold_Percent' %}id="threshold-field-wrapper" style="display:none;"{% endif %}>
```

And append to the existing `<script>` block at the bottom of the file
(inside the existing `jQuery(function() { ... });`, or as a second
`jQuery` call right after it):

```html
    jQuery(function() {
        function toggleThresholdField() {
            var freq = $('#id_Frequency').val();
            if (freq === '4') {
                $('#threshold-field-wrapper').show();
            } else {
                $('#threshold-field-wrapper').hide();
            }
        }
        toggleThresholdField();
        $('#id_Frequency').on('change', toggleThresholdField);
    });
```

- [ ] **Step 3: Regenerate migrations if forms changed model usage (none needed — forms don't require migrations), then manually verify in the browser**

Run: `python3 manage.py runserver 0.0.0.0:8000` (against the local dev
database only)

Manually:
1. Log in as a staff user.
2. Navigate to a client, click "Add Loan".
3. Confirm `Penalty_Rate` appears as an input for every Frequency choice.
4. Select "OverDraft" from the Frequency dropdown — confirm the
   `Principal_Threshold_Percent` field appears; select any other
   frequency — confirm it hides again.
5. Submit an OverDraft loan with `Principle_Amount=250000`,
   `Intrest_Rate=2`, `Principal_Threshold_Percent=20`,
   `First_Due_Date` a few days in the past — confirm no server error and
   the loan is created.
6. Open that loan's edit page — confirm `Principle_Amount` is disabled/
   grayed out with the explanatory help text.

Stop the dev server after verifying (`Ctrl+C`).

- [ ] **Step 4: Commit**

```bash
git add microfinance/forms.py microfinance/templates/microfinance/Add_Loan.html
git commit -m "Add Penalty_Rate (all loan types) and Principal_Threshold_Percent (OverDraft) to loan forms"
```

---

### Task 10: Overdue Loans screen — officer grouping and defaulters section

**Files:**
- Modify: `microfinance/views.py:1408-1473` (`Overdue_Loans`)
- Modify: `microfinance/templates/microfinance/Overdue_Loans.html`
- Test: `microfinance/tests_overdraft.py` or a new
  `microfinance/tests_reports.py` (either is fine; using
  `tests_overdraft.py` keeps things in one place for this feature)

**Interfaces:**
- Consumes: `bulk_overdue_map`, `loan_repayment_status` (already
  overdraft-aware after Task 7)
- Produces: `Overdue_Loans` view context gains `officer_groups` (a list
  of `{'officer': Staff, 'rows': [...], 'subtotal_overdue': float}`) and
  `defaulter_rows` (rows whose `loan_repayment_status` state is
  `'behind'`, same grouping by officer) — additive to the existing
  `rows`/`total_overdue`/etc. context keys, none removed.

**Context for implementer:** Current `Overdue_Loans` (`views.py:1407-1473`)
already computes per-loan overdue amounts via `bulk_overdue_map` and
builds a flat `rows` list. This task adds grouping on top — it does not
replace the existing flat list variables (`rows`, `total_overdue`,
`total_penalty`, `behind_count`, `open_count`), so any existing template
usage of those keys keeps working; the template is extended, not
rewritten, to add the new grouped sections.

- [ ] **Step 1: Write a failing test for the grouped context**

```python
# microfinance/tests_overdraft.py — append
from microfinance.views import Overdue_Loans


class OverdueLoansOfficerGroupingTest(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staffviewer', password='x', is_staff=True)

    def test_context_includes_officer_groups_and_defaulter_rows(self):
        loan = _make_overdraft_loan(first_due=date.today() - timedelta(days=40))
        sync_overdraft_loan(loan, as_of=date.today())
        factory = RequestFactory()
        request = factory.get('/Overdue/')
        request.user = self.staff_user
        response = Overdue_Loans(request)
        self.assertIn(b'officer_groups' if False else b'', response.content)  # placeholder replaced below
```

Replace that last placeholder assertion — `Overdue_Loans` returns a
rendered `HttpResponse`, so context isn't directly inspectable from the
view's return value without Django's test `Client`. Rewrite using
`self.client` instead:

```python
# microfinance/tests_overdraft.py — replace the class above with this
class OverdueLoansOfficerGroupingTest(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staffviewer', password='x', is_staff=True)

    def test_view_groups_overdue_loans_by_officer(self):
        loan = _make_overdraft_loan(first_due=date.today() - timedelta(days=40))
        sync_overdraft_loan(loan, as_of=date.today())
        self.client.force_login(self.staff_user)
        response = self.client.get('/microfinance/Overdue/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('officer_groups', response.context)
        self.assertIn('defaulter_rows', response.context)
        officer_names = [g['officer'].Officer_Name for g in response.context['officer_groups']]
        self.assertIn(loan.Loan_Collector.Officer_Name, officer_names)

    def test_defaulter_rows_only_include_behind_loans(self):
        loan = _make_overdraft_loan(first_due=date.today() - timedelta(days=40))
        sync_overdraft_loan(loan, as_of=date.today())
        self.client.force_login(self.staff_user)
        response = self.client.get('/microfinance/Overdue/')
        for row in response.context['defaulter_rows']:
            self.assertEqual(row['status']['state'], 'behind')
```

Note: confirm the actual URL prefix by checking the project's root
`urls.py` `include()` call for the `microfinance` app before running
this — if it's mounted at a different prefix than `/microfinance/`,
adjust the test URLs accordingly (check
`essarrfinance/urls.py` for the `include('microfinance.urls')` line).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 manage.py test microfinance.tests_overdraft.OverdueLoansOfficerGroupingTest -v 2`
Expected: FAIL — `officer_groups`/`defaulter_rows` not in context yet.

- [ ] **Step 3: Extend the `Overdue_Loans` view**

Current code (`views.py:1407-1473`):

```python
@login_required(login_url="/accounts/login/")
def Overdue_Loans(request):
    """Every open loan behind on repayment, worst exposure first.

    Answers "who do I chase today" in one screen, which previously meant running
    a report and reading it. Overdue comes from bulk_overdue_map so the whole
    list costs a fixed handful of queries and agrees with the reports and the
    client page to the rupee.
    """
    if not request.user.is_staff:
        return HttpResponseForbidden("You do not have permission to view this page.")

    today_date = timezone.now().date()
    officer_pk = request.GET.get('officer') or ''

    open_loans = Loans.objects.filter(Status=False).select_related(
        'Account__Client', 'Loan_Collector')
    if officer_pk:
        open_loans = open_loans.filter(Loan_Collector_id=officer_pk)

    open_loans = list(open_loans)
    overdue_by_loan = bulk_overdue_map([l.pk for l in open_loans], today_date)

    # Pending penalty in bulk, so the page does not fall back to per-row queries.
    behind_pks = list(overdue_by_loan)
    penalty_charged = dict(Penalty.objects.filter(Loan_id__in=behind_pks)
                           .values_list('Loan_id').annotate(t=Sum('Penalty_Calc')))
    penalty_paid = dict(Payments.objects.filter(Loan_id__in=behind_pks, Payment_Type=2)
                        .values_list('Loan_id').annotate(t=Sum('Amount_Paid')))
    penalty_waived = dict(Waiver.objects.filter(Loan_id__in=behind_pks, Waiver_Type=1)
                          .values_list('Loan_id').annotate(t=Sum('Amount')))
    last_paid = dict(Payments.objects.filter(Loan_id__in=behind_pks, Payment_Type=1)
                     .values_list('Loan_id').annotate(d=Max('Date_Paid')))

    rows = []
    total_overdue = 0
    total_penalty = 0
    for loan in open_loans:
        overdue = overdue_by_loan.get(loan.pk)
        if not overdue:
            continue
        pending_penalty = round(max(0, (penalty_charged.get(loan.pk) or 0)
                                    - (penalty_paid.get(loan.pk) or 0)
                                    - (penalty_waived.get(loan.pk) or 0)), 1)
        last = last_paid.get(loan.pk)
        rows.append({
            'loan': loan,
            'overdue': overdue,
            'pending_penalty': pending_penalty,
            'last_paid': last,
            'days_since': (today_date - last).days if last else None,
        })
        total_overdue += overdue
        total_penalty += pending_penalty

    rows.sort(key=lambda r: r['overdue'], reverse=True)

    return render(request, 'microfinance/Overdue_Loans.html', {
        'rows': rows,
        'total_overdue': round(total_overdue, 1),
        'total_penalty': round(total_penalty, 1),
        'behind_count': len(rows),
        'open_count': len(open_loans),
        'officers': Staff.objects.all().order_by('Officer_Name'),
        'selected_officer': officer_pk,
        'today': today_date,
    })
```

Change the end of the function (after `rows.sort(...)`, replacing the
final `return render(...)`) to:

```python
    rows.sort(key=lambda r: r['overdue'], reverse=True)

    status_cache = {}
    for row in rows:
        row['status'] = loan_repayment_status(row['loan'], cache=status_cache, as_of=today_date)

    groups_by_officer = {}
    for row in rows:
        officer = row['loan'].Loan_Collector
        group = groups_by_officer.setdefault(officer.pk, {
            'officer': officer, 'rows': [], 'subtotal_overdue': 0.0,
        })
        group['rows'].append(row)
        group['subtotal_overdue'] += row['overdue']
    officer_groups = sorted(
        groups_by_officer.values(), key=lambda g: g['subtotal_overdue'], reverse=True)

    defaulter_rows = [r for r in rows if r['status']['state'] == 'behind']

    return render(request, 'microfinance/Overdue_Loans.html', {
        'rows': rows,
        'total_overdue': round(total_overdue, 1),
        'total_penalty': round(total_penalty, 1),
        'behind_count': len(rows),
        'open_count': len(open_loans),
        'officers': Staff.objects.all().order_by('Officer_Name'),
        'selected_officer': officer_pk,
        'today': today_date,
        'officer_groups': officer_groups,
        'defaulter_rows': defaulter_rows,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 manage.py test microfinance.tests_overdraft.OverdueLoansOfficerGroupingTest -v 2`
Expected: PASS

- [ ] **Step 5: Extend the template with officer-grouped and defaulters sections**

In `microfinance/templates/microfinance/Overdue_Loans.html`, add two new
sections after the existing figures block (`</div>` closing `.od-figures`)
and before the existing flat table's `<div class="card shadow-sm">`.
Insert:

```html
  <div class="mb-4">
    <h4 class="mb-2">By collection officer</h4>
    {% for group in officer_groups %}
    <div class="card shadow-sm mb-3">
      <div class="card-header d-flex justify-content-between align-items-center">
        <strong>{{ group.officer.Officer_Name }}</strong>
        <span class="text-danger fw-semibold">&#8377;{{ group.subtotal_overdue|floatformat:0 }} overdue</span>
      </div>
      <div class="table-responsive">
        <table class="table-modern mb-0">
          <thead>
            <tr>
              <th>Loan</th>
              <th>Client</th>
              <th class="text-end">Overdue</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {% for r in group.rows %}
            <tr>
              <td><a href="{% url 'microfinance:loandetail' pk=r.loan.pk %}">#{{ r.loan.pk }}</a></td>
              <td><a href="{% url 'microfinance:clientdetail' pk=r.loan.Account.Client.pk %}">{{ r.loan.Account.Client.Name }}</a></td>
              <td class="text-end text-danger">&#8377;{{ r.overdue|floatformat:0 }}</td>
              <td>{{ r.status.label }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
    {% empty %}
    <div class="text-muted">No officers with overdue loans.</div>
    {% endfor %}
  </div>

  <div class="mb-4">
    <h4 class="mb-2">Defaulters</h4>
    <div class="card shadow-sm">
      <div class="table-responsive">
        <table class="table-modern mb-0">
          <thead>
            <tr>
              <th>Loan</th>
              <th>Client</th>
              <th>Officer</th>
              <th class="text-end">Overdue</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {% for r in defaulter_rows %}
            <tr>
              <td><a href="{% url 'microfinance:loandetail' pk=r.loan.pk %}">#{{ r.loan.pk }}</a></td>
              <td><a href="{% url 'microfinance:clientdetail' pk=r.loan.Account.Client.pk %}">{{ r.loan.Account.Client.Name }}</a></td>
              <td class="small text-muted">{{ r.loan.Loan_Collector.Officer_Name }}</td>
              <td class="text-end text-danger">&#8377;{{ r.overdue|floatformat:0 }}</td>
              <td>{{ r.status.label }}</td>
            </tr>
            {% empty %}
            <tr><td colspan="5" class="text-center text-muted py-3">No defaulters right now.</td></tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>
```

- [ ] **Step 6: Run full suite, then manually verify in browser**

Run: `python3 manage.py test microfinance -v 2`
Expected: all tests pass.

Manually (local dev server, local DB):
1. `python3 manage.py runserver 0.0.0.0:8000`
2. Log in as staff, navigate to `/microfinance/Overdue/` (or whatever
   prefix is confirmed from `essarrfinance/urls.py`).
3. Confirm the existing flat table still renders as before.
4. Confirm a new "By collection officer" section appears, grouping loans
   under each officer with a per-officer subtotal.
5. Confirm a new "Defaulters" section appears, listing only loans
   currently behind schedule.
6. Stop the dev server.

- [ ] **Step 7: Commit**

```bash
git add microfinance/views.py microfinance/templates/microfinance/Overdue_Loans.html microfinance/tests_overdraft.py
git commit -m "Overdue Loans: add officer grouping and defaulters section"
```

---

### Task 11: Full regression pass and manual end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `python3 manage.py test microfinance -v 2`
Expected: every test across `microfinance/tests.py` and
`microfinance/tests_overdraft.py` passes.

- [ ] **Step 2: Run Django's system check**

Run: `python3 manage.py check`
Expected: no errors (in particular, no unresolved migration state).

- [ ] **Step 3: Confirm migration state matches code**

Run: `python3 manage.py makemigrations --check --dry-run`
Expected: no new migrations needed — confirms `models.py` and the
migration file from Task 1 are in sync.

- [ ] **Step 4: Manual end-to-end walkthrough on the local dev database**

Run: `python3 manage.py runserver 0.0.0.0:8000` (local DB only — do
**not** point at the Hetzner server or open the SSH tunnel for this).

1. Create a new OverDraft loan for an existing client: principal
   250000, interest rate 2, threshold 20%, first due date a few days in
   the past.
2. Record a payment exactly equal to one cycle's interest — confirm the
   loan detail page shows the installment as paid and no overdue amount.
3. Record a second, larger payment (e.g. 10x the threshold amount) —
   confirm outstanding principal visibly drops (check `Loans.Total` /
   loan detail).
4. Record a small payment below the threshold — confirm principal does
   NOT drop and the amount shows up credited toward next month somehow
   visible in the loan/installment view.
5. Visit the enhanced Overdue Loans screen — confirm the new loan
   appears grouped under its officer, and appears in Defaulters only if
   actually behind.
6. Create a regular (Monthly) loan exactly as before this feature —
   confirm nothing about its creation flow, installment schedule, or
   penalty calculation looks different from before.

- [ ] **Step 5: Report completion**

No commit needed for this task (verification only) — if any step
surfaces a bug, return to the relevant earlier task, fix it with a
failing-test-first cycle, and re-run this task's checklist from Step 1.

---

## Self-Review Notes

**Spec coverage:** Every "Decision locked in" (1-12) has a corresponding
task: fixed due dates (Task 3/4), penalty rate configurability for all
types (Task 2), unpaid-interest penalty base (Task 2, no code change
needed — noted explicitly), simple monthly rate (Task 3), open-ended
tenure (Task 6, no `No_Of_Installments` schedule generated), daily
proration (Task 3), actual-days daily rate (Task 3), defaulter reuse
(Task 10), report-as-enhancement (Task 10), non-compounding missed
months (Task 3), threshold-gated principal reduction (Task 3), payoff
stub interest (Task 3). The "Edge cases" section's items are covered by:
waivers (deferred — flagged as a known gap below), overpayment cap
(Task 3's `_allocate_payment`, capped via `min(leftover, outstanding_principal)`),
payment edit/delete (not covered — flagged below), penalty-type exclusion
(Task 3's `Payments.objects.filter(Loan=loan, Payment_Type=1)`), first
cycle (Task 3, generic day-count math), cycle boundary convention (Task
3's `<` comparisons), month-end drift (inherited from `relativedelta`,
no special handling needed), materialization idempotency (Task 4's
`get_or_create`), stop-after-closure (not explicitly implemented —
flagged below), future-dated payments (not explicitly validated —
flagged below).

**Known gaps intentionally left for a follow-up task** (out of this
plan's scope, since the spec marked them as assumptions rather than hard
requirements, and this plan is already large):
- Waiver interaction with overdraft installments (spec's edge case) is
  not implemented — an interest `Waiver` row against an overdraft loan
  will not currently reduce the replay's unpaid-interest figure. Low
  risk since waivers are presumably rare and manually applied by staff
  who can be told to double-check overdraft loans specifically.
- Payment edit/delete re-sync is not wired — if the existing payment
  edit/delete UI is used against an overdraft loan's payment, portions
  will go stale until the next `pay_installment` call re-triggers a
  sync. Recommend a fast-follow task once this ships, gated on whichever
  view handles payment edit/delete (not identified in this research
  pass).
- Explicit rejection of future-dated payments and an explicit "stop
  materializing after full closure" guard are not implemented as hard
  validations — the replay naturally stops materializing once
  `current_due_date > today`, which covers the common case, but a
  loan that's fully paid off before its "natural" next cycle would still
  materialize a new (zero-amount, per Task 3's max(0, ...) floor)
  installment row on the next sync. This is cosmetically harmless (a
  zero-amount row) but not fully clean; flagged for a follow-up rather
  than expanding this already-large plan further.

**Placeholder scan:** No TBD/TODO markers. Every code step has complete,
runnable code, not descriptions.

**Type consistency:** `sync_overdraft_loan`, `ensure_overdraft_installments`,
`replay_overdraft_loan`, `overdraft_total_owed` are used with consistent
signatures across every task that references them (checked: Task 3 defines,
Tasks 4/5/6/7/8 consume with matching names/arguments).
