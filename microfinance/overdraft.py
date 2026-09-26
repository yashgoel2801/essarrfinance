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


def _merge_or_append_installment(installments, new_row):
    """Append new_row to installments, unless an existing row already shares
    its Date_Due -- in that case merge the two into one row (summed amount,
    combined paid state) instead of appending a second row that would later
    collide on (Loan, Date_Due) in sync_overdraft_loan's get_or_create.
    """
    for existing in installments:
        if existing['Date_Due'] == new_row['Date_Due']:
            existing['Installment_Due'] = round(
                existing['Installment_Due'] + new_row['Installment_Due'], 2
            )
            existing['_remaining'] = max(
                0.0, existing.get('_remaining', 0.0) + new_row.get('_remaining', 0.0)
            )
            existing['is_paid'] = existing['is_paid'] and new_row['is_paid']
            if existing['is_paid']:
                existing['_remaining'] = 0.0
            return existing
    installments.append(new_row)
    return new_row


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
        if cycle_days <= 0:
            raise ValueError(
                f"Overdraft loan {loan.pk}: non-positive cycle length "
                f"({cycle_days} days) between {previous_due_date} and "
                f"{current_due_date} -- First_Due_Date must be after Loan_Date."
            )

        # Collect payments that fall inside [previous_due_date, current_due_date)
        # and are allocated before this due date is reached, tracking segment
        # boundaries from any Principal_Portion allocation.
        segments = [(previous_due_date, outstanding_principal)]

        while payment_cursor < len(payments) and payments[payment_cursor].Date_Paid < current_due_date:
            payment = payments[payment_cursor]
            interest_portion, principal_portion, credit_balance, stub_row = _allocate_payment(
                payment, unpaid_installments, outstanding_principal,
                credit_balance, loan,
                previous_due_date, current_due_date,
            )
            payment_splits[payment.pk] = {
                'Interest_Portion': interest_portion,
                'Principal_Portion': principal_portion,
            }
            if stub_row is not None:
                _merge_or_append_installment(installments, stub_row)
                # The stub already billed interest for
                # [previous_due_date, payment.Date_Paid); don't let this
                # cycle's own materialization re-bill that span.
                segments = [(payment.Date_Paid, 0.0)]
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
    last_due_date = installments[-1]['Date_Due'] if installments else loan.Loan_Date
    while payment_cursor < len(payments) and payments[payment_cursor].Date_Paid <= today:
        payment = payments[payment_cursor]
        interest_portion, principal_portion, credit_balance, stub_row = _allocate_payment(
            payment, unpaid_installments, outstanding_principal,
            credit_balance, loan,
            last_due_date, current_due_date,
        )
        payment_splits[payment.pk] = {
            'Interest_Portion': interest_portion,
            'Principal_Portion': principal_portion,
        }
        if stub_row is not None:
            _merge_or_append_installment(installments, stub_row)
            last_due_date = payment.Date_Paid
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
                       credit_balance, loan, period_start, period_end):
    """Allocate one payment: interest-first (oldest unpaid), then -- only if
    the payer explicitly chose to (payment.Apply_To_Principal) -- the
    leftover reduces outstanding principal. Otherwise the entire leftover
    banks as advance-interest credit, no minimum. This is an explicit,
    per-payment choice, not an automatic threshold rule: a payment that
    would fully retire the loan still only does so when the flag is set --
    left unset, the excess just banks as credit and the loan stays open,
    however large the credit balance grows.

    If the flag is set and the leftover is enough to fully retire
    outstanding principal (after also billing a prorated stub for the
    not-yet-materialized partial period), that stub is billed and netted
    against any available credit before principal is applied. Returns
    (interest_portion, principal_portion, new_credit_balance, stub_row)
    where stub_row is a new installments-list dict (or None if no stub was
    billed).
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
        return round(interest_portion, 2), 0.0, credit_balance, None

    if payment.Apply_To_Principal:
        stub_row = None
        if outstanding_principal > 0:
            period_days = (period_end - period_start).days
            stub_days = (payment.Date_Paid - period_start).days
            stub_amount = 0.0
            if period_days > 0 and stub_days > 0:
                stub_amount = (
                    outstanding_principal * (loan.Intrest_Rate / 100.0 / period_days) * stub_days
                )

            if leftover >= outstanding_principal + stub_amount:
                applied_credit = min(credit_balance, stub_amount)
                credit_balance -= applied_credit
                net_stub = stub_amount - applied_credit
                interest_portion += net_stub
                leftover -= net_stub

                stub_row = {
                    'Date_Due': payment.Date_Paid,
                    'Installment_Due': round(stub_amount - applied_credit, 2),
                    'is_paid': True,
                    '_remaining': 0.0,
                }

                principal_portion = min(leftover, outstanding_principal)
                leftover -= principal_portion
                # Any true numeric residual (float rounding only, by
                # construction) is banked as credit rather than discarded.
                if leftover > 0:
                    credit_balance += leftover

                return (
                    round(interest_portion, 2),
                    round(principal_portion, 2),
                    round(credit_balance, 2),
                    stub_row,
                )

        principal_portion = min(leftover, outstanding_principal)
        leftover -= principal_portion
        if leftover > 0:
            credit_balance += leftover
        return round(interest_portion, 2), round(principal_portion, 2), credit_balance, None

    credit_balance += leftover
    return round(interest_portion, 2), 0.0, credit_balance, None


def overdraft_total_owed(loan, as_of=None):
    """Total amount an overdraft loan still owes: outstanding principal
    plus any unpaid materialized interest.

    Banked advance-interest credit is NOT subtracted here: it is a
    prepayment against a future cycle's interest, not a discount on what
    is owed today (the design spec: leftover below the threshold "will be
    considered as the next month interest adv payment"). Credit is already
    applied inside replay_overdraft_loan when each future cycle is
    materialized (installment_due = raw_interest - applied_credit) --
    subtracting it again here would double-count the same credit as both
    a reduction of today's total AND a reduction of a future cycle's bill.
    """
    result = replay_overdraft_loan(loan, as_of=as_of)
    unpaid_interest = sum(
        i['Installment_Due'] for i in result.installments if not i['is_paid']
    )
    total = result.outstanding_principal + unpaid_interest
    return round(max(0.0, total), 2)
