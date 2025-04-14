from django.db import models
from django.utils import timezone
from datetime import datetime, timedelta
from django import forms
from django.utils.text import slugify
from django.db.models.signals import pre_save
from phone_field import PhoneField
from essarrfinance.utils import unique_slug_generator
from django.core.validators import MaxValueValidator, MinValueValidator
from PIL import Image
from django.contrib.auth.models import User,Permission



# Create your models here.
class Staff(models.Model):
    Officer_Name = models.CharField(max_length=100)
    Designation = models.CharField(max_length=100)
    Salary = models.FloatField()
    def save(self, force_insert=False, force_update=False,*args,**kawgrs):
        self.Officer_Name = self.Officer_Name.upper()
        self.Designation = self.Designation.upper()
        super(Staff, self).save(force_insert, force_update,*args,**kawgrs)    

    def __str__(self):
        return self.Officer_Name

class Expenditures(models.Model):
    Amount = models.FloatField()
    To = models.ForeignKey(Staff,related_name='to',default=1,on_delete=models.PROTECT)
    From = models.ForeignKey(Staff,related_name='by',default=1,on_delete=models.PROTECT)
    Date = models.DateField(default=timezone.now)
    Remark = models.TextField(blank=True)    


LOAN_CHOICES = (
   (1, 'Daily'),
   (2, 'Weekly'),
   (3,'Monthly'),
   (3,'OverDraft'),
)
LOAN_ON_CHOICES = (
   ('c', 'Cash Loan'),
   ('p', 'Property Loan'),
   ('v', 'Vehicle Loan'),
   ('g','Gold Loan')
 
)

Photo_ID = (
   ('aadhar', 'aadhar card'),
   ('pan', 'pan card'),
   ('voter', 'Voter ID card'),
   ('passport', 'Passport'),
)
class Clients(models.Model):
    ClientUser = models.ForeignKey(User, on_delete=models.CASCADE,related_name='logged_in_client',null=True)
    Name = models.CharField(max_length=100)
    Image = models.ImageField(upload_to='pics',default='pics/avatar.png')
    Father_Name = models.CharField(max_length=100,default='')
    Husband_Name = models.CharField(max_length=100,default='')
    Mother_Name = models.CharField(max_length=100,default='')
    Wife_Name = models.CharField(max_length=100,default='')
    Local_Address= models.CharField(max_length=200,default='')
    Permanent_Address= models.CharField(max_length=200,default='')
    Occupation = models.CharField(max_length=100,default='')
    Designation = models.CharField(max_length=100,default='')
    Office_Address= models.CharField(max_length=200,default='')
    Phone_no1 = PhoneField(unique=True)
    Phone_no2= PhoneField(null=True,blank=True)
    Reference_Name = models.CharField(max_length=100,default='')
    Reference_No = PhoneField(null=True,blank=True)
    Verified_By = models.CharField(max_length=100,blank=False)  
    Date_Added =  models.DateField(default=timezone.now)    
    author=models.ForeignKey(User, on_delete=models.PROTECT,default= None)
    Photo_Id = models.CharField(max_length=100,choices=Photo_ID,default='aadhar')
    Photo_Id_No = models.CharField(max_length=100,blank=False,unique=True)
    Major_Medical_Issues = models.CharField(max_length=100,default=None)
    class Meta:
        permissions = [
            ("client_view", "Can view sensitive client data")
        ] 

    def __str__(self):
       return self.Name+" - "+str(self.pk)
    def save(self, force_insert=False, force_update=False,*args,**kawgrs):
        self.Name = self.Name.upper()
        self.Photo_Id_No = self.Photo_Id_No.upper()
        permissions = Permission.objects.get(codename='view_client')
        user = User.objects.create_user(
            username=self.Phone_no1,
            password=self.Name[:4]+self.Photo_Id_No[-4:],
        )
        user.user_permissions.add(permissions)
        user.save()
        self.ClientUser_id = user.pk
        super(Clients, self).save(force_insert, force_update,*args, **kawgrs)      



class Documents(models.Model):
    Image = models.ImageField(upload_to='documents',blank=True)
    Client = models.ForeignKey(Clients,on_delete=models.PROTECT)


class Accounts(models.Model):
    Date_Created = models.DateField(default = timezone.now)
    Client = models.ForeignKey(Clients,on_delete=models.PROTECT)
    @classmethod
    def create_account(cls, new_account):         
       Accounts.save(new_account)  


