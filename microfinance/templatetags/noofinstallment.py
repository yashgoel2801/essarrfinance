from django import template
register = template.Library()
@register.filter
def noofinstallment(value):  
    if value.Frequency==2 :
        if value.No_Of_Installments%7!=0:
            return int(value.No_Of_Installments/7) + 1
        else: 
            return int(value.No_Of_Installments/7)
    else:
        return value.No_Of_Installments
        

