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
    existing_client = forms.ModelChoiceField(
        queryset=models.Clients.objects.all().order_by('Name'),
        required=False,
        empty_label="Select existing client to pre-populate (optional)",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'existing-client-select'})
    )

    class Meta:
        model=models.Clients
        exclude = ['ClientUser'] 
        widgets = {
            'Date_Added': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'Name': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_name'}),
            'Father_Name': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_father_name'}),
            'Mother_Name': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_mother_name'}),
            'Husband_Name': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_husband_name'}),
            'Wife_Name': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_wife_name'}),
            'Local_Address': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_local_address'}),
            'Permanent_Address': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_permanent_address'}),
            'Occupation': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_occupation'}),
            'Office_Address': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_office_address'}),
            'Designation': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_designation'}),
            'Reference_Name': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_reference_name'}),
            'Verified_By': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_verified_by'}),
            'Photo_Id_No': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_photo_id_no'}),
            'Major_Medical_Issues': forms.Textarea(attrs={'class': 'form-control', 'id': 'id_major_medical_issues'}),
            'author': forms.Select(attrs={'class': 'form-select', 'id': 'id_author'}),
            'Photo_Id': forms.Select(attrs={'class': 'form-select', 'id': 'id_photo_id'}),
            'Image': forms.FileInput(attrs={'class': 'form-control', 'id': 'id_image'}),
            'Phone_no1': PhoneWidget(attrs={'class': 'form-control', 'id': 'id_phone_no1'}),
            'Phone_no2': PhoneWidget(attrs={'class': 'form-control', 'id': 'id_phone_no2'}),
            'Reference_No': PhoneWidget(attrs={'class': 'form-control', 'id': 'id_reference_no'}),

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

class GuarantorSelectionForm(forms.Form):
    guarantor_choice = forms.ChoiceField(
        choices=[
            ('new', 'Create New Guarantor'),
            ('existing', 'Use Existing Guarantor'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial='new'
    )
    existing_guarantor = forms.ModelChoiceField(
        queryset=models.Guarantors.objects.all().order_by('Guarantor_Name'),
        required=False,
        empty_label="Select existing guarantor",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'existing-guarantor-select'})
    )
        

class AddGuarantorDocs(forms.ModelForm):
    class Meta:
        model=models.Guarantor_Documents
        fields= ['Image']
        
class AddExpenditures(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(AddExpenditures, self).__init__(*args, **kwargs)
        from .models import ExpenseCategory
        try:
            categories = list(ExpenseCategory.objects.all().values_list('name', 'name'))
            self.fields['Category'] = forms.ChoiceField(
                choices=categories, 
                widget=forms.Select(attrs={'class': 'form-select', 'id': 'category_select'})
            )
        except Exception:
            pass # handle migration cases

    class Meta:
        model=models.Expenditures
        fields= '__all__'
        widgets = {
            'Date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            # Category widget is handled in __init__
            'Amount': forms.NumberInput(attrs={'class': 'form-control', 'placehoder': 'Enter Amount'}),
            'To': forms.Select(attrs={'class': 'form-select'}),
            'From': forms.Select(attrs={'class': 'form-select'}),
            'Remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional remarks'}),
        }
        labels = {
            'To': 'Paid To (Officer/Payee)',
            'From': 'Paid By (Source)',
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
        widgets = {
            'Loan_Date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'First_Due_Date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Format dates for HTML5 date input (yyyy-MM-dd)
        if self.instance and self.instance.pk:
            if self.instance.Loan_Date:
                self.initial['Loan_Date'] = self.instance.Loan_Date.strftime('%Y-%m-%d')
            if self.instance.First_Due_Date:
                self.initial['First_Due_Date'] = self.instance.First_Due_Date.strftime('%Y-%m-%d')

class EditInstallmentDetail(forms.ModelForm):
    class Meta:
        model=models.Installments
        fields=['Loan','Date_Due','Date_Paid','Installment_Due','Installment_Paid','Installment_To_Be_Paid','Pending_Amount']

class AddInstallments(forms.ModelForm):
    class Meta:
        model=models.Installments
        fields=['Date_Due','Date_Paid','Installment_Due','Installment_Paid','Installment_To_Be_Paid','Pending_Amount']
