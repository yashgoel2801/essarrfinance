from django import template
from microfinance.models import Payments
from django.utils.safestring import mark_safe

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

@register.simple_tag
def last_payment_info(loan):
    """Returns HTML formatted payment info with amount, penalty, and date stacked"""
    try:
        # Get last installment payment
        payment = Payments.objects.filter(Loan=loan, Payment_Type=1).exclude(Amount_Paid=0).order_by('-Date_Paid').first()
        
        # Get last penalty payment on the same date if exists
        penalty_payment = None
        if payment:
            penalty_payment = Payments.objects.filter(
                Loan=loan, 
                Payment_Type=2, 
                Date_Paid=payment.Date_Paid
            ).exclude(Amount_Paid=0).first()
        
        if payment:
            html = f'<span style="font-weight: bold; color: #28a745;">₹{int(payment.Amount_Paid)}</span>'
            
            if penalty_payment and penalty_payment.Amount_Paid > 0:
                html += f'<br><span style="font-size: 0.75rem; color: #dc3545;">+ Pen: ₹{int(penalty_payment.Amount_Paid)}</span>'
            
            html += f'<br><span style="font-size: 0.75rem; color: #6c757d;">Last: {payment.Date_Paid.strftime("%b %d")}</span>'
            
            return mark_safe(html)
        else:
            return mark_safe('<span style="font-size: 0.875rem; color: #6c757d;">No Pay</span>')
    except Exception as e:
        return mark_safe('<span style="font-size: 0.875rem; color: #6c757d;">-</span>')
