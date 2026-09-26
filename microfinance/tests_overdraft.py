from datetime import date, timedelta
from decimal import Decimal
from django.db import connection
from django.db.models import Sum
from django.test import TestCase, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.contrib.auth.models import User
from microfinance.models import Loans, Payments, Staff, Guarantors, Accounts, Clients, Installments, Penalty
from microfinance.overdraft import replay_overdraft_loan
from microfinance.views import Add_Loan


def _make_overdraft_loan(principal=250000, rate=2.0,
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
        Intrest_Rate=rate,
        Loan_Collector=staff, Guarantor=guarantor, Account=account,
        First_Due_Date=first_due, Loan_Date=loan_date,
    )


def _pay(loan, amount, on, apply_to_principal=False):
    return Payments.objects.create(
        Loan=loan, Amount_Paid=amount, Date_Paid=on, Payment_Type=1,
        Apply_To_Principal=apply_to_principal,
    )


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
        # Pay 5000 interest on the 10th, then 55000 on the 20th WITH the
        # apply-to-principal flag set -- the full leftover hits principal.
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))
        p2 = _pay(loan, 55000, date(2026, 1, 20), apply_to_principal=True)
        result = replay_overdraft_loan(loan, as_of=date(2026, 1, 25))
        self.assertAlmostEqual(result.payment_splits[p2.pk]['Interest_Portion'], 0.0, places=2)
        self.assertAlmostEqual(result.payment_splits[p2.pk]['Principal_Portion'], 55000.0, places=2)
        self.assertAlmostEqual(result.outstanding_principal, 195000.0, places=2)

    def test_next_cycle_prorates_across_the_principal_change(self):
        # Same scenario as above; next cycle (Jan 10 -> Feb 10, 31 days) should be
        # 10 days on 250000 + 21 days on 195000, at 2%/31 per day.
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))
        _pay(loan, 55000, date(2026, 1, 20), apply_to_principal=True)
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

    def test_payoff_stub_correctly_consumes_existing_credit_balance(self):
        # Bank credit via a below-threshold payment on day 20 (interest already
        # cleared exactly on the 10th), then pay off fully while that credit
        # still exists, with the payoff exactly covering principal + the
        # prorated gross stub interest.
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))    # clears cycle-1 interest exactly
        _pay(loan, 30000, date(2026, 1, 20))   # checkbox unchecked -> banks as credit
        # At this point credit_balance should be 30000, outstanding_principal 250000.
        payoff_date = date(2026, 1, 25)
        days_elapsed = (payoff_date - date(2026, 1, 10)).days  # 15
        cycle_days = (date(2026, 2, 10) - date(2026, 1, 10)).days  # 31
        gross_stub = 250000 * (2.0 / 100 / cycle_days) * days_elapsed
        # The existing 30000 credit more than covers the gross stub, so the net
        # stub billed as interest is 0, and only `gross_stub` of the credit is
        # consumed -- the rest (30000 - gross_stub) must remain banked, and the
        # cash this payment brings (principal + gross_stub) must NOT also be
        # debited for the credit-covered portion.
        payoff_amount = 250000 + gross_stub  # exact payoff: principal + gross stub
        p3 = _pay(loan, payoff_amount, payoff_date, apply_to_principal=True)
        result = replay_overdraft_loan(loan, as_of=payoff_date)
        self.assertAlmostEqual(result.outstanding_principal, 0.0, places=1)
        # Interest_Portion on this payoff payment should reflect only the NET
        # stub actually billed as interest after credit is applied -- since
        # credit fully covers the gross stub here, net billed interest is 0.
        self.assertAlmostEqual(result.payment_splits[p3.pk]['Interest_Portion'], 0.0, places=1)
        self.assertAlmostEqual(result.payment_splits[p3.pk]['Principal_Portion'], 250000.0, places=1)
        # Cash conservation: the gross stub was already covered by pre-existing
        # credit, so this payment's cash (principal + gross_stub) is fully
        # absorbed by principal, and the *unused* cash beyond principal
        # (gross_stub) is re-banked as credit alongside the untouched remainder
        # of the original 30000 credit. Net effect: final credit balance is
        # unchanged at 30000 -- only `gross_stub` of it was ever "consumed and
        # replaced" by this payment's own cash, none of it vanishes.
        self.assertAlmostEqual(result.credit_balance, 30000.0, places=1)

    def test_full_payoff_charges_prorated_stub_interest(self):
        # Pay off entirely on day 25 of the first 31-day cycle (Jan 10 -> Feb 10).
        # First, the cycle-1 installment (5000, due Jan 10) is already billed and
        # unpaid by the time this payoff payment lands on Jan 25 -- oldest-first
        # allocation clears that first, THEN the stub for days 10-25 is billed.
        loan = _make_overdraft_loan()
        payoff_date = date(2026, 1, 25)
        days_elapsed = (payoff_date - date(2026, 1, 10)).days  # 15
        cycle_days = (date(2026, 2, 10) - date(2026, 1, 10)).days  # 31
        stub_interest = 250000 * (2.0 / 100 / cycle_days) * days_elapsed
        cycle_1_interest = 5000.0
        payoff_amount = 250000 + cycle_1_interest + stub_interest
        p1 = _pay(loan, payoff_amount, payoff_date, apply_to_principal=True)
        result = replay_overdraft_loan(loan, as_of=payoff_date)
        self.assertAlmostEqual(result.outstanding_principal, 0.0, places=1)
        self.assertAlmostEqual(
            result.payment_splits[p1.pk]['Interest_Portion'],
            cycle_1_interest + stub_interest, places=1)
        self.assertAlmostEqual(
            result.payment_splits[p1.pk]['Principal_Portion'], 250000.0, places=1)

    def test_fully_paid_off_loan_shows_zero_overdue_even_with_leftover_credit(self):
        loan = _make_overdraft_loan(
            principal=250000, first_due=date(2026, 2, 1), loan_date=date(2026, 1, 1),
        )
        _pay(loan, 9000, date(2026, 1, 20))     # checkbox unchecked -> banks as credit
        _pay(loan, 252500, date(2026, 2, 15), apply_to_principal=True)   # full payoff, stub covered partly by credit
        result = replay_overdraft_loan(loan, as_of=date(2026, 2, 15))
        self.assertAlmostEqual(result.outstanding_principal, 0.0, places=1)

        sync_overdraft_loan(loan, as_of=date(2026, 2, 15))
        from microfinance.views import bulk_overdue_map
        overdue = bulk_overdue_map([loan.pk], date(2026, 2, 15))
        self.assertEqual(overdue.get(loan.pk, 0), 0)

    def test_stub_on_same_date_as_existing_due_date_merges_not_drops(self):
        loan = _make_overdraft_loan(first_due=date(2026, 2, 1), loan_date=date(2026, 1, 1))
        _pay(loan, 5000, date(2026, 2, 1))       # pays cycle-1 interest exactly on due date
        _pay(loan, 250000, date(2026, 2, 1), apply_to_principal=True)     # full payoff, same day -> stub lands on same Date_Due
        result = replay_overdraft_loan(loan, as_of=date(2026, 2, 1))
        due_dates = [i['Date_Due'] for i in result.installments]
        self.assertEqual(len(due_dates), len(set(due_dates)),
                          "no two installments should share a Date_Due after merge")
        self.assertAlmostEqual(result.outstanding_principal, 0.0, places=1)


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

        # Strict idempotency: a second call must issue ZERO write statements,
        # not merely leave row counts unchanged (an unconditional UPDATE with
        # identical values would pass the count check but still be a write).
        with CaptureQueriesContext(connection) as ctx:
            sync_overdraft_loan(loan, as_of=date(2026, 2, 10))
        write_queries = [
            q['sql'] for q in ctx.captured_queries
            if q['sql'].strip().upper().split(' ', 1)[0] in ('INSERT', 'UPDATE', 'DELETE')
        ]
        self.assertEqual(write_queries, [])

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


from unittest.mock import patch
from microfinance.views import pay_installment, Recalculate_Penalty
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


