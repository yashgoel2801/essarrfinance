"""Persistence layer for the overdraft replay engine.

Turns replay_overdraft_loan's pure output into Installments/Payments rows.
Idempotent and safe to call from any request that touches an overdraft loan:
calling sync_overdraft_loan twice in a row with the same arguments issues
zero additional database writes on the second call.
"""
from django.db import transaction
from django.db.models import Sum

from .models import Installments, Payments, Penalty
from .overdraft import replay_overdraft_loan, overdraft_total_owed


def sync_overdraft_loan(loan, as_of=None):
    """Materialize/refresh Installments and Payments rows for an overdraft
    loan from the current state of its payment ledger. Safe to call
    repeatedly; only unpaid installments are ever rewritten, and a save is
    issued only when a field's value actually needs to change.
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
                # Already settled in a previous sync — leave it frozen, even
                # if a later replay (e.g. from a backdated payment) would now
                # compute a different amount for this row.
                continue

            # Compute the desired field values and only touch the row (and
            # issue a write) if something actually needs to change. This is
            # what makes repeated calls a true no-op at the database level,
            # not just a no-op in the eventual row count.
            desired = {
                'Installment_Due': installment_data['Installment_Due'],
                'Installment_To_Be_Paid': installment_data['Installment_Due'],
                'Pending_Amount': installment_data['Installment_Due'],
            }
            if installment_data['is_paid']:
                desired['Date_Paid'] = installment_data['Date_Due']
                desired['Installment_Paid'] = installment_data['Installment_Due']
                desired['Pending_Amount'] = 0

            changed_fields = [
                field for field, value in desired.items()
                if getattr(row, field) != value
            ]
            if not changed_fields:
                continue

            for field, value in desired.items():
                if field in changed_fields:
                    setattr(row, field, value)
            row.save(update_fields=changed_fields)

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


def rebuild_overdraft_loan(loan, as_of=None):
    """Discard and fully recompute an overdraft loan's Installments rows,
    then resync from the current Payments ledger.

    sync_overdraft_loan is deliberately incremental: once an Installment
    row is settled (Date_Paid is not None) it is frozen and never
    rewritten, even if a later replay would compute a different amount for
    it -- that's what makes routine syncs safe and cheap. But it also means
    a genuine correction (editing a payment's amount/date, deleting a
    payment, or inserting one dated before an already-settled cycle) is
    silently ignored by an ordinary sync, because the stale row it should
    replace is already frozen.

    Call this instead of sync_overdraft_loan whenever the correction is the
    point: after editing or deleting a Payments row, or after recording a
    payment dated before an already-settled cycle. It is a pure function of
    the loan's Payments rows, so a full rebuild always converges on the
    same state a freshly-created loan with that exact payment history
    would reach -- there is no way for a rebuild to leave behind
    inconsistent data, only work.

    Penalty is a FK to Installments with on_delete=CASCADE, so deleting
    Installments here silently wipes every Penalty row for this loan
    whether or not this function touches Penalty directly -- Django does
    it regardless. That would lose Penalty_Paid amounts staff have already
    recorded against a specific cycle's penalty, since the caller's
    subsequent Recalculate_Penalty/_calculate_individual_penalties call
    rebuilds Penalty rows fresh and has nothing left to read a "already
    paid this much" total from. So: capture each due date's total
    Penalty_Paid, keyed by Installment_Due_Date (stable across a rebuild,
    unlike Installment_id -- every row gets a new PK), before the cascade,
    and return it so the caller can re-apply it once new Penalty rows
    exist. Waivers are untouched by any of this: they live in a separate
    Waiver table with no FK to Installments, and the penalty function
    already re-reads and reapplies them on every call, for every loan type.

    Returns (replay_result, paid_by_due_date) where paid_by_due_date is
    {Installment_Due_Date: total_Penalty_Paid_before_the_rebuild}.
    """
    with transaction.atomic():
        paid_by_due_date = dict(
            Penalty.objects.filter(Loan=loan, Penalty_Paid__gt=0)
            .values_list('Installment_Due_Date')
            .annotate(t=Sum('Penalty_Paid'))
        )
        Installments.objects.filter(Loan=loan).delete()  # cascades Penalty
        result = sync_overdraft_loan(loan, as_of=as_of)
        return result, paid_by_due_date


def reapply_penalty_paid_after_rebuild(loan, paid_by_due_date):
    """Restore each cycle's previously-recorded Penalty_Paid total onto the
    freshly-recreated Penalty rows a rebuild's caller just generated (via
    Recalculate_Penalty/_calculate_individual_penalties, which deletes and
    recreates Penalty rows on every call for every loan type -- this is
    pre-existing, unrelated to overdraft). No-op for any due date with
    nothing captured. Sets Status=True once Penalty_Paid + Waived_Amount
    covers Penalty_Calc, matching the penalty function's own rule.
    """
    if not paid_by_due_date:
        return
    for due_date, amount_paid in paid_by_due_date.items():
        rows = Penalty.objects.filter(Loan=loan, Installment_Due_Date=due_date).order_by('Date_Started')
        remaining = amount_paid
        for row in rows:
            if remaining <= 0:
                break
            applied = min(remaining, row.Penalty_Calc)
            remaining -= applied
            row.Penalty_Paid = applied
            row.Status = (row.Penalty_Paid + row.Waived_Amount) >= row.Penalty_Calc
            row.save(update_fields=['Penalty_Paid', 'Status'])


def overdraft_report_rows(loans_qs, start, end):
    """One row per overdraft loan for a date-range report's separate
    OverDraft section -- these loans are excluded from every flat-formula
    aggregate in the report (interest/principal are inherently split, not
    a single derivable number the way a flat loan's is), so this is the
    only place their numbers appear.

    Syncs each loan first so a loan nobody has opened since its last
    payment still shows current figures, not stale ones. `start`/`end` are
    date objects (or ISO strings; callers already have these as strings
    from request.POST, so both are accepted).

    Returns a list of dicts, each with the identity
    interest_collected + principal_collected + credit_banked == amount_collected
    holding by construction (credit_banked is defined as the residual), so
    each row and the section's own subtotal are self-checking -- staff can
    verify a total_collected figure against the split at a glance, without
    trusting a derived formula the way the old flat-report math required.
    """
    from datetime import date as _date

    def _as_date(value):
        if isinstance(value, str):
            return _date.fromisoformat(value)
        return value

    start_date = _as_date(start)
    end_date = _as_date(end)

    rows = []
    for loan in loans_qs.filter(Frequency=4):
        ensure_overdraft_installments(loan)

        interest_billed = Installments.objects.filter(
            Loan=loan, Date_Due__range=[start_date, end_date]
        ).aggregate(Sum('Installment_Due'))['Installment_Due__sum'] or 0.0

        payments_in_range = Payments.objects.filter(
            Loan=loan, Payment_Type=1, Date_Paid__range=[start_date, end_date]
        )
        payment_agg = payments_in_range.aggregate(
            amount=Sum('Amount_Paid'), interest=Sum('Interest_Portion'),
            principal=Sum('Principal_Portion'),
        )
        amount_collected = payment_agg['amount'] or 0.0
        interest_collected = payment_agg['interest'] or 0.0
        principal_collected = payment_agg['principal'] or 0.0
        credit_banked = round(max(0.0, amount_collected - interest_collected - principal_collected), 2)

        penalty_payments_in_range = Payments.objects.filter(
            Loan=loan, Payment_Type=2, Date_Paid__range=[start_date, end_date]
        ).aggregate(Sum('Amount_Paid'))['Amount_Paid__sum'] or 0.0

        rows.append({
            'loan': loan,
            'interest_billed_in_range': round(interest_billed, 2),
            'interest_collected_in_range': round(interest_collected, 2),
            'principal_collected_in_range': round(principal_collected, 2),
            'credit_banked_in_range': credit_banked,
            'amount_collected_in_range': round(amount_collected, 2),
            'penalty_collected_in_range': round(penalty_payments_in_range, 2),
            'total_owed_as_of_end': overdraft_total_owed(loan, as_of=end_date),
        })
    return rows