class Guarantors(models.Model):
    Guarantor_Name = models.CharField(max_length=100,default='not specified')
    Image = models.ImageField(upload_to='Guarantor',default='pics/avatar.png')
    Guarantor_Father_Name = models.CharField(max_length=100,default='not specified')
    Guarantor_Mother_Name = models.CharField(max_length=100,default='not specified')
    Guarantor_Local_Address= models.CharField(max_length=200,default='not specified')
    Guarantor_Permanent_Address= models.CharField(max_length=200,default='not specified')
    Guarantor_Occupation = models.CharField(max_length=100,default='not specified')
    Guarantor_Designation = models.CharField(max_length=100,default='not specified')
    Guarantor_Office_Address= models.CharField(max_length=200,default='not specified')
    Guarantor_Phone_no=PhoneField()
    Guarantor_Phone_no2= PhoneField(null=True,blank=True)    
    Guarantor_Security_Docs= models.TextField(default='not specified')
    def __str__(self):
       return "Guarnator ID:"+str(self.pk)


class Guarantor_Documents(models.Model):
    Image = models.ImageField(upload_to='Guarantor_Documents',blank=True)
    Guarantor = models.ForeignKey(Guarantors,on_delete=models.PROTECT)
    def __str__(self):
       return "Guarnator ID: "+str(self.Guarantor.pk)

class Loans(models.Model):
    Principle_Amount = models.FloatField()
    Frequency = models.IntegerField(choices=LOAN_CHOICES,default=1)
    AccNo = models.IntegerField(default=0)
    Purpose = models.CharField(choices=LOAN_ON_CHOICES,max_length=100, default='c')
    No_Of_Installments = models.IntegerField(default=0)
    Intrest_Rate = models.FloatField(default=20)
    File_Charge_Percent =models.FloatField(default=5)
    First_Due_Date =  models.DateField(default=timezone.now)
    Loan_Date = models.DateField(default=timezone.now)
    Loan_Collector = models.ForeignKey(Staff, on_delete=models.PROTECT,default= 1)
    Guarantor = models.ForeignKey(Guarantors,on_delete=models.PROTECT,default = 0)
    Account = models.ForeignKey(Accounts,on_delete=models.PROTECT,default = 0)
    Status =models.BooleanField(default=False)
    remark = models.CharField(max_length=100,default='None')
    reminder = models.DateField(default=datetime.now(),blank=True,null=True)
    security_docs= models.TextField(default='not specified')
    def __str__(self):
       return "Loan ID: "+str(self.pk)
    def _get_total_amnt_to_collect(self):
        return self.Principle_Amount + (self.Principle_Amount * self.Intrest_Rate/100 )      
    Total = property(_get_total_amnt_to_collect)



class Installments(models.Model):
    Loan=models.ForeignKey(Loans,on_delete=models.PROTECT,default=0)
    Date_Due = models.DateField(default=timezone.now)
    Date_Paid = models.DateField(default=None, null=True,blank=True)
    Installment_Due = models.FloatField(default=0)
    Installment_Paid = models.FloatField(default=0)
    Installment_To_Be_Paid = models.FloatField(default=0)
    Pending_Amount = models.FloatField(default=0)
    def __str__(self):
       return str(self.Date_Due) +" - "+str(self.Date_Due)+ " - "+str(self.Loan.pk)  
    class Meta:
        ordering = ['Loan_id','Date_Due','-Installment_Due']

     
    @classmethod
    def create_dates(cls, new_loanee):         
       Installments.save(new_loanee)  

class Penalty(models.Model):
    Loan=models.ForeignKey(Loans,on_delete=models.PROTECT,default=0)
    Installment = models.ForeignKey(Installments,on_delete=models.PROTECT,default =0)
    Date_Started = models.DateField(default=None)
    Date_Ended = models.DateField(default = None,null=True)
    Amount = models.FloatField(default = 0)
    Percent = models.FloatField(default=2)
    Penalty_Calc = models.FloatField(default=0)
    Penalty_Paid =models.FloatField(default=0)
    Penalty_Paid_Date= models.DateField(default=None,null=True)
    Status = models.BooleanField(default=False)

    def __str__(self):
       return str(self.Date_Started) +" - "+str(self.Loan.pk)  
    class Meta:
        ordering = ['Loan_id','Date_Started']


PAYMENT_TYPE = (
   (1, 'installment'),
   (2, 'penalty')
)

class Payments(models.Model):
    Loan=models.ForeignKey(Loans,on_delete=models.PROTECT,default=0)
    Date_Paid = models.DateField(default=None, null=True,blank=True)
    Amount_Paid = models.FloatField(default=0)
    Payment_Type =models.IntegerField(choices=PAYMENT_TYPE,default=1)
    def __str__(self):
       return str(self.Date_Paid) +" - "+str(self.Amount_Paid)+ " - "+str(self.Loan.pk)  
    class Meta:
        ordering = ['Loan_id','Date_Paid']












