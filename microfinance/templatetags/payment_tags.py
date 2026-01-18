from django import template
from microfinance.models import Payments

register = template.Library()

@register.simple_tag
def last_payment_date(loan):
    try:
        payment = Payments.objects.filter(Loan=loan, Payment_Type=1).exclude(Amount_Paid=0).order_by('-Date_Paid').first()
        return payment.Date_Paid if payment else '-'
    except:
        return '-'

@register.simple_tag
def last_payment_amount(loan):
    try:
        payment = Payments.objects.filter(Loan=loan, Payment_Type=1).exclude(Amount_Paid=0).order_by('-Date_Paid').first()
        return payment.Amount_Paid if payment else 0
    except:
        return 0
