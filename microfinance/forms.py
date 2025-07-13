from django import forms
from .import models
from phone_field.forms import PhoneWidget

from django.forms import ModelForm
from phone_field.forms import PhoneFormField


class AddStaff(forms.ModelForm):
    class Meta:
        model=models.Staff
        fields=['Officer_Name','Designation','Salary']


class AddClient(forms.ModelForm):
    Phone_no1 = PhoneFormField()
    Phone_no2 = PhoneFormField(required=False)
    Reference_No = PhoneFormField(required=False)

    class Meta:
        model=models.Clients
        exclude = ['ClientUser'] 
        widgets = {
            'Date_Added': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'Name': forms.TextInput(attrs={'class': 'form-control'}),
            'Father_Name': forms.TextInput(attrs={'class': 'form-control'}),
            'Mother_Name': forms.TextInput(attrs={'class': 'form-control'}),
            'Husband_Name': forms.TextInput(attrs={'class': 'form-control'}),
            'Wife_Name': forms.TextInput(attrs={'class': 'form-control'}),
            'Local_Address': forms.TextInput(attrs={'class': 'form-control'}),
            'Permanent_Address': forms.TextInput(attrs={'class': 'form-control'}),
            'Occupation': forms.TextInput(attrs={'class': 'form-control'}),
            'Office_Address': forms.TextInput(attrs={'class': 'form-control'}),
            'Designation': forms.TextInput(attrs={'class': 'form-control'}),
            'Reference_Name': forms.TextInput(attrs={'class': 'form-control'}),
            'Verified_By': forms.TextInput(attrs={'class': 'form-control'}),
            'Photo_Id_No': forms.TextInput(attrs={'class': 'form-control'}),
            'Major_Medical_Issues': forms.Textarea(attrs={'class': 'form-control'}),
            'Author': forms.Select(attrs={'class': 'form-select'}),
            'Photo_Id': forms.Select(attrs={'class': 'form-select'}),
            'Image': forms.FileInput(attrs={'class': 'form-control'}),
            'Phone_no1': PhoneWidget(attrs={'class': 'form-control'}),
            'Phone_no2': PhoneWidget(attrs={'class': 'form-control'}),
            'Reference_No': PhoneWidget(attrs={'class': 'form-control'}),

        }


class AddDocs(forms.ModelForm):
    class Meta:
        model=models.Documents
        fields= ['Image']

class AddLoan(forms.ModelForm):
    class Meta:
        model=models.Loans
        fields= ['AccNo','Principle_Amount','Frequency','Purpose','No_Of_Installments','Intrest_Rate','File_Charge_Percent','First_Due_Date','Loan_Date','Loan_Collector','Security_Docs']
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
