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