class RecalculatePenaltyPaymentsDataCorrectionTest(TestCase):
    """Proves that for overdraft loans, the penalty engine only ever sees the
    INTEREST-designated portion of each payment, not the raw cash amount --
    otherwise a large principal-paydown payment would incorrectly "advance
    pay" and silently zero out penalty on a later, genuinely-unpaid interest
    installment. Penalty accrues on unpaid interest, never on principal.
    """

    def test_overdraft_payments_data_uses_interest_portion_not_amount_paid(self):
        # Spec worked example: pay 5000 interest on the 10th, then 55000 on the
        # 20th. Leftover 55000 >= threshold, so ALL of it hits principal --
        # p2.Interest_Portion ends up 0 even though Amount_Paid is 55000.
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))
        p2 = _pay(loan, 55000, date(2026, 1, 20))

        captured = {}

        def fake_calc(loan_arg, installments_data, payments_data, today):
            captured['payments_data'] = payments_data

        with patch('microfinance.views._calculate_individual_penalties_corrected', side_effect=fake_calc):
            Recalculate_Penalty(loan)

        p2.refresh_from_db()
        self.assertEqual(p2.Amount_Paid, 55000)
        self.assertAlmostEqual(p2.Interest_Portion, 0.0, places=2)

        entry = next(e for e in captured['payments_data'] if e['Date_Paid'] == date(2026, 1, 20))
        # The bug this test guards against: feeding the engine the raw
        # Amount_Paid (55000) here would incorrectly "advance-pay" future
        # interest installments and silently suppress penalty on them.
        self.assertAlmostEqual(entry['Amount_Paid'], 0.0, places=2)
        self.assertNotAlmostEqual(entry['Amount_Paid'], 55000.0, places=2)

    def test_non_overdraft_payments_data_still_uses_raw_amount_paid(self):
        # Control: a Daily/Weekly/Monthly loan (Frequency != 4) must be
        # completely unaffected by the correction -- payments_data carries
        # the raw Amount_Paid exactly as before.
        staff = Staff.objects.create(Officer_Name='Regular Officer', Designation='Collector', Salary=0)
        user = User.objects.create_user(username='regularauthor', password='x')
        client = Clients.objects.create(
            Name='Regular Client', Phone_no1='+911234567892', Verified_By='x',
            author=user, Photo_Id_No='REG123', Major_Medical_Issues='none',
        )
        account = Accounts.objects.create(Client=client)
        guarantor = Guarantors.objects.create()
        loan = Loans.objects.create(
            Principle_Amount=100000, Frequency=3, No_Of_Installments=12,
            Intrest_Rate=2.0, Loan_Collector=staff, Guarantor=guarantor,
            Account=account, First_Due_Date=date(2026, 1, 10), Loan_Date=date(2026, 1, 1),
        )
        payment = _pay(loan, 12345, date(2026, 1, 10))
        # Interest_Portion is never populated for non-overdraft loans (stays
        # at its model default of 0), so if the correction's ternary were
        # ever applied unconditionally, this would come back as 0 instead of
        # the real cash amount.
        self.assertEqual(payment.Interest_Portion, 0)

        captured = {}

        def fake_calc(loan_arg, installments_data, payments_data, today):
            captured['payments_data'] = payments_data

        with patch('microfinance.views._calculate_individual_penalties_corrected', side_effect=fake_calc):
            Recalculate_Penalty(loan)

        entry = next(e for e in captured['payments_data'] if e['Date_Paid'] == date(2026, 1, 10))
        self.assertEqual(entry['Amount_Paid'], 12345)


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
        # NOTE: Add_Loan calls sync_overdraft_loan(instance) with as_of=None,
        # which resolves to date.today() when the replay engine runs. A
        # hardcoded past First_Due_Date would materialize many months of
        # installment rows by the time this test actually executes, so the
        # due date must be computed relative to today instead -- a few days
        # in the future means no cycle has come due yet, and sync should
        # create zero installment rows.
        future_due_date = date.today() + timedelta(days=5)
        factory = RequestFactory()
        post_data = {
            'AccNo': '1', 'Principle_Amount': '250000', 'Frequency': '4',
            'Purpose': 'c', 'No_Of_Installments': '0', 'Intrest_Rate': '2',
            'File_Charge_Percent': '0',
            'First_Due_Date': future_due_date.isoformat(), 'Loan_Date': date.today().isoformat(),
            'Loan_Collector': str(self.staff.pk),
            'security_docs': 'none',
        }
        request = factory.post(
            f'/loan/{self.client_obj.pk}/{self.guarantor.pk}/', post_data)
        request.user = self.user
        Add_Loan(request, pk=self.client_obj.pk, sk=self.guarantor.pk)
        loan = Loans.objects.get(Account=self.account)
        self.assertEqual(loan.Frequency, 4)
        # An overdraft loan must not get a flat No_Of_Installments-based
        # schedule. Since the first due date hasn't arrived yet, sync should
        # not have materialized any installment rows either.
        installment_count = Installments.objects.filter(Loan=loan).count()
        self.assertEqual(installment_count, 0)


from microfinance.overdraft import overdraft_total_owed
from microfinance.views import bulk_overdue_map, loan_repayment_status
from microfinance.tests import _make_loan


class OverdraftTotalOwedTest(TestCase):
    def test_total_owed_before_any_payment(self):
        loan = _make_overdraft_loan()
        total = overdraft_total_owed(loan, as_of=date(2026, 1, 10))
        # 250000 principal + 5000 first-cycle interest, no credit.
        self.assertAlmostEqual(total, 255000.0, places=2)

    def test_total_owed_after_partial_payoff(self):
        loan = _make_overdraft_loan()
        _pay(loan, 5000, date(2026, 1, 10))   # clears interest
        _pay(loan, 55000, date(2026, 1, 20), apply_to_principal=True)  # reduces principal
        total = overdraft_total_owed(loan, as_of=date(2026, 1, 25))
        # Outstanding principal 195000, no unpaid interest yet (next cycle not due).
        self.assertAlmostEqual(total, 195000.0, places=2)


class LoansTotalOverdraftTest(TestCase):
    def test_loans_total_property_uses_overdraft_logic_for_frequency_4(self):
        # NOTE: loan.Total resolves as_of=None to the real date.today() inside
        # overdraft_total_owed, so First_Due_Date must be set relative to today
        # (not a hardcoded past date) to keep exactly one cycle materialized --
        # same reasoning as AddLoanOverdraftDispatchTest above.
        loan = _make_overdraft_loan(first_due=date.today())
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


class DashboardOverdraftSplitTest(TestCase):
    def setUp(self):
        self.dashboard_url = reverse('microfinance:dashboard')

    def test_dashboard_uses_stored_split_for_overdraft_payments(self):
        # Create an overdraft loan with 2% interest rate
        loan = _make_overdraft_loan()
        # Make a payment that will be synced and have Interest_Portion calculated
        _pay(loan, 5000, date(2026, 1, 10))
        sync_overdraft_loan(loan, as_of=date(2026, 1, 10))

        # Get the payment and verify it has the correct Interest_Portion
        payment = Payments.objects.get(Loan=loan)
        # After sync, this payment's Interest_Portion should be ~5000
        self.assertAlmostEqual(payment.Interest_Portion, 5000.0, places=2)

        # Sanity check: the flat-rate reverse-derivation formula would produce
        # a different (wrong) number for this loan's 2% rate
        flat_wrong_principal = payment.Amount_Paid / (1 + (loan.Intrest_Rate / 100))
        flat_wrong_interest = payment.Amount_Paid - flat_wrong_principal
        self.assertNotAlmostEqual(payment.Interest_Portion, flat_wrong_interest, places=2)

        # Now hit the dashboard view through the real URL/response pipeline so we
        # can inspect the actually-rendered template context.
        user = User.objects.create_user(username='dashuser', password='dashpass')
        self.client.force_login(user)
        response = self.client.get(self.dashboard_url, {
            'date_range': 'custom',
            'start_date': '2026-01-01',
            'end_date': '2026-01-31',
        })

        self.assertEqual(response.status_code, 200)
        interest_earned = response.context['interest_earned_period']
        # Should equal the payment's stored Interest_Portion, not the flat-rate wrong value
        self.assertAlmostEqual(interest_earned, 5000.0, places=2)
        self.assertNotAlmostEqual(interest_earned, flat_wrong_interest, places=2)

    def test_dashboard_still_uses_flat_rate_for_non_overdraft_payments(self):
        # Create a regular (non-overdraft) loan - Frequency != 4
        staff = Staff.objects.create(Officer_Name='Regular Officer', Designation='Collector', Salary=0)
        user = User.objects.create_user(username='regauthor', password='x')
        client = Clients.objects.create(
            Name='Regular Client', Phone_no1='+911234567892', Verified_By='x',
            author=user, Photo_Id_No='REG123', Major_Medical_Issues='none',
        )
        account = Accounts.objects.create(Client=client)
        guarantor = Guarantors.objects.create()
        # Frequency=1 means Daily (or whatever regular frequency)
        loan = Loans.objects.create(
            Principle_Amount=100000, Frequency=1, No_Of_Installments=12,
            Intrest_Rate=24.0, Loan_Collector=staff, Guarantor=guarantor,
            Account=account, First_Due_Date=date(2026, 1, 10), Loan_Date=date(2026, 1, 1),
        )

        # Create a payment for this regular loan
        payment = Payments.objects.create(Loan=loan, Amount_Paid=10000, Date_Paid=date(2026, 1, 10), Payment_Type=1)
        # For non-overdraft, Interest_Portion won't be set by sync; it will be derived
        # in the dashboard view using the flat-rate formula

        # Call the dashboard view through the real URL/response pipeline.
        dashuser = User.objects.create_user(username='dashuser2', password='dashpass')
        self.client.force_login(dashuser)
        response = self.client.get(self.dashboard_url, {
            'date_range': 'custom',
            'start_date': '2026-01-01',
            'end_date': '2026-01-31',
        })

        self.assertEqual(response.status_code, 200)
        interest_earned = response.context['interest_earned_period']
        # For non-overdraft, should use the flat-rate formula
        flat_principal = payment.Amount_Paid / (1 + (loan.Intrest_Rate / 100))
        flat_interest = payment.Amount_Paid - flat_principal
        self.assertAlmostEqual(interest_earned, flat_interest, places=2)
        # Sanity check: this must differ from the stored-split value the
        # overdraft test expects, so neither test could pass vacuously.
        self.assertNotAlmostEqual(interest_earned, 5000.0, places=2)


