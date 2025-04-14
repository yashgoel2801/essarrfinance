from django import template
register = template.Library()
@register.filter
def lastamntpaid(value):  
    try: 
        return value.filter(Date_Paid__isnull =False).exclude(Installment_Paid = 0).order_by('-Date_Paid','-Installment_Paid').first().Installment_Paid    
    except AttributeError:
        return '-'
