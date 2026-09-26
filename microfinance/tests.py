from django.test import TestCase
from microfinance.models import Loans, Payments, LOAN_CHOICES, Staff, Guarantors, Accounts, Clients, Penalty, Installments
from django.contrib.auth.models import User
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from microfinance.views import _calculate_individual_installment_penalties


class OverdraftFieldsTest(TestCase):
    def test_loan_choices_has_no_duplicate_values(self):
        values = [v for v, _ in LOAN_CHOICES]
        self.assertEqual(len(values), len(set(values)),
                          "LOAN_CHOICES must not have duplicate integer values")

    def test_loan_choices_has_distinct_overdraft_value(self):
        self.assertIn((4, 'OverDraft'), LOAN_CHOICES)

    def test_loans_has_penalty_rate_field(self):
        field_names = {f.name for f in Loans._meta.get_fields()}
        self.assertIn('Penalty_Rate', field_names)

    def test_penalty_rate_is_nullable(self):
        penalty_field = Loans._meta.get_field('Penalty_Rate')
        self.assertTrue(penalty_field.null)

    def test_payments_has_principal_and_interest_portion_fields(self):
        field_names = {f.name for f in Payments._meta.get_fields()}
        self.assertIn('Principal_Portion', field_names)
        self.assertIn('Interest_Portion', field_names)

    def test_principal_and_interest_portion_default_to_zero(self):
        principal_field = Payments._meta.get_field('Principal_Portion')
        interest_field = Payments._meta.get_field('Interest_Portion')
        self.assertEqual(principal_field.default, 0)
        self.assertEqual(interest_field.default, 0)

    def test_payments_has_apply_to_principal_field_defaulting_false(self):
        field_names = {f.name for f in Payments._meta.get_fields()}
        self.assertIn('Apply_To_Principal', field_names)
        field = Payments._meta.get_field('Apply_To_Principal')
        self.assertEqual(field.default, False)


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
    loan = Loans.objects.create(**defaults)
    # Create a test installment
    Installments.objects.create(
        Loan=loan,
        Date_Due=date(2026, 1, 10),
        Installment_Due=1000.0,
    )
    return loan


class PenaltyRateConfigurationTest(TestCase):
    def test_default_penalty_rate_unchanged_when_not_set(self):
        loan = _make_loan(Penalty_Rate=None)
        inst = Installments.objects.filter(Loan=loan).first()
        installments = [{'id': inst.id, 'Date_Due': date(2026, 1, 10), 'Installment_Due': 1000.0}]
        payments = []
        today = date(2026, 1, 20)
        result = _calculate_individual_installment_penalties(loan, installments, payments, today)
        # 10 days overdue, amount 1000, default rate 2%/day = 1000 * 0.02 * 10 = 200
        self.assertEqual(result['total_penalty'], Decimal('200'))

    def test_custom_penalty_rate_applied_when_set(self):
        loan = _make_loan(Penalty_Rate=5.0)
        inst = Installments.objects.filter(Loan=loan).first()
        installments = [{'id': inst.id, 'Date_Due': date(2026, 1, 10), 'Installment_Due': 1000.0}]
        payments = []
        today = date(2026, 1, 20)
        result = _calculate_individual_installment_penalties(loan, installments, payments, today)
        # 10 days overdue, amount 1000, custom rate 5%/day = 1000 * 0.05 * 10 = 500
        self.assertEqual(result['total_penalty'], Decimal('500'))

    def test_penalty_rows_record_the_applied_rate(self):
        loan = _make_loan(Penalty_Rate=3.0)
        inst = Installments.objects.filter(Loan=loan).first()
        installments = [{'id': inst.id, 'Date_Due': date(2026, 1, 10), 'Installment_Due': 1000.0}]
        payments = []
        today = date(2026, 1, 20)
        _calculate_individual_installment_penalties(loan, installments, payments, today)
        penalty_row = Penalty.objects.filter(Loan=loan).first()
        self.assertEqual(penalty_row.Percent, Decimal('3'))
