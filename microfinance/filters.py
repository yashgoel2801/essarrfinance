from django.contrib.auth.models import User
import django_filters
from . import models

class LoanFilter(django_filters.FilterSet):
    class Meta:
        model = models.Loans
        fields = ['Loan_Collector',]
    