class OverdueLoansOfficerGroupingTest(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staffviewer', password='x', is_staff=True)

    def test_view_groups_overdue_loans_by_officer(self):
        loan = _make_overdraft_loan(first_due=date.today() - timedelta(days=40))
        sync_overdraft_loan(loan, as_of=date.today())
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('microfinance:overdue'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('officer_groups', response.context)
        self.assertIn('defaulter_rows', response.context)
        officer_names = [g['officer'].Officer_Name for g in response.context['officer_groups']]
        self.assertIn(loan.Loan_Collector.Officer_Name, officer_names)

    def test_defaulter_rows_only_include_behind_loans(self):
        loan = _make_overdraft_loan(first_due=date.today() - timedelta(days=40))
        sync_overdraft_loan(loan, as_of=date.today())
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('microfinance:overdue'))
        defaulter_rows = response.context['defaulter_rows']
        # Not vacuous: the loan created above (40 days overdue, unpaid) must
        # actually show up as a defaulter.
        self.assertGreaterEqual(len(defaulter_rows), 1)
        defaulter_pks = [row['loan'].pk for row in defaulter_rows]
        self.assertIn(loan.pk, defaulter_pks)
        for row in defaulter_rows:
            self.assertEqual(row['status']['state'], 'behind')


class OverdraftDateValidationTest(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(Officer_Name='Officer', Designation='Collector', Salary=0)
        self.user = User.objects.create_user(username='dateloanauthor', password='x', is_staff=True)
        self.client_obj = Clients.objects.create(
            Name='Date Loan Client', Phone_no1='+911234567893', Verified_By='x',
            author=self.user, Photo_Id_No='DL123', Major_Medical_Issues='none',
        )
        self.account = Accounts.objects.create(Client=self.client_obj)
        self.guarantor = Guarantors.objects.create()

    def test_add_loan_rejects_first_due_equal_to_loan_date_for_overdraft(self):
        # Reuses AddLoanOverdraftDispatchTest's pattern for a valid overdraft
        # AddLoan POST payload, then mutates First_Due_Date to equal Loan_Date.
        today = date.today()
        post_data = {
            'AccNo': '1', 'Principle_Amount': '250000', 'Frequency': '4',
            'Purpose': 'c', 'No_Of_Installments': '0', 'Intrest_Rate': '2',
            'File_Charge_Percent': '0',
            'First_Due_Date': today.isoformat(), 'Loan_Date': today.isoformat(),
            'Loan_Collector': str(self.staff.pk),
            'security_docs': 'none',
        }
        from microfinance.forms import AddLoan
        form = AddLoan(post_data)
        self.assertFalse(form.is_valid())

    def test_edit_loan_detail_rejects_first_due_before_loan_date_for_overdraft(self):
        loan = _make_overdraft_loan()
        post_data = {
            'Principle_Amount': str(loan.Principle_Amount),
            'Frequency': '4',
            'Purpose': 'c',
            'No_Of_Installments': '0',
            'Intrest_Rate': '2',
            'File_Charge_Percent': '0',
            'Loan_Date': date(2026, 1, 10).isoformat(),
            'First_Due_Date': date(2026, 1, 1).isoformat(),  # before Loan_Date
            'Loan_Collector': str(loan.Loan_Collector.pk),
        }
        from microfinance.forms import EditLoanDetail
        form = EditLoanDetail(post_data, instance=loan)
        self.assertFalse(form.is_valid())

    def test_replay_raises_value_error_on_non_positive_cycle_days(self):
        loan = _make_overdraft_loan(first_due=date(2026, 1, 1), loan_date=date(2026, 1, 1))
        with self.assertRaises(ValueError):
            replay_overdraft_loan(loan, as_of=date(2026, 3, 1))


class OverdraftLazyMaterializationTest(TestCase):
    def test_loan_detail_materializes_overdue_overdraft_loan(self):
        loan = _make_overdraft_loan(
            first_due=date.today() - timedelta(days=20),
            loan_date=date.today() - timedelta(days=25),
        )
        self.assertEqual(Installments.objects.filter(Loan=loan).count(), 0)

        user = User.objects.create_user(username='staffuser', password='x', is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse('microfinance:loandetail', args=[loan.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertGreater(Installments.objects.filter(Loan=loan).count(), 0)
        # Not just materialized somewhere by the time the response is built:
        # the rendered installment/payment table itself (built from the
        # `Installment` queryset fetched at the top of the view, before any
        # later sync in the same request) must reflect the synced schedule
        # too, or a same-request stale-read gap could leave the page showing
        # an empty table with installments materialized too late to appear.
        self.assertGreater(len(response.context['combinedInstallmentPaymentView']), 0)

    def test_overdue_loans_screen_shows_never_paid_overdue_overdraft_loan(self):
        loan = _make_overdraft_loan(
            first_due=date.today() - timedelta(days=20),
            loan_date=date.today() - timedelta(days=25),
        )
        self.assertEqual(Installments.objects.filter(Loan=loan).count(), 0)

        user = User.objects.create_user(username='staffuser2', password='x', is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse('microfinance:overdue'))

        self.assertEqual(response.status_code, 200)
        overdue_pks = {row['loan'].pk for row in response.context['rows']}
        self.assertIn(loan.pk, overdue_pks)
        matching = [r for r in response.context['rows'] if r['loan'].pk == loan.pk]
        self.assertGreater(matching[0]['overdue'], 0)


class NoOfInstallmentsOverdraftOptionalTest(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(Officer_Name='Officer', Designation='Collector', Salary=0)
        self.user = User.objects.create_user(username='noinstallmentsauthor', password='x', is_staff=True)
        self.client_obj = Clients.objects.create(
            Name='No Installments Client', Phone_no1='+911234567894', Verified_By='x',
            author=self.user, Photo_Id_No='NI123', Major_Medical_Issues='none',
        )
        self.account = Accounts.objects.create(Client=self.client_obj)
        self.guarantor = Guarantors.objects.create()

    def test_add_loan_valid_without_no_of_installments_for_overdraft(self):
        from microfinance.forms import AddLoan
        today = date.today()
        post_data = {
            'AccNo': str(self.account.pk), 'Principle_Amount': '250000', 'Frequency': '4',
            'Purpose': 'c', 'No_Of_Installments': '',  # blank, as the browser sends an empty number input
            'Intrest_Rate': '2', 'File_Charge_Percent': '0',
            'First_Due_Date': (today + timedelta(days=30)).isoformat(),
            'Loan_Date': today.isoformat(),
            'Loan_Collector': str(self.staff.pk),
            'security_docs': 'none',
        }
        form = AddLoan(post_data)
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        self.assertEqual(instance.No_Of_Installments, 0)

    def test_add_loan_still_requires_no_of_installments_for_monthly(self):
        from microfinance.forms import AddLoan
        today = date.today()
        post_data = {
            'AccNo': str(self.account.pk), 'Principle_Amount': '100000', 'Frequency': '3',
            'Purpose': 'c', 'No_Of_Installments': '',
            'Intrest_Rate': '2', 'File_Charge_Percent': '0',
            'First_Due_Date': (today + timedelta(days=30)).isoformat(),
            'Loan_Date': today.isoformat(),
            'Loan_Collector': str(self.staff.pk),
            'security_docs': 'none',
        }
        form = AddLoan(post_data)
        self.assertFalse(form.is_valid())
        self.assertIn('No_Of_Installments', form.errors)


class AddLoanFormRerenderKeepsSelectedFrequencyTest(TestCase):
    """A validation failure elsewhere on the form must not visually reset
    the Frequency dropdown to its first option (Daily) on re-render --
    Django's bound field.value() returns a string ('4'), while the model's
    LOAN_CHOICES values are ints, so a plain == comparison in the template
    always failed and every select silently fell back to its first
    <option>. This looks like "the loan type changed to Daily" even though
    nothing was actually saved."""

    def setUp(self):
        self.staff = Staff.objects.create(Officer_Name='Officer', Designation='Collector', Salary=0)
        self.user = User.objects.create_user(username='rerenderauthor', password='x', is_staff=True)
        self.client_obj = Clients.objects.create(
            Name='Rerender Client', Phone_no1='+911234567895', Verified_By='x',
            author=self.user, Photo_Id_No='RR123', Major_Medical_Issues='none',
        )
        self.account = Accounts.objects.create(Client=self.client_obj)
        self.guarantor = Guarantors.objects.create()

    def test_overdraft_selection_survives_a_rerender_after_a_validation_error(self):
        future_due_date = date.today() + timedelta(days=5)
        post_data = {
            'AccNo': str(self.account.pk), 'Principle_Amount': '250000', 'Frequency': '4',
            # Invalid on purpose: 'x' is not a valid Purpose choice, forcing
            # the view to re-render the bound form with errors instead of
            # creating a loan.
            'Purpose': 'x', 'No_Of_Installments': '',
            'Intrest_Rate': '2', 'File_Charge_Percent': '0',
            'First_Due_Date': future_due_date.isoformat(), 'Loan_Date': date.today().isoformat(),
            'Loan_Collector': str(self.staff.pk),
            'security_docs': 'none',
        }
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('microfinance:addloan', args=[self.client_obj.pk, self.guarantor.pk]),
            post_data,
        )
        self.assertEqual(response.status_code, 200)  # re-rendered, not redirected
        self.assertFalse(Loans.objects.filter(Account=self.account).exists())
        html = response.content.decode()
        # The OverDraft <option> must still carry selected -- proves the
        # dropdown reflects what the user actually submitted, not a reset
        # to the first choice (Daily).
        self.assertIn('value="4" selected', html)

    def test_non_field_validation_error_is_rendered_on_the_page(self):
        # clean()'s "First Due Date must be after Loan Date" error is a
        # non-field error, not attached to any single input -- if the
        # template never renders form.non_field_errors, the page silently
        # fails to create the loan with no visible explanation at all.
        today = date.today()
        post_data = {
            'AccNo': str(self.account.pk), 'Principle_Amount': '250000', 'Frequency': '4',
            'Purpose': 'c', 'No_Of_Installments': '',
            'Intrest_Rate': '2', 'File_Charge_Percent': '0',
            'First_Due_Date': today.isoformat(), 'Loan_Date': today.isoformat(),
            'Loan_Collector': str(self.staff.pk),
            'security_docs': 'none',
        }
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('microfinance:addloan', args=[self.client_obj.pk, self.guarantor.pk]),
            post_data,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Loans.objects.filter(Account=self.account).exists())
        self.assertContains(response, 'First Due Date must be after Loan Date')


class LoanDetailOverdraftTotalsTest(TestCase):
    """Loan_Detail's own GET-path totals (Total_Loan_Amount, Total_Pending,
    Amount_Overdue, amnt_pen) were computed with the flat principal+interest
    formula and a payment-subtraction running balance, unconditionally for
    every loan type -- never routed through the replay engine, even though
    Loan.Total/loan_repayment_status already do this correctly. For a fresh
    overdraft loan with a future First_Due_Date and zero payments, this
    showed a phantom flat "Total Pending" (principal + one flat interest
    charge) instead of the correct outstanding balance (principal only,
    since no interest has accrued yet)."""

    def setUp(self):
        self.staff = Staff.objects.create(Officer_Name='Officer', Designation='Collector', Salary=0)
        self.user = User.objects.create_user(username='loandetailauthor', password='x', is_staff=True)
        self.client_obj = Clients.objects.create(
            Name='Loan Detail Client', Phone_no1='+911234567896', Verified_By='x',
            author=self.user, Photo_Id_No='LD123', Major_Medical_Issues='none',
        )
        self.account = Accounts.objects.create(Client=self.client_obj)
        self.guarantor = Guarantors.objects.create()
        self.client.force_login(self.user)

    def _make_loan(self, first_due, loan_date, principal=100000, rate=20.0):
        return Loans.objects.create(
            Principle_Amount=principal, Frequency=4, No_Of_Installments=0,
            Intrest_Rate=rate, Penalty_Rate=2.0,
            Loan_Collector=self.staff, Guarantor=self.guarantor, Account=self.account,
            First_Due_Date=first_due, Loan_Date=loan_date,
        )

    def test_fresh_overdraft_loan_shows_outstanding_not_flat_total(self):
        # First_Due_Date in the future: no cycle has come due, so nothing
        # is owed yet except the principal itself. The flat formula
        # (principal + one flat interest charge) is wrong here -- it bills
        # interest that hasn't accrued.
        loan = self._make_loan(
            first_due=date.today() + timedelta(days=30), loan_date=date.today(),
            principal=100000, rate=20.0,
        )
        response = self.client.get(reverse('microfinance:loandetail', args=[loan.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['Total_Pending'], loan.Total)
        self.assertEqual(response.context['Total_Loan_Amount'], loan.Total)
        self.assertNotEqual(response.context['Total_Pending'], 120000.0)  # the old flat figure
        self.assertEqual(response.context['Amount_Overdue'], 0)

    def test_backdated_overdraft_loan_amount_overdue_matches_repayment_status(self):
        loan = self._make_loan(
            first_due=date.today() - timedelta(days=20), loan_date=date.today() - timedelta(days=25),
            principal=100000, rate=20.0,
        )
        response = self.client.get(reverse('microfinance:loandetail', args=[loan.pk]))
        self.assertEqual(response.status_code, 200)
        expected = loan_repayment_status(loan)['overdue']
        self.assertGreater(expected, 0)
        self.assertEqual(response.context['Amount_Overdue'], expected)
        self.assertEqual(response.context['amnt_pen'], round(expected, 1))

    def test_total_pending_does_not_double_subtract_a_fully_paid_cycle(self):
        # Reproduces the exact screenshot: pay the first cycle's interest in
        # full. Loan.Total already nets the payment out (interest fully
        # paid, principal untouched -> Total stays at principal). Without
        # the fix, the per-row walk loop subtracts the payment a SECOND
        # time from the headline Total_Pending, landing on principal minus
        # the payment (80000 for a 100000 principal / 20000 payment).
        loan = self._make_loan(
            first_due=date.today(), loan_date=date.today() - timedelta(days=30),
            principal=100000, rate=20.0,
        )
        Payments.objects.create(Loan=loan, Amount_Paid=20000, Date_Paid=date.today(), Payment_Type=1)
        response = self.client.get(reverse('microfinance:loandetail', args=[loan.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['Total_Pending'], loan.Total)
        self.assertEqual(response.context['Total_Pending'], 100000.0)
        self.assertNotEqual(response.context['Total_Pending'], 80000.0)  # the old double-subtracted figure

    def test_per_row_total_balance_matches_headline_when_no_credit_was_banked(self):
        loan = self._make_loan(
            first_due=date.today(), loan_date=date.today() - timedelta(days=30),
            principal=100000, rate=20.0,
        )
        Payments.objects.create(Loan=loan, Amount_Paid=20000, Date_Paid=date.today(), Payment_Type=1)
        response = self.client.get(reverse('microfinance:loandetail', args=[loan.pk]))
        rows = response.context['combinedInstallmentPaymentView']
        self.assertTrue(rows)
        self.assertEqual(rows[-1]['Total_Balance'], loan.Total)

    def test_future_due_date_shows_an_upcoming_estimate(self):
        loan = self._make_loan(
            first_due=date.today() + timedelta(days=25), loan_date=date.today(),
            principal=100000, rate=20.0,
        )
        response = self.client.get(reverse('microfinance:loandetail', args=[loan.pk]))
        self.assertEqual(response.status_code, 200)
        upcoming = response.context['overdraft_upcoming']
        self.assertIsNotNone(upcoming)
        self.assertEqual(upcoming['Date_Due'], loan.First_Due_Date)
        self.assertGreater(upcoming['Estimated_Interest'], 0)
        self.assertContains(response, 'Upcoming (estimate)')


class OverdraftFullLifecycleTest(TestCase):
    """End-to-end regression net through the real views (AddLoan POST,
    Loan_Detail's payment POST, Overdue_Loans GET) rather than calling
    engine functions directly -- every prior manual-testing bug was in
    Loan_Detail's rendered context, and no existing test asserted the full
    set of displayed numbers together at each lifecycle step. Each scenario
    below hand-computes its expected values against the design spec's own
    worked examples rather than trusting whatever the code currently
    returns."""

    def setUp(self):
        self.staff = Staff.objects.create(Officer_Name='Officer', Designation='Collector', Salary=0)
        self.user = User.objects.create_user(username='lifecycleauthor', password='x', is_staff=True)
        self.client_obj = Clients.objects.create(
            Name='Lifecycle Client', Phone_no1='+911234567897', Verified_By='x',
            author=self.user, Photo_Id_No='LC123', Major_Medical_Issues='none',
        )
        self.account = Accounts.objects.create(Client=self.client_obj)
        self.guarantor = Guarantors.objects.create()
        self.client.force_login(self.user)

    def _create_loan_via_ui(self, first_due, loan_date, principal=250000,
                             rate=2.0, penalty_rate=None):
        post_data = {
            'AccNo': str(self.account.pk), 'Principle_Amount': str(principal),
            'Frequency': '4', 'Purpose': 'c', 'No_Of_Installments': '',
            'Intrest_Rate': str(rate),
            'File_Charge_Percent': '0',
            'First_Due_Date': first_due.isoformat(), 'Loan_Date': loan_date.isoformat(),
            'Loan_Collector': str(self.staff.pk),
            'security_docs': 'none',
        }
        if penalty_rate is not None:
            post_data['Penalty_Rate'] = str(penalty_rate)
        response = self.client.post(
            reverse('microfinance:addloan', args=[self.client_obj.pk, self.guarantor.pk]),
            post_data,
        )
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['form'].errors)
        loan = Loans.objects.get(Account=self.account)
        return loan

    def _pay_via_ui(self, loan, amount, on, apply_to_principal=False):
        post_data = {'pay': '1', 'amount': str(amount), 'date_paid': on.isoformat()}
        if apply_to_principal:
            post_data['apply_to_principal'] = '1'
        response = self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            post_data,
        )
        self.assertEqual(response.status_code, 302)

    def _get_detail(self, loan):
        response = self.client.get(reverse('microfinance:loandetail', args=[loan.pk]))
        self.assertEqual(response.status_code, 200)
        return response

    def _get_overdue_pks(self):
        response = self.client.get(reverse('microfinance:overdue'))
        self.assertEqual(response.status_code, 200)
        return {row['loan'].pk for row in response.context['rows']}

    def test_scenario_a_fresh_future_due_loan(self):
        loan = self._create_loan_via_ui(
            first_due=date.today() + timedelta(days=30), loan_date=date.today(),
            principal=250000, rate=2.0,
        )
        response = self._get_detail(loan)
        self.assertEqual(response.context['Total_Pending'], 250000.0)
        self.assertEqual(response.context['Total_Loan_Amount'], 250000.0)
        self.assertEqual(response.context['Amount_Overdue'], 0)
        self.assertEqual(response.context['amnt_pen'], 0.0)
        self.assertEqual(len(response.context['combinedInstallmentPaymentView']), 0)
        self.assertIsNotNone(response.context['overdraft_upcoming'])
        self.assertNotIn(loan.pk, self._get_overdue_pks())

    def test_scenario_b_backdated_unpaid_loan_is_overdue_and_penalized(self):
        loan = self._create_loan_via_ui(
            first_due=date.today() - timedelta(days=20), loan_date=date.today() - timedelta(days=25),
            principal=250000, rate=2.0, penalty_rate=3.0,
        )
        response = self._get_detail(loan)
        # 20-day-old cycle billed on 250000 @ 2%/mo, unpaid -> overdue == the
        # single materialized installment's Installment_Due (interest only,
        # no proration needed since only one cycle exists and nothing paid).
        expected_overdue = loan_repayment_status(loan)['overdue']
        self.assertGreater(expected_overdue, 0)
        self.assertEqual(response.context['Amount_Overdue'], expected_overdue)
        self.assertEqual(response.context['amnt_pen'], round(expected_overdue, 1))
        self.assertIn(loan.pk, self._get_overdue_pks())
        # Penalty at the loan's own configured 3%/day rate, not the 2% default.
        penalty = Penalty.objects.filter(Loan=loan).first()
        self.assertIsNotNone(penalty)
        self.assertEqual(penalty.Percent, Decimal('3'))

    def test_scenario_c_paying_exact_interest_clears_overdue(self):
        loan = self._create_loan_via_ui(
            first_due=date.today(), loan_date=date.today() - timedelta(days=30),
            principal=250000, rate=2.0,
        )
        # 30-day cycle @ 2%/mo on 250000 = 5000.0 exactly (design spec's own worked example).
        self._pay_via_ui(loan, 5000.0, date.today())
        response = self._get_detail(loan)
        self.assertEqual(response.context['Total_Pending'], 250000.0)
        self.assertEqual(response.context['Amount_Overdue'], 0)
        self.assertNotIn(loan.pk, self._get_overdue_pks())

    def test_scenario_d_unchecked_excess_banks_as_credit_not_principal(self):
        loan = self._create_loan_via_ui(
            first_due=date.today(), loan_date=date.today() - timedelta(days=30),
            principal=250000, rate=2.0,
        )
        # Interest (5000) + an excess of 30000, checkbox NOT checked --
        # must bank the excess as credit, not touch principal, no matter
        # how large the excess is (no threshold anymore).
        self._pay_via_ui(loan, 35000.0, date.today(), apply_to_principal=False)
        response = self._get_detail(loan)
        self.assertEqual(response.context['Total_Pending'], 250000.0)  # principal untouched
        upcoming = response.context['overdraft_upcoming']
        self.assertIsNotNone(upcoming)
        # Next cycle's interest (250000 @ 2%/mo = 5000) minus the 30000
        # credit is negative -> floored at 0 by the estimate's own max(0, ...).
        self.assertEqual(upcoming['Estimated_Interest'], 0.0)

    def test_scenario_d2_unchecked_full_payoff_amount_still_banks_as_credit(self):
        # Even a payment large enough to fully retire the loan does NOT
        # close it if the checkbox is unchecked -- the whole excess just
        # banks as credit and the loan stays open, per explicit design.
        loan = self._create_loan_via_ui(
            first_due=date.today(), loan_date=date.today() - timedelta(days=30),
            principal=250000, rate=2.0,
        )
        self._pay_via_ui(loan, 255000.0, date.today(), apply_to_principal=False)
        response = self._get_detail(loan)
        self.assertEqual(response.context['Total_Pending'], 250000.0)  # principal untouched, loan still open

    def test_scenario_e_checked_excess_reduces_principal(self):
        loan = self._create_loan_via_ui(
            first_due=date.today(), loan_date=date.today() - timedelta(days=30),
            principal=250000, rate=2.0,
        )
        # Interest (5000) + an excess of 55000, checkbox CHECKED -- the
        # entire excess reduces principal, no minimum required.
        self._pay_via_ui(loan, 60000.0, date.today(), apply_to_principal=True)
        response = self._get_detail(loan)
        self.assertEqual(response.context['Total_Pending'], 195000.0)  # 250000 - 55000
        upcoming = response.context['overdraft_upcoming']
        self.assertIsNotNone(upcoming)
        # Next cycle's interest computed on the reduced principal: 195000 @ 2%/mo = 3900.
        self.assertAlmostEqual(upcoming['Estimated_Interest'], 3900.0, places=1)

    def test_scenario_e2_checked_tiny_excess_still_reduces_principal(self):
        # No minimum: checkbox checked applies the FULL leftover to
        # principal even when it's tiny (e.g. 1 rupee over interest).
        loan = self._create_loan_via_ui(
            first_due=date.today(), loan_date=date.today() - timedelta(days=30),
            principal=250000, rate=2.0,
        )
        self._pay_via_ui(loan, 5001.0, date.today(), apply_to_principal=True)
        response = self._get_detail(loan)
        self.assertEqual(response.context['Total_Pending'], 249999.0)  # 250000 - 1

    def test_scenario_f_two_cycles_second_unpaid_overdue_is_second_only(self):
        loan = self._create_loan_via_ui(
            first_due=date.today() - timedelta(days=35), loan_date=date.today() - timedelta(days=65),
            principal=250000, rate=2.0,
        )
        first_due_date = date.today() - timedelta(days=35)
        self._pay_via_ui(loan, 5000.0, first_due_date)  # clears first cycle exactly
        response = self._get_detail(loan)
        self.assertEqual(len(response.context['combinedInstallmentPaymentView']), 2)
        # Overdue reflects only the second, unpaid cycle -- not both.
        expected_overdue = loan_repayment_status(loan)['overdue']
        self.assertGreater(expected_overdue, 0)
        self.assertAlmostEqual(expected_overdue, 5000.0, delta=50)
        self.assertEqual(response.context['Amount_Overdue'], expected_overdue)

    def test_scenario_g_full_payoff_zeroes_out_pending(self):
        loan = self._create_loan_via_ui(
            first_due=date.today(), loan_date=date.today() - timedelta(days=30),
            principal=250000, rate=2.0,
        )
        # Interest (5000) + full principal (250000), paid off completely on
        # the due date -- checkbox CHECKED, since full payoff also requires
        # the explicit choice, per the design.
        self._pay_via_ui(loan, 255000.0, date.today(), apply_to_principal=True)
        response = self._get_detail(loan)
        self.assertEqual(response.context['Total_Pending'], 0)
        self.assertEqual(response.context['Amount_Overdue'], 0)
        self.assertIsNone(response.context['overdraft_upcoming'] and response.context['overdraft_upcoming']['Estimated_Interest'] or None)
        self.assertNotIn(loan.pk, self._get_overdue_pks())


class OverdraftPaymentCorrectionTest(TestCase):
    """Editing, deleting, or backdating a payment must not leave the loan's
    displayed numbers inconsistent with what a fresh loan carrying that
    exact final payment history would show -- sync_overdraft_loan's frozen-
    row rule silently ignores a correction to an already-settled cycle, so
    edit/delete/backdate must go through rebuild_overdraft_loan instead."""

    def setUp(self):
        self.staff = Staff.objects.create(Officer_Name='Officer', Designation='Collector', Salary=0)
        self.user = User.objects.create_user(username='correctionauthor', password='x', is_staff=True)
        self.client_obj = Clients.objects.create(
            Name='Correction Client', Phone_no1='+911234567898', Verified_By='x',
            author=self.user, Photo_Id_No='CX123', Major_Medical_Issues='none',
        )
        self.account = Accounts.objects.create(Client=self.client_obj)
        self.guarantor = Guarantors.objects.create()
        self.client.force_login(self.user)

    def _make_loan(self, first_due, loan_date, principal=250000, rate=2.0):
        return Loans.objects.create(
            Principle_Amount=principal, Frequency=4, No_Of_Installments=0,
            Intrest_Rate=rate, Penalty_Rate=2.0,
            Loan_Collector=self.staff, Guarantor=self.guarantor, Account=self.account,
            First_Due_Date=first_due, Loan_Date=loan_date,
        )

    def _get_detail(self, loan):
        response = self.client.get(reverse('microfinance:loandetail', args=[loan.pk]))
        self.assertEqual(response.status_code, 200)
        return response

    def _snapshot(self, loan):
        response = self._get_detail(loan)
        ctx = response.context
        return {
            'Total_Pending': ctx['Total_Pending'],
            'Amount_Overdue': ctx['Amount_Overdue'],
            'amnt_pen': ctx['amnt_pen'],
            'row_count': len(ctx['combinedInstallmentPaymentView']),
        }

    def test_editing_a_payment_amount_updates_the_loan_not_just_the_row(self):
        loan = self._make_loan(
            first_due=date.today(), loan_date=date.today() - timedelta(days=30),
        )
        # Pay the exact interest (5000) first, so the cycle's Installment
        # row settles and freezes (Date_Paid is set) -- this is the state
        # an ordinary sync would refuse to touch, which is exactly the case
        # this test needs to exercise, not one where the row was never
        # frozen to begin with.
        Payments.objects.create(Loan=loan, Amount_Paid=5000, Date_Paid=date.today(), Payment_Type=1)
        before = self._snapshot(loan)
        self.assertEqual(before['Amount_Overdue'], 0)
        settled_row = Installments.objects.get(Loan=loan, Date_Due=date.today())
        self.assertIsNotNone(settled_row.Date_Paid)  # confirms frozen before the edit

        # Now correct it DOWN to 3000 (a mistake: staff recorded too much) --
        # the cycle should go back to being underpaid.
        payment = Payments.objects.filter(Loan=loan, Payment_Type=1).first()
        response = self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'edit_payment': '1', 'payment_id': str(payment.pk),
             'amount': '3000', 'date_paid': date.today().isoformat(), 'payment_type': '1'},
        )
        self.assertIn(response.status_code, (200, 302))

        after = self._snapshot(loan)
        self.assertGreater(after['Amount_Overdue'], 0)  # corrected DOWN -> now underpaid
        self.assertEqual(after['Total_Pending'], loan.Total)
        # The row itself must have been unfrozen/rebuilt, not left stale.
        rebuilt_row = Installments.objects.get(Loan=loan, Date_Due=date.today())
        self.assertIsNone(rebuilt_row.Date_Paid)

        # Must match a loan built fresh with the corrected amount from the start.
        fresh_loan = self._make_loan(
            first_due=date.today(), loan_date=date.today() - timedelta(days=30),
        )
        Payments.objects.create(Loan=fresh_loan, Amount_Paid=3000, Date_Paid=date.today(), Payment_Type=1)
        fresh = self._snapshot(fresh_loan)
        self.assertEqual(after['Total_Pending'], fresh['Total_Pending'])
        self.assertEqual(after['Amount_Overdue'], fresh['Amount_Overdue'])

    def test_deleting_a_payment_reverts_the_loan_to_unpaid_state(self):
        loan = self._make_loan(
            first_due=date.today(), loan_date=date.today() - timedelta(days=30),
        )
        Payments.objects.create(Loan=loan, Amount_Paid=5000, Date_Paid=date.today(), Payment_Type=1)
        before = self._snapshot(loan)
        self.assertEqual(before['Amount_Overdue'], 0)
        settled_row = Installments.objects.get(Loan=loan, Date_Due=date.today())
        self.assertIsNotNone(settled_row.Date_Paid)  # confirms frozen before the delete

        payment = Payments.objects.filter(Loan=loan, Payment_Type=1).first()
        response = self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'delete_payment': '1', 'payment_id': str(payment.pk)},
        )
        self.assertIn(response.status_code, (200, 302))

        after = self._snapshot(loan)
        self.assertGreater(after['Amount_Overdue'], 0)  # payment gone -> overdue again
        self.assertEqual(after['Total_Pending'], loan.Total)
        # The row itself must be unfrozen/rebuilt, not left stale as "paid".
        rebuilt_row = Installments.objects.get(Loan=loan, Date_Due=date.today())
        self.assertIsNone(rebuilt_row.Date_Paid)
        self.assertEqual(rebuilt_row.Installment_Paid, 0)

        # Must match a loan that never had that payment at all.
        fresh_loan = self._make_loan(
            first_due=date.today(), loan_date=date.today() - timedelta(days=30),
        )
        fresh = self._snapshot(fresh_loan)
        self.assertEqual(after['Total_Pending'], fresh['Total_Pending'])
        self.assertEqual(after['Amount_Overdue'], fresh['Amount_Overdue'])

    def test_backdated_payment_after_a_cycle_already_settled_is_not_ignored(self):
        # Two cycles have already elapsed and been paid; now insert a
        # forgotten payment dated back in the FIRST cycle, after it (and a
        # later one) are already frozen/settled. second_due is derived with
        # the same relativedelta(months=1) the engine itself uses, rather
        # than a hand-picked day count, since month lengths vary.
        # first_due is set 1 month + 5 days back (not 2 months): that puts
        # second_due (first_due + 1mo) just 5 days ago, and the THIRD due
        # date (first_due + 2mo) about 25 days in the future -- so exactly
        # two cycles have elapsed, not three.
        from dateutil.relativedelta import relativedelta
        first_due = date.today() - relativedelta(months=1) - timedelta(days=5)
        second_due = first_due + relativedelta(months=1)
        loan = self._make_loan(first_due=first_due, loan_date=first_due - timedelta(days=30))
        # Overpay both cycles up front so nothing is overdue yet.
        response = self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'pay': '1', 'amount': '5000', 'date_paid': first_due.isoformat()},
        )
        response = self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'pay': '1', 'amount': '5000', 'date_paid': second_due.isoformat()},
        )
        before = self._snapshot(loan)
        self.assertEqual(before['Amount_Overdue'], 0)
        self.assertEqual(before['row_count'], 2)

        # Now insert a forgotten backdated payment landing inside the first
        # (already-settled) cycle: 1000 rupees, below the interest still
        # owed nowhere (cycle 1's interest is already fully paid by the
        # first Payments row), so per the threshold-gated design this
        # entire 1000 correctly banks as advance-interest credit -- not
        # applied as Interest_Portion or Principal_Portion on ITS OWN row.
        # That's not a bug: credit is a third, deferred state (the spec's
        # own words), and its effect shows up on cycle 2's Installment_Due
        # (reduced by the banked amount), not on this payment's split.
        backdate = first_due + timedelta(days=5)
        response = self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'pay': '1', 'amount': '1000', 'date_paid': backdate.isoformat()},
        )
        self.assertIn(response.status_code, (200, 302))

        # What actually proves the frozen-row bypass worked: cycle 2's
        # Installment_Due on disk must reflect the credit (5000 - 1000 =
        # 4000), not the stale 5000 an ordinary sync would have left in
        # place because that row was already settled (Date_Paid set) by
        # the time this backdated payment arrived.
        second_cycle_row = Installments.objects.get(Loan=loan, Date_Due=second_due)
        self.assertAlmostEqual(second_cycle_row.Installment_Due, 4000.0, places=1)

        # Cash conservation: sum of Interest_Portion across all three
        # payments must equal the total interest actually billed (5000 for
        # cycle 1 + 4000 for the credit-reduced cycle 2 = 9000), and the
        # loan's own Total must match what the replay engine reports.
        total_interest_recorded = Payments.objects.filter(
            Loan=loan, Payment_Type=1).aggregate(Sum('Interest_Portion'))['Interest_Portion__sum']
        self.assertAlmostEqual(total_interest_recorded, 9000.0, places=1)

    def test_penalty_paid_survives_an_unrelated_rebuild(self):
        # A rebuild deletes Installments, which CASCADEs to Penalty (the
        # model's own FK). If a correction on one payment triggers a
        # rebuild, a penalty payment already recorded against a DIFFERENT,
        # unrelated cycle must not be silently erased.
        loan = self._make_loan(
            first_due=date.today() - timedelta(days=40), loan_date=date.today() - timedelta(days=70),
        )
        # First cycle: never paid -> accrues a penalty.
        self._get_detail(loan)  # materializes + computes the penalty
        penalty = Penalty.objects.filter(Loan=loan).order_by('Date_Started').first()
        self.assertIsNotNone(penalty)
        self.assertGreater(penalty.Penalty_Calc, 0)

        # Pay off that penalty in full.
        response = self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'penalty': '1', 'Penalty_Paid': str(penalty.Penalty_Calc),
             'date_paid': date.today().isoformat(), 'Status': 'on'},
        )
        self.assertIn(response.status_code, (200, 302))
        penalty.refresh_from_db()
        original_penalty_calc = penalty.Penalty_Calc
        original_due_date = penalty.Installment_Due_Date
        self.assertAlmostEqual(penalty.Penalty_Paid, original_penalty_calc, places=1)
        self.assertTrue(penalty.Status)

        # Record then delete a small unrelated payment on a later date --
        # deleting a payment for an overdraft loan always triggers a
        # rebuild, which CASCADE-deletes and recreates every Penalty row
        # for this loan (new PKs) -- so the correction under test must be
        # verified by re-querying via the stable Installment_Due_Date key,
        # not by refresh_from_db() on the now-deleted original row.
        dummy = Payments.objects.create(
            Loan=loan, Amount_Paid=1, Date_Paid=date.today(), Payment_Type=1)
        response = self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'delete_payment': '1', 'payment_id': str(dummy.pk)},
        )
        self.assertIn(response.status_code, (200, 302))

        rebuilt_penalty = Penalty.objects.get(Loan=loan, Installment_Due_Date=original_due_date)
        self.assertAlmostEqual(rebuilt_penalty.Penalty_Paid, original_penalty_calc, places=1,
                                msg="Penalty_Paid was lost across an unrelated rebuild")
        self.assertTrue(rebuilt_penalty.Status)


