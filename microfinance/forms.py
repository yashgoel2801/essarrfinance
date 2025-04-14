from django import forms
from . import models

from django.forms import ModelForm

class AddStaff(forms.ModelForm):
    class Meta:
        model=models.Staff
        fields=['Officer_Name','Designation','Salary']


class AddClient(forms.ModelForm):
    class Meta:
        model=models.Clients
        fields= '__all__'
        widgets = {
            'Date_Added': forms.DateInput(attrs={'type': 'date'})
        }


class AddDocs(forms.ModelForm):
    class Meta:
        model=models.Documents
        fields= ['Image']

class AddLoan(forms.ModelForm):
    class Meta:
        model=models.Loans
        fields= ['AccNo','Principle_Amount','Frequency','Purpose','No_Of_Installments','Intrest_Rate','File_Charge_Percent','First_Due_Date','Loan_Date','Loan_Collector','security_docs']
        widgets = {
            'First_Due_Date': forms.DateInput(attrs={'type': 'date'}),
            'Loan_Date': forms.DateInput(attrs={'type': 'date'})
        }

class AddGuarantor(forms.ModelForm):
    class Meta:
        model=models.Guarantors
        fields= '__all__'
        

class AddGuarantorDocs(forms.ModelForm):
    class Meta:
        model=models.Guarantor_Documents
        fields= ['Image']
        
class AddExpenditures(forms.ModelForm):
    class Meta:
        model=models.Expenditures
        fields= '__all__'
        widgets = {
            'Date': forms.DateInput(attrs={'type': 'date'})
        }


class EditClientDetail(forms.ModelForm):
    class Meta:
        model=models.Clients
        fields=['Image','Local_Address','Permanent_Address','Occupation','Office_Address','Father_Name','Mother_Name','Phone_no2','Reference_Name','Reference_No']

class AddPenalty(forms.ModelForm):
    class Meta:
        model=models.Penalty
        fields = ['Status','Penalty_Paid']

class ClientSearchForm(forms.Form):
    search_name =  forms.CharField(
                    required = False,
                    label='Search By name',
                    widget=forms.TextInput(attrs={'placeholder': 'search here!'})
                  )

    search_id = forms.IntegerField(
                    required = False,
                    label='Search By Client Id:'
                  )           
    search_phone = forms.CharField(
                    required=False,
                    label= 'Search by Phone no'
                  )


class EditLoanDetail(forms.ModelForm):
    class Meta:
        model=models.Loans
        fields=['Principle_Amount','Frequency','Purpose','No_Of_Installments','Intrest_Rate','File_Charge_Percent','Loan_Date','First_Due_Date','Loan_Collector']

class EditInstallmentDetail(forms.ModelForm):
    class Meta:
        model=models.Installments
        fields=['Loan','Date_Due','Date_Paid','Installment_Due','Installment_Paid','Installment_To_Be_Paid','Pending_Amount']

class AddInstallments(forms.ModelForm):
    class Meta:
        model=models.Installments
        fields=['Date_Due','Date_Paid','Installment_Due','Installment_Paid','Installment_To_Be_Paid','Pending_Amount']
