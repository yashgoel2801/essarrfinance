from django import template
register = template.Library()
@register.filter
def lastpaid(value):  
    try: 
        return value.filter(Date_Paid__isnull =False).exclude(Installment_Paid = 0).order_by('-Date_Paid','-Installment_Paid').first().Date_Paid    
    except AttributeError:
        return '-'