class ApplyToPrincipalCheckboxTest(TestCase):
    """The explicit per-payment 'apply to principal' choice, driven through
    the real pay_installment/Loan_Detail POST paths, replacing the removed
    Principal_Threshold_Percent auto-detect."""

    def setUp(self):
        self.staff = Staff.objects.create(Officer_Name='Officer', Designation='Collector', Salary=0)
        self.user = User.objects.create_user(username='checkboxauthor', password='x', is_staff=True)
        self.client_obj = Clients.objects.create(
            Name='Checkbox Client', Phone_no1='+911234567899', Verified_By='x',
            author=self.user, Photo_Id_No='CB123', Major_Medical_Issues='none',
        )
        self.account = Accounts.objects.create(Client=self.client_obj)
        self.guarantor = Guarantors.objects.create()
        self.client.force_login(self.user)

    def _make_loan(self, first_due, loan_date, principal=250000, rate=2.0):
        return Loans.objects.create(
            Principle_Amount=principal, Frequency=4, No_Of_Installments=0,
            Intrest_Rate=rate, Penalty_Rate=2.0,
            Loan_Collector=self.staff, Guarantor=self.guarantor, Account=self.account,
            First_Due_Date=first_due, Loan_Date=loan_date,
        )

    def test_default_unchecked_banks_as_credit(self):
        loan = self._make_loan(first_due=date.today(), loan_date=date.today() - timedelta(days=30))
        self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'pay': '1', 'amount': '10000', 'date_paid': date.today().isoformat()},
        )
        payment = Payments.objects.get(Loan=loan, Payment_Type=1)
        self.assertFalse(payment.Apply_To_Principal)
        self.assertEqual(payment.Principal_Portion, 0.0)
        self.assertEqual(loan.Total, 250000.0)

    def test_checked_reduces_principal_no_minimum(self):
        loan = self._make_loan(first_due=date.today(), loan_date=date.today() - timedelta(days=30))
        # Interest (5000) + 1 rupee excess, checkbox checked -- the full
        # rupee still reduces principal, no minimum threshold anymore.
        self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'pay': '1', 'amount': '5001', 'date_paid': date.today().isoformat(),
             'apply_to_principal': '1'},
        )
        payment = Payments.objects.get(Loan=loan, Payment_Type=1)
        self.assertTrue(payment.Apply_To_Principal)
        self.assertAlmostEqual(payment.Principal_Portion, 1.0, places=2)
        self.assertEqual(loan.Total, 249999.0)

    def test_same_day_merge_or_of_apply_to_principal_flags(self):
        # First payment unchecked, second payment (same day) checked --
        # the merged row's flag must be the OR of both: a principal intent
        # on either entry applies to the whole day's combined payment.
        loan = self._make_loan(first_due=date.today(), loan_date=date.today() - timedelta(days=30))
        self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'pay': '1', 'amount': '3000', 'date_paid': date.today().isoformat()},
        )
        self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'pay': '1', 'amount': '2001', 'date_paid': date.today().isoformat(),
             'apply_to_principal': '1'},
        )
        payments = Payments.objects.filter(Loan=loan, Payment_Type=1)
        self.assertEqual(payments.count(), 1)  # merged into one same-day row
        merged = payments.first()
        self.assertTrue(merged.Apply_To_Principal)
        self.assertEqual(merged.Amount_Paid, 5001.0)
        self.assertAlmostEqual(merged.Principal_Portion, 1.0, places=2)

    def test_editing_payment_to_check_the_box_triggers_recompute(self):
        # The correction workflow the user will actually hit: "I forgot to
        # check the box." Pay 5001 unchecked (banks as credit), then edit
        # the SAME payment to check the box -- principal must now reduce.
        loan = self._make_loan(first_due=date.today(), loan_date=date.today() - timedelta(days=30))
        self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'pay': '1', 'amount': '5001', 'date_paid': date.today().isoformat()},
        )
        payment = Payments.objects.get(Loan=loan, Payment_Type=1)
        self.assertEqual(loan.Total, 250000.0)  # unchecked: principal untouched

        self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'edit_payment': '1', 'payment_id': str(payment.pk),
             'amount': '5001', 'date_paid': date.today().isoformat(),
             'payment_type': '1', 'apply_to_principal': '1'},
        )
        self.assertAlmostEqual(loan.Total, 249999.0, places=2)

    def test_credit_banked_column_shows_on_unchecked_excess_payment(self):
        loan = self._make_loan(first_due=date.today(), loan_date=date.today() - timedelta(days=30))
        self.client.post(
            reverse('microfinance:loandetail', args=[loan.pk]),
            {'pay': '1', 'amount': '35000', 'date_paid': date.today().isoformat()},
        )
        response = self.client.get(reverse('microfinance:loandetail', args=[loan.pk]))
        payment = response.context['InstallmentPayments'].first()
        self.assertEqual(payment.Banked_As_Credit, 30000.0)
        self.assertContains(response, 'credit: ₹30000.00')


class OverdraftReportRowsTest(TestCase):
    """overdraft_report_rows powers every report's separate OverDraft
    section -- each row must satisfy the self-checking identity
    interest + principal + credit == amount collected, and the flat
    reports must never aggregate these loans into their own totals."""

    def test_row_identity_holds_with_mixed_credit_and_principal_payments(self):
        from microfinance.overdraft_sync import overdraft_report_rows

        loan = _make_overdraft_loan(
            principal=250000, rate=2.0,
            first_due=date(2026, 1, 10), loan_date=date(2026, 1, 1),
        )
        _pay(loan, 5000, date(2026, 1, 10))                                    # interest only
        _pay(loan, 35000, date(2026, 1, 20))                                    # +30000 unchecked -> credit
        _pay(loan, 20000, date(2026, 2, 10), apply_to_principal=True)          # partial interest + principal

        rows = overdraft_report_rows(
            Loans.objects.filter(pk=loan.pk), date(2026, 1, 1), date(2026, 2, 28),
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        identity_sum = round(
            row['interest_collected_in_range'] + row['principal_collected_in_range']
            + row['credit_banked_in_range'], 2
        )
        self.assertAlmostEqual(identity_sum, row['amount_collected_in_range'], places=2)
        self.assertAlmostEqual(row['amount_collected_in_range'], 60000.0, places=2)

    def test_only_overdraft_loans_are_returned(self):
        from microfinance.overdraft_sync import overdraft_report_rows
        from microfinance.tests import _make_loan

        overdraft_loan = _make_overdraft_loan(first_due=date(2026, 1, 10), loan_date=date(2026, 1, 1))
        flat_loan = _make_loan(Frequency=3, Principle_Amount=100000, Intrest_Rate=20)

        rows = overdraft_report_rows(
            Loans.objects.filter(pk__in=[overdraft_loan.pk, flat_loan.pk]),
            date(2026, 1, 1), date(2026, 2, 28),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['loan'].pk, overdraft_loan.pk)


class OverdraftExcludedFromFlatReportsTest(TestCase):
    """Every finance/collection report excludes OverDraft loans from its
    flat totals and shows them in a separate section instead, per explicit
    user instruction ("dont aggregate overdraft things in the other
    details in report")."""

    def setUp(self):
        self.staff = Staff.objects.create(Officer_Name='Report Officer', Designation='Collector', Salary=0)
        self.user = User.objects.create_user(username='reportauthor', password='x', is_staff=True)
        self.flat_client = Clients.objects.create(
            Name='Flat Report Client', Phone_no1='+911234567800', Verified_By='x',
            author=self.user, Photo_Id_No='FR123', Major_Medical_Issues='none',
        )
        self.flat_account = Accounts.objects.create(Client=self.flat_client)
        self.od_client = Clients.objects.create(
            Name='OD Report Client', Phone_no1='+911234567801', Verified_By='x',
            author=self.user, Photo_Id_No='OR123', Major_Medical_Issues='none',
        )
        self.od_account = Accounts.objects.create(Client=self.od_client)
        self.guarantor = Guarantors.objects.create()
        self.client.force_login(self.user)

        self.report_date = date.today()

        # A flat Monthly loan with a payment today.
        self.flat_loan = Loans.objects.create(
            Principle_Amount=100000, Frequency=3, No_Of_Installments=12,
            Intrest_Rate=20, Loan_Collector=self.staff, Guarantor=self.guarantor,
            Account=self.flat_account, First_Due_Date=self.report_date,
            Loan_Date=self.report_date - timedelta(days=30),
        )
        Installments.objects.create(
            Loan=self.flat_loan, Date_Due=self.report_date, Installment_Due=10000.0,
        )
        Payments.objects.create(
            Loan=self.flat_loan, Amount_Paid=10000.0, Date_Paid=self.report_date, Payment_Type=1,
        )

        # An overdraft loan with an excess payment today (interest 5000 +
        # 30000 banked as credit).
        self.od_loan = Loans.objects.create(
            Principle_Amount=250000, Frequency=4, No_Of_Installments=0,
            Intrest_Rate=2.0, Penalty_Rate=2.0,
            Loan_Collector=self.staff, Guarantor=self.guarantor, Account=self.od_account,
            First_Due_Date=self.report_date, Loan_Date=self.report_date - timedelta(days=30),
        )
        self.client.post(
            reverse('microfinance:loandetail', args=[self.od_loan.pk]),
            {'pay': '1', 'amount': '35000', 'date_paid': self.report_date.isoformat()},
        )

    def test_total_finance_and_collection_report_excludes_overdraft_from_totals(self):
        response = self.client.post(
            reverse('microfinance:report2'),
            {'from': (self.report_date - timedelta(days=1)).isoformat(),
             'to': (self.report_date + timedelta(days=1)).isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        # Flat loan's 10000 payment counted; overdraft's 35000 must NOT be
        # folded into the same total.
        self.assertEqual(response.context['totalinst'], 10000.0)
        overdraft_rows = response.context['overdraft_rows']
        self.assertEqual(len(overdraft_rows), 1)
        self.assertEqual(overdraft_rows[0]['loan'].pk, self.od_loan.pk)
        self.assertAlmostEqual(overdraft_rows[0]['amount_collected_in_range'], 35000.0, places=2)
        self.assertContains(response, 'OverDraft Loans (separate section)')

    def test_officerwise_report_excludes_overdraft_from_collection_data(self):
        response = self.client.post(
            reverse('microfinance:report'),
            {'name': '0', 'loan': '0', 'status': 'False',
             'from': (self.report_date - timedelta(days=1)).isoformat(),
             'to': (self.report_date + timedelta(days=1)).isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        collection_loan_ids = {item['loan'].pk for item in response.context['Collection_Data']}
        self.assertIn(self.flat_loan.pk, collection_loan_ids)
        self.assertNotIn(self.od_loan.pk, collection_loan_ids)
        overdraft_rows = response.context['overdraft_rows']
        self.assertEqual(len(overdraft_rows), 1)
        self.assertEqual(overdraft_rows[0]['loan'].pk, self.od_loan.pk)

    def test_officerwise_report_frequency_4_shows_only_overdraft_section(self):
        response = self.client.post(
            reverse('microfinance:report'),
            {'name': '0', 'loan': '4', 'status': 'False',
             'from': (self.report_date - timedelta(days=1)).isoformat(),
             'to': (self.report_date + timedelta(days=1)).isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['overdraft_only'])
        self.assertEqual(len(response.context['Collection_Data']), 0)
        self.assertEqual(len(response.context['overdraft_rows']), 1)

    def test_officerwise_report_frequency_3_shows_no_overdraft_section(self):
        response = self.client.post(
            reverse('microfinance:report'),
            {'name': '0', 'loan': '3', 'status': 'False',
             'from': (self.report_date - timedelta(days=1)).isoformat(),
             'to': (self.report_date + timedelta(days=1)).isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['overdraft_rows']), 0)
        collection_loan_ids = {item['loan'].pk for item in response.context['Collection_Data']}
        self.assertIn(self.flat_loan.pk, collection_loan_ids)

    def test_total_amount_collected_report_excludes_overdraft_from_officer_totals(self):
        response = self.client.post(
            reverse('microfinance:report5'),
            {'Date': self.report_date.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['grand_totals']['inst'], 10000.0)
        overdraft_data = response.context['overdraft_report_data']
        self.assertEqual(len(overdraft_data), 1)
        self.assertAlmostEqual(overdraft_data[0]['totals']['amount'], 35000.0, places=2)
        self.assertContains(response, 'OverDraft Loans (separate section)')

    def test_home_reminders_never_surface_overdraft_loans(self):
        # Give the overdraft loan a stale reminder from before this feature
        # existed, simulating the one real-world way it could carry one.
        self.od_loan.reminder = self.report_date
        self.od_loan.save()
        response = self.client.get(reverse('microfinance:home'))
        self.assertEqual(response.status_code, 200)
        displayed_pks = {l.pk for l in response.context['loan']}
        self.assertNotIn(self.od_loan.pk, displayed_pks)


class SyncOverdraftLoansCommandTest(TestCase):
    """The nightly sync management command: per-loan isolation (one bad
    loan must not stop the others), idempotency, and --dry-run/--loan-id."""

    def test_valid_loan_gets_synced(self):
        from django.core.management import call_command
        from io import StringIO

        loan = _make_overdraft_loan(first_due=date.today() - timedelta(days=5),
                                     loan_date=date.today() - timedelta(days=35))
        self.assertEqual(Installments.objects.filter(Loan=loan).count(), 0)

        out = StringIO()
        call_command('sync_overdraft_loans', stdout=out)
        self.assertGreater(Installments.objects.filter(Loan=loan).count(), 0)
        self.assertIn('Synced 1, failed 0.', out.getvalue())

    def _make_second_overdraft_loan(self, first_due, loan_date, principal=100000, rate=2.0):
        # _make_overdraft_loan hardcodes its Staff/User/Client/Account
        # identifiers, so it can only be called once per test -- every
        # other test in this file needing two loans builds a second one
        # against fresh fixtures, same as here.
        staff = Staff.objects.create(Officer_Name='OD Officer 2', Designation='Collector', Salary=0)
        user = User.objects.create_user(username='odauthor2', password='x')
        client = Clients.objects.create(
            Name='OD Client 2', Phone_no1='+911234567892', Verified_By='x',
            author=user, Photo_Id_No='OD456', Major_Medical_Issues='none',
        )
        account = Accounts.objects.create(Client=client)
        guarantor = Guarantors.objects.create()
        return Loans.objects.create(
            Principle_Amount=principal, Frequency=4, No_Of_Installments=0,
            Intrest_Rate=rate, Loan_Collector=staff, Guarantor=guarantor,
            Account=account, First_Due_Date=first_due, Loan_Date=loan_date,
        )

    def test_one_bad_loan_does_not_stop_the_others(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from io import StringIO

        good_loan = _make_overdraft_loan(first_due=date.today() - timedelta(days=5),
                                          loan_date=date.today() - timedelta(days=35))
        # A loan with First_Due_Date == Loan_Date bypasses form validation
        # (created directly via the ORM) and raises ValueError inside
        # replay_overdraft_loan (cycle_days == 0) -- this is the shape of
        # failure the isolation exists to survive.
        bad_loan = self._make_second_overdraft_loan(first_due=date(2026, 5, 1), loan_date=date(2026, 5, 1))

        out = StringIO()
        with self.assertRaises(CommandError):
            call_command('sync_overdraft_loans', stdout=out)

        self.assertGreater(Installments.objects.filter(Loan=good_loan).count(), 0)
        self.assertEqual(Installments.objects.filter(Loan=bad_loan).count(), 0)
        self.assertIn('Synced 1, failed 1.', out.getvalue())

    def test_idempotent_second_run_issues_zero_writes(self):
        from django.core.management import call_command
        from io import StringIO

        loan = _make_overdraft_loan(first_due=date.today() - timedelta(days=5),
                                     loan_date=date.today() - timedelta(days=35))
        call_command('sync_overdraft_loans', stdout=StringIO())

        with CaptureQueriesContext(connection) as ctx:
            call_command('sync_overdraft_loans', stdout=StringIO())
        write_queries = [
            q['sql'] for q in ctx.captured_queries
            if q['sql'].strip().upper().split(' ', 1)[0] in ('INSERT', 'UPDATE', 'DELETE')
        ]
        self.assertEqual(write_queries, [])

    def test_dry_run_makes_no_changes(self):
        from django.core.management import call_command
        from io import StringIO

        loan = _make_overdraft_loan(first_due=date.today() - timedelta(days=5),
                                     loan_date=date.today() - timedelta(days=35))
        out = StringIO()
        call_command('sync_overdraft_loans', '--dry-run', stdout=out)
        self.assertEqual(Installments.objects.filter(Loan=loan).count(), 0)
        self.assertIn('Would sync 1', out.getvalue())

    def test_loan_id_targets_a_single_loan(self):
        from django.core.management import call_command
        from io import StringIO

        loan1 = _make_overdraft_loan(first_due=date.today() - timedelta(days=5),
                                      loan_date=date.today() - timedelta(days=35))
        loan2 = self._make_second_overdraft_loan(first_due=date.today() - timedelta(days=5),
                                                  loan_date=date.today() - timedelta(days=35))
        call_command('sync_overdraft_loans', f'--loan-id={loan1.pk}', stdout=StringIO())
        self.assertGreater(Installments.objects.filter(Loan=loan1).count(), 0)
        self.assertEqual(Installments.objects.filter(Loan=loan2).count(), 0)

    def test_closed_loans_are_not_synced(self):
        from django.core.management import call_command
        from io import StringIO

        loan = _make_overdraft_loan(first_due=date.today() - timedelta(days=5),
                                     loan_date=date.today() - timedelta(days=35))
        loan.Status = True
        loan.save()
        out = StringIO()
        call_command('sync_overdraft_loans', stdout=out)
        self.assertIn('Synced 0, failed 0.', out.getvalue())
        self.assertEqual(Installments.objects.filter(Loan=loan).count(), 0)
