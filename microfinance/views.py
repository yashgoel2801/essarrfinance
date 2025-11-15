from decimal import Decimal
from django.shortcuts import render,redirect, get_object_or_404
from .import forms
from .forms import AddExpenditures,AddGuarantor,AddStaff,AddClient,AddDocs,AddLoan,AddGuarantorDocs,EditClientDetail,EditLoanDetail,EditInstallmentDetail,AddInstallments
from .forms import ClientSearchForm
from .models import *
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from datetime import datetime, time, timedelta,date
from dateutil.relativedelta import relativedelta
from search_views.search import SearchListView,BaseFilter
from django.utils.dateparse import parse_date
from django.db.models import Q,Sum, Count
from django.template import loader
from datetime import date
from datetime import datetime
from django.contrib.auth.models import Permission
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone

import requests
import json
# from twilio.rest import Client as twilioClient
from .filters import LoanFilter
from PIL import Image
from django.core.files.uploadedfile import InMemoryUploadedFile
from io import BytesIO
URL = 'https://www.sms4india.com/api/v1/sendCampaign'
# get request
def sendPostRequest(reqUrl, apiKey, secretKey, useType, phoneNo, senderId, textMessage):
  req_params = {
  'apikey':apiKey,
  'secret':secretKey,
  'usetype':useType,
  'phone': phoneNo,
  'message':textMessage,
  'senderid':senderId
  }
  return requests.post(reqUrl, req_params)

# Create your views here.
@login_required(login_url="/accounts/login/")
def Add_Officer(request):
    if request.method == 'POST':
        form=AddStaff(request.POST,request.FILES)
        if form.is_valid():
            form.save()
    else: 
        form=AddStaff()     
    return render(request,'microfinance/Add_Officer.html',{'form':form})

@login_required(login_url="/accounts/login/")
def Add_Client(request):
    
    Today = datetime.now()
    if request.method == 'POST':
        print(request.POST)
        form=AddClient(request.POST,request.FILES)
        
        if form.is_valid():
            instance=form.save(commit=False)
            newobj = Accounts(Client=instance)
            permissions = Permission.objects.get(codename='client_view')
            username = form.cleaned_data['Phone_no1']
            password = instance.Name[:4]+ form.cleaned_data['Photo_Id_No'][-4:]
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(
                    username=username,
                    password=password,
                )
                user.user_permissions.add(permissions)
            # Link the user to the client
            instance.ClientUser = user
            instance.author = request.user # Set the author to the current user
            instance.save()
            newobj.save()
            return redirect('microfinance:adddocs', pk=instance.pk)
        print(form.errors)
        return render(request,'microfinance/Add_Client.html',{'Today':Today,'form':form})
    
    else: 
        form =AddClient()
        return render(request,'microfinance/Add_Client.html',{'Today':Today,'form':form})

@login_required(login_url="/accounts/login/")
def Add_Docs(request,pk):
    if request.method == 'POST':
        form=AddDocs(request.POST,request.FILES)
        if form.is_valid():
            instance=form.save(commit=False)
            instance.Client_id = pk
            instance.save()
            if 'm' in request.POST:
                return redirect('microfinance:adddocs', pk=pk)
            if 'n' in request.POST:
                return redirect('microfinance:addguarantor', pk=pk)
    else: 
        form=AddDocs()     
    return render(request,'microfinance/Add_Docs.html',{'form':form})

@login_required(login_url="/accounts/login/")
def Add_Loan(request,pk, sk):
    if request.method == 'POST':
        form=AddLoan(request.POST,request.FILES)
        if form.is_valid():
            instance=form.save(commit=False)
            client =Clients.objects.get(pk=pk)
            acc = Accounts.objects.get(Client=client)
            instance.Account =acc
            instance.Guarantor_id = sk
            instance.save()
            Installment = (instance.Principle_Amount + (instance.Principle_Amount/100*instance.Intrest_Rate))/instance.No_Of_Installments
            if instance.Frequency !=2 :
                Inst = round(Installment,1)
                Installments_Inst = Installments(Installment_Paid = 0, Loan = instance, Date_Due = instance.First_Due_Date, Installment_Due = Inst,Installment_To_Be_Paid=Inst,Pending_Amount=Inst )
            else:
                Inst = round(Installment,1)
                Installments_Inst = Installments(Installment_Paid = 0, Loan = instance, Date_Due = instance.First_Due_Date, Installment_Due = round(Inst*7),Installment_To_Be_Paid=round(Inst*7),Pending_Amount=round(Inst*7) )
            Installments_Inst.save()   
            
            if instance.Frequency == 1:
                Date_Due = instance.First_Due_Date 
                for i in range(1,instance.No_Of_Installments):
                    Inst = round(Installment,1)
                    Date_Due = Date_Due + timedelta(1)
                    Installments_Inst = Installments(Installment_Paid = 0, Loan = instance,Date_Due = Date_Due, Installment_Due = round(Installment,1),Installment_To_Be_Paid=round(Installment,1),Pending_Amount=round(Installment,1))
                    Installments_Inst.save()
            if instance.Frequency == 2:
                Date_Due = instance.First_Due_Date 
                Extra_Days = instance.No_Of_Installments % 7
                for i in range(1,int(instance.No_Of_Installments/7)):                
                    Inst = Installment                
                    Date_Due = Date_Due + timedelta(7)
                    Installments_Inst = Installments(Installment_Paid = 0, Loan = instance, Date_Due = Date_Due, Installment_Due = round(Inst*7),Installment_To_Be_Paid=round(Inst*7),Pending_Amount=round(Inst*7))
                    Installments_Inst.save()
                if Extra_Days>0:
                    Inst = Installment
                    Date_Due = Date_Due + timedelta(Extra_Days)
                    Installments_Inst = Installments(Installment_Paid = 0, Loan = instance,Date_Due = Date_Due, Installment_Due = round(Inst*Extra_Days),Installment_To_Be_Paid=round(Inst*Extra_Days),Pending_Amount=round(Inst *Extra_Days))
                    Installments_Inst.save()
            if instance.Frequency == 3:
                Date_Due = instance.First_Due_Date 
                for i in range(1,int(instance.No_Of_Installments)):
                    Inst = round(Installment,1)
                    Date_Due = Date_Due + relativedelta(months=1)
                    Installments_Inst = Installments(Installment_Paid = 0, Loan = instance,Date_Due = Date_Due, Installment_Due = round(Installment,1),Installment_To_Be_Paid=round(Installment,1),Pending_Amount=round(Installment,1) )
                    Installments_Inst.save()
            return redirect('microfinance:clientdetail' ,pk=pk)
        else:
            # Form is not valid, show errors
            return render(request,'microfinance/Add_Loan.html',{'form':form})
    else: 
        form=AddLoan()     
    return render(request,'microfinance/Add_Loan.html',{'form':form})

@login_required(login_url="/accounts/login/")
def Add_Guarantor(request,pk):
    if request.method == 'POST':
        form=AddGuarantor(request.POST,request.FILES)
        if form.is_valid():
            instance=form.save(commit=False)
            form.save()
            
            return redirect('microfinance:addguarantordocs', pk=pk, sk=instance.pk)
            
    else: 
        form=AddGuarantor()     
    return render(request,'microfinance/Add_Guarantor.html',{'form':form})

@login_required(login_url="/accounts/login/")
def Add_Guarantor_Docs(request,pk,sk):
    if request.method == 'POST':        
        form=AddGuarantorDocs(request.POST,request.FILES)      
        instance=form.save(commit=False)
        instance.Guarantor_id = sk
        instance.save()
        if 'k' in request.POST:            
            return redirect('microfinance:addguarantordocs', pk=pk,sk=sk)
        if 'l' in request.POST:
            
            return redirect('microfinance:addloan', pk=pk,  sk=sk)      
            
    else: 
        form=AddGuarantorDocs()     
    return render(request,'microfinance/Add_Guarantor_Docs.html',{'form':form})

@login_required(login_url="/accounts/login/")
def Add_Expense(request):
    if request.user.is_superuser:    
        if request.method == 'POST':
            Date = request.POST.get('Month')
            form=AddExpenditures(request.POST,request.FILES)
            Expense = Expenditures.objects.filter(Date__month=Date,Date__year=timezone.now().date().year).order_by('Date','-Amount')
            if form.is_valid():
                form.save()
            return render(request,'microfinance/Add_Expense.html',{'form':form,'expense':Expense})
        else: 
            Expense = Expenditures.objects.filter(Date__month=timezone.now().date().month,Date__year=timezone.now().date().year).order_by('Date','-Amount')
            form=AddExpenditures()     
            return render(request,'microfinance/Add_Expense.html',{'form':form,'expense':Expense})
    else:
        return HttpResponse('you dont have access to this page. Contact admin')

        
@login_required(login_url="/accounts/login/")
def AllExpense(request):
    if request.user.is_superuser:
        Expense = Expenditures.objects.all().order_by('Date','-Amount')
        return render(request,'microfinance/Add_Expense.html',{'expense':Expense})
    else:
        return HttpResponse('you dont have access to this page. Contact admin')

@login_required(login_url="/accounts/login/")
def Client_Detail(request,pk):
    # Retrieve the Client object, or return 404 if not found
    Client = get_object_or_404(Clients, pk=pk)

    # Check if the user is a superuser
    if not request.user.is_superuser:
        # If not a superuser, check if the logged-in user is associated with this client
        user_client = request.user.logged_in_client.first()
        if user_client: # Check if a client is actually associated
            if user_client.pk != Client.pk:
                return HttpResponseForbidden("You are not authorized to view this client's details.")
        else:
            # If the user is not a superuser and not linked to a client, forbid access
            return HttpResponseForbidden("You are not authorized to view client details.")

    Account = get_object_or_404(Accounts, Client=Client)
    Loan = Loans.objects.filter(Account =Account).distinct()
    guarantors = Guarantors.objects.filter(loans__Account=Account).distinct()

    if request.method == "POST" :
        if "save" in request.POST:
            pk=request.POST['pk']
            rem = request.POST['Reminder']
            remark=request.POST['remark']
            loan = Loans.objects.get(pk=pk)
            loan.remark =remark
            loan.reminder=rem
            loan.save()

            return render(request,'microfinance/Client_Detail.html',{'Client':Client,'Account':Account,'Loan':Loan,'Guarantors':guarantors})
        elif "delete_loan" in request.POST:
            loan_id = request.POST.get('loan_id')
            if loan_id:
                try:
                    loan = Loans.objects.get(pk=loan_id)
                    # Delete associated installments and payments first
                    Installments.objects.filter(Loan=loan).delete()
                    Payments.objects.filter(Loan=loan).delete()
                    Penalty.objects.filter(Loan=loan).delete()
                    # Delete the loan
                    loan.delete()
                    messages.success(request, f'Loan {loan_id} has been successfully deleted.')
                except Loans.DoesNotExist:
                    messages.error(request, 'Loan not found.')
                except Exception as e:
                    messages.error(request, f'Error deleting loan: {str(e)}')
            return redirect('microfinance:clientdetail', pk=pk)
        return redirect('microfinance:addguarantor', pk=pk)
    else:
        return render(request,'microfinance/Client_Detail.html',{'Client':Client,'Account':Account,'Loan':Loan,'Guarantors':guarantors})



# def Recalculate_Penalty(Loan):
#     calculate_penalties(Loan)

def Recalculate_Penalty(Loan):
    # Convert QuerySets to the format expected by the function
    installments = Installments.objects.filter(Loan=Loan).filter(Installment_Due__gt=0).order_by('Date_Due')
    payments = Payments.objects.filter(Loan=Loan, Payment_Type=1).order_by('Date_Paid')
    
    installments_data = []
    for inst in installments:
        installments_data.append({
            'Date_Due': inst.Date_Due,
            'Installment_Due': inst.Installment_Due
        })
    
    payments_data = []
    for pay in payments:
        payments_data.append({
            'Date_Paid': pay.Date_Paid,
            'Amount_Paid': pay.Amount_Paid
        })
    
    _calculate_individual_penalties_corrected(Loan, installments_data, payments_data, timezone.now().date())

def removePenalty(Loan,startDate):
    try: 
        Penalty_Obj = getPenalty(Loan,startDate)
        if(Penalty_Obj is not None):
            Penalty_Obj.delete()
    except Exception as e:
        print(e)
        return None


def getPenalty(Loan,startDate):
    try:
        Penalty_Obj = Penalty.objects.get(Loan=Loan,Date_Started=startDate)
        return Penalty_Obj
    except:
        print('Penalty not found')
        return None



def getOrCreatePenalties(Loan,startDate,endDate,penalty_amnt,penalty_calc):
    try:
        Penalty_Obj = getPenalty(Loan,startDate)
        Penalty_Obj = Penalty(Loan=Loan,Date_Started=startDate,Date_Ended=endDate,Amount=penalty_amnt,Penalty_Calc=penalty_calc,Installment_Due_Date=startDate)
        Penalty_Obj.save()
    except Penalty.DoesNotExist: 
        print('get or create penalty error')
        return None




def pay_installment(request,loan,payments,DatePaid):
    Amount_Paid = float(request.POST.get('amount'))             #amount entered
    Amount_Paid=round(Amount_Paid,1)
    if DatePaid is None or DatePaid =='':
        DatePaid=datetime.now()
    else:
        DatePaid =datetime.strptime(DatePaid, "%Y-%m-%d")  
    paymentOnSameDay = payments.filter(
        Loan_id=loan.id,
        Payment_Type=1,
        Date_Paid=DatePaid
    ).first()
    if(paymentOnSameDay is not None):
        paymentOnSameDay.Amount_Paid+=Amount_Paid
        paymentOnSameDay.save()
    else:
        paymentObj = Payments(Amount_Paid=Amount_Paid,Date_Paid=DatePaid,Loan=loan)
        paymentObj.save()
    Recalculate_Penalty(loan)

@login_required(login_url="/accounts/login/")
def Loan_Detail(request,pk):
    print("=" * 50)
    print("LOAN_DETAIL VIEW CALLED!")
    print(f"Loan ID: {pk}")
    print("=" * 50)
    Loan=Loans.objects.get(pk=pk)
    Installment = Installments.objects.filter(Loan=Loan).filter(Installment_Due__gt=0).order_by('Date_Due')
    print(f"=== INSTALLMENT DEBUG ===")
    print(f"Found {Installment.count()} installments for loan {Loan.pk}")
    today = timezone.now().date()
    print(f"Today's date: {today}")
    for inst in Installment:
        print(f"Installment: Date_Due={inst.Date_Due}, Amount={inst.Installment_Due}, Paid={inst.Installment_Paid}, Is Overdue: {inst.Date_Due < today}")
    print(f"=== END INSTALLMENT DEBUG ===")
    Account =Accounts.objects.get(loans=Loan)  
    Client =Clients.objects.get(accounts=Account)    
    Payment =Payments.objects.filter(Loan=Loan).filter(Payment_Type=1).order_by('Date_Paid')
    Total_Amount_Paid = Payments.objects.filter(Loan=Loan, Payment_Type=1).aggregate(Sum('Amount_Paid'))['Amount_Paid__sum'] or 0
    Total_Loan_Amount = Loan.Principle_Amount + Loan.Principle_Amount * Loan.Intrest_Rate / 100
    Penalties = Penalty.objects.filter(Loan=Loan)
    print(f"=== PENALTY DEBUG ===")
    print(f"Found {Penalties.count()} penalties for loan {Loan.pk}")
    for penalty in Penalties:
        print(f"Penalty: Date_Started={penalty.Date_Started}, Date_Ended={penalty.Date_Ended}, Amount={penalty.Amount}, Status={penalty.Status}")
    print(f"=== END PENALTY DEBUG ===")
    DatePaid= request.POST.get('date_paid')    

    lastinst = Installment.filter(Date_Paid__isnull=False).filter(Installment_Paid__gt=0).order_by('Date_Paid').last()  

    if request.method == "POST":  
        Total_Pending = Total_Loan_Amount 
        print('=== FULL POST DATA DEBUG ===')
        print('POST keys:', list(request.POST.keys()))
        print('POST values:', dict(request.POST))
        print('Looking for edit_payment:', 'edit_payment' in request.POST)
        print('================================')  #total amount stored in starting to calculate amnt pending 
        if 'status' in request.POST:    #To change the current status
            status = bool(request.POST.get('Status'))
            Loan.Status =status
            Loan.save()              
        
        if "pay" in request.POST:   #Code to add amount paid 
            pay_installment(request,Loan,Payment,DatePaid)

        if "penalty" in request.POST:
            PenaltyObjects =Penalties.filter(Status = False).order_by("Date_Started")
            Amount_Paid = float(request.POST.get('Penalty_Paid')) 
            Amount_Paid=round(Amount_Paid,1)
            PenaltyIndx =0
            paymentOnSameDay = Payment.filter(
                Loan_id=Loan.id,
                Payment_Type=2,
                Date_Paid=DatePaid
            ).first()
            if(paymentOnSameDay is not None):
                paymentOnSameDay.Amount_Paid+=Amount_Paid
                paymentOnSameDay.save()
            else:
                paymentObj = Payments(Amount_Paid=Amount_Paid,Date_Paid=DatePaid,Loan=Loan,Payment_Type=2)
                paymentObj.save()
            while(Amount_Paid>0 and PenaltyIndx<len(PenaltyObjects)):
                if(Amount_Paid<PenaltyObjects[PenaltyIndx].Penalty_Calc):
                    PenaltyObjects[PenaltyIndx].Penalty_Paid = Amount_Paid 
                    PenaltyObjects[PenaltyIndx].Status = bool(request.POST.get('Status'))
                else:
                    PenaltyObjects[PenaltyIndx].Penalty_Paid =PenaltyObjects[PenaltyIndx].Penalty_Calc
                    PenaltyObjects[PenaltyIndx].Status=True
                PenaltyObjects[PenaltyIndx].Penalty_Paid_Date =datetime.now()
                PenaltyObjects[PenaltyIndx].save()
                Amount_Paid-=PenaltyObjects[PenaltyIndx].Penalty_Calc
                PenaltyIndx+=1
        
            # Handle payment editing
        if "edit_payment" in request.POST:
            payment_id = request.POST.get('payment_id')
            print(f"=== PAYMENT EDIT REQUEST ===")
            print(f"Payment ID: {payment_id}")
            print(f"Date Paid: {request.POST.get('date_paid')}")
            print(f"Amount: {request.POST.get('amount')}")
            print(f"Payment Type: {request.POST.get('payment_type')}")
            
            success = False
            try:
                payment = Payments.objects.get(pk=payment_id, Loan=Loan)
                old_date = payment.Date_Paid
                old_amount = payment.Amount_Paid
                
                print(f"Found payment: {payment.pk}, Old Date: {old_date}, Old Amount: {old_amount}")
                
                new_date = request.POST.get('date_paid')
                new_amount = float(request.POST.get('amount'))
                new_payment_type = int(request.POST.get('payment_type'))
                
                print(f"New values from form: Date={new_date}, Amount={new_amount}, Type={new_payment_type}")
                print(f"Old values from DB: Date={old_date}, Amount={old_amount}, Type={payment.Payment_Type}")
                
                payment.Date_Paid = new_date
                payment.Amount_Paid = new_amount
                payment.Payment_Type = new_payment_type
                payment.save()
                print(f"Successfully updated payment {payment_id}")
                print(f"Final values in DB: Date={payment.Date_Paid}, Amount={payment.Amount_Paid}, Type={payment.Payment_Type}")
                
                success = True
                
                # Recalculate penalties if payment date or amount changed
                date_changed = str(old_date) != str(new_date)
                amount_changed = old_amount != new_amount
                print(f"Date changed: {date_changed} (old: {old_date}, new: {new_date})")
                print(f"Amount changed: {amount_changed} (old: {old_amount}, new: {new_amount})")
                
                if date_changed or amount_changed:
                    print(f"Payment date/amount changed, recalculating penalties...")
                    try:
                        # Convert QuerySets to the format expected by the function
                        installments_data = []
                        for inst in Installment:
                            installments_data.append({
                                'Date_Due': inst.Date_Due,
                                'Installment_Due': inst.Installment_Due
                            })
                        
                        payments_data = []
                        for pay in Payment:
                            payments_data.append({
                                'Date_Paid': pay.Date_Paid,
                                'Amount_Paid': pay.Amount_Paid
                            })
                        
                        _calculate_individual_penalties(Loan, installments_data, payments_data, timezone.now().date())
                        print(f"Penalties recalculated after payment update")
                    except Exception as penalty_error:
                        print(f"WARNING: Penalty recalculation failed: {str(penalty_error)}")
                        # Don't fail the payment update if penalty recalculation fails
                else:
                    print(f"No changes detected, skipping penalty recalculation")
                
            except Payments.DoesNotExist:
                print(f"ERROR: Payment {payment_id} not found")
            except Exception as e:
                print(f"ERROR updating payment: {str(e)}")
            print(f"=== END PAYMENT EDIT ===")
            
            # Always redirect back to loan detail page
            if success:
                return redirect(f"{request.path}?payment_updated=true")
            else:
                return redirect(f"{request.path}?payment_error=true")
        
        # Handle payment deletion
        if "delete_payment" in request.POST:
            payment_id = request.POST.get('payment_id')
            try:
                payment = Payments.objects.get(pk=payment_id, Loan=Loan)
                payment.delete()
                print(f"Deleted payment {payment_id}")
                
                # Recalculate penalties after payment deletion
                print(f"Payment deleted, recalculating penalties...")
                # Convert QuerySets to the format expected by the function
                installments_data = []
                for inst in Installment:
                    installments_data.append({
                        'Date_Due': inst.Date_Due,
                        'Installment_Due': inst.Installment_Due
                    })
                
                payments_data = []
                for pay in Payment:
                    payments_data.append({
                        'Date_Paid': pay.Date_Paid,
                        'Amount_Paid': pay.Amount_Paid
                    })
                
                _calculate_individual_penalties(Loan, installments_data, payments_data, timezone.now().date())
                print(f"Penalties recalculated after payment deletion")
                
                # Redirect with success parameter
                return redirect(f"{request.path}?payment_deleted=true")
                
            except Payments.DoesNotExist:
                print(f"Payment {payment_id} not found")
        
        # Handle penalty editing
        if "edit_penalty" in request.POST:
            penalty_id = request.POST.get('penalty_id')
            try:
                penalty = Penalty.objects.get(pk=penalty_id, Loan=Loan)
                penalty.Date_Started = request.POST.get('date_started')
                penalty.Date_Ended = request.POST.get('date_ended')
                penalty.Amount = float(request.POST.get('amount'))
                penalty.Penalty_Calc = float(request.POST.get('penalty_calc'))
                penalty.Status = bool(request.POST.get('status'))
                penalty.save()
                print(f"Updated penalty {penalty_id}")
                
                # Redirect with success parameter
                return redirect(f"{request.path}?penalty_updated=true")
                
            except Penalty.DoesNotExist:
                print(f"Penalty {penalty_id} not found")
        
        # Handle penalty deletion
        if "delete_penalty" in request.POST:
            penalty_id = request.POST.get('penalty_id')
            try:
                penalty = Penalty.objects.get(pk=penalty_id, Loan=Loan)
                penalty.delete()
                print(f"Deleted penalty {penalty_id}")
                
                # Recalculate penalties after penalty deletion
                print(f"Penalty deleted, recalculating penalties...")
                # Convert QuerySets to the format expected by the function
                installments_data = []
                for inst in Installment:
                    installments_data.append({
                        'Date_Due': inst.Date_Due,
                        'Installment_Due': inst.Installment_Due
                    })
                
                payments_data = []
                for pay in Payment:
                    payments_data.append({
                        'Date_Paid': pay.Date_Paid,
                        'Amount_Paid': pay.Amount_Paid
                    })
                
                _calculate_individual_penalties(Loan, installments_data, payments_data, timezone.now().date())
                print(f"Penalties recalculated after penalty deletion")
                
                # Redirect with success parameter
                return redirect(f"{request.path}?penalty_deleted=true")
                
            except Penalty.DoesNotExist:
                print(f"Penalty {penalty_id} not found")
        
        return redirect("microfinance:home")

    else: 
        paymentIndx =0
        installmentIndx =0
        totalPending=Total_Loan_Amount
        AmntBal=0
        combinedInstallmentPaymentView =[]
        today = datetime.now().date()
        while(installmentIndx < len(Installment) and paymentIndx < len(Payment)):
            if(Payment[paymentIndx].Payment_Type!=1):
                paymentIndx+=1
            elif(Installment[installmentIndx].Date_Due<Payment[paymentIndx].Date_Paid):
                if(Installment[installmentIndx].Date_Due<=today):
                    AmntBal+=Installment[installmentIndx].Installment_Due
                combinedInstallmentPaymentView.append({
                    "Date_Due":Installment[installmentIndx].Date_Due,
                    "Date_Paid":"-",
                    "Amount_Due":Installment[installmentIndx].Installment_Due,
                    "Amount_Paid":"-",
                    "Amount_Balance":round(AmntBal,2),
                    "Total_Balance":totalPending,
                })   
                installmentIndx+=1
            elif(Installment[installmentIndx].Date_Due>Payment[paymentIndx].Date_Paid):
                AmntBal-=Payment[paymentIndx].Amount_Paid
                totalPending -= Payment[paymentIndx].Amount_Paid
                combinedInstallmentPaymentView.append({
                    "Date_Due":"-",
                    "Date_Paid":Payment[paymentIndx].Date_Paid,
                    "Amount_Due":" - ",
                    "Amount_Paid":Payment[paymentIndx].Amount_Paid,
                    "Amount_Balance":round(AmntBal,2),
                    "Total_Balance":totalPending,
                })   
                paymentIndx+=1
            else:
                if(Installment[installmentIndx].Date_Due<=today):
                    AmntBal+=Installment[installmentIndx].Installment_Due
                AmntBal-=Payment[paymentIndx].Amount_Paid
                totalPending -= Payment[paymentIndx].Amount_Paid
                combinedInstallmentPaymentView.append({
                    "Date_Due":Installment[installmentIndx].Date_Due,
                    "Date_Paid":Payment[paymentIndx].Date_Paid,
                    "Amount_Due":Installment[installmentIndx].Installment_Due,
                    "Amount_Paid":Payment[paymentIndx].Amount_Paid,
                    "Amount_Balance":round(AmntBal,2),
                    "Total_Balance":totalPending,
                })   
                installmentIndx+=1
                paymentIndx+=1
        while(installmentIndx < len(Installment)):
            if(Installment[installmentIndx].Date_Due<=today):
                AmntBal+=Installment[installmentIndx].Installment_Due
            combinedInstallmentPaymentView.append({
                "Date_Due":Installment[installmentIndx].Date_Due,
                "Date_Paid":"-",
                "Amount_Due":Installment[installmentIndx].Installment_Due,
                "Amount_Paid":"-",
                "Amount_Balance":round(AmntBal,2),
                "Total_Balance":totalPending,
            })   
            installmentIndx+=1
        while(paymentIndx < len(Payment)):
            AmntBal-=Payment[paymentIndx].Amount_Paid
            totalPending -= Payment[paymentIndx].Amount_Paid
            combinedInstallmentPaymentView.append({
                "Date_Due":"-",
                "Date_Paid":Payment[paymentIndx].Date_Paid,
                "Amount_Due":" - ",
                "Amount_Paid":Payment[paymentIndx].Amount_Paid,
                "Amount_Balance":round(AmntBal,2),
                "Total_Balance":totalPending,
            })   
            paymentIndx+=1
        Recalculate_Penalty(Loan)
        
        PenaltyPayments = Payments.objects.filter(Loan=Loan, Payment_Type=2).order_by('Date_Paid')
        combinedPenaltyPaymentView = []
        penaltyIndx = 0
        penaltyPaymentIndx = 0
        
        # Initialize running totals for penalties
        current_penalty_outstanding = 0
        total_penalty_calc = 0
        total_penalty_paid = 0

        # Create a mapping of penalty start dates to installment due dates
        # This is a simplified approach - in a real system, you'd want to store this in the database
        # penalty_to_installment_map = {}
        # for inst in Installment:
        #     if inst.Date_Due < today:  # Only overdue installments
        #         # Find penalties that start on or after this installment due date
        #         for penalty in Penalties:
        #             if penalty.Date_Started >= inst.Date_Due and penalty.Date_Started not in penalty_to_installment_map:
        #                 print('fssf',penalty.Date_Started,penalty.Date_Ended, inst.Date_Due)
        #                 penalty_to_installment_map[penalty.Date_Started] = inst.Date_Due
        #                 break

        # Merge Penalties and PenaltyPayments
        while penaltyIndx < len(list(Penalties)) and penaltyPaymentIndx < len(list(PenaltyPayments)):
            penalty = list(Penalties)[penaltyIndx]
            penalty_payment = list(PenaltyPayments)[penaltyPaymentIndx]

            # Handle cases where penalty_payment.Date_Paid might be None
            if penalty_payment.Date_Paid is None or penalty.Date_Started <= penalty_payment.Date_Paid:
                # Process penalty first if its start date is earlier or same as payment date
                # or if the payment date is None
                # installment_due_date = penalty_to_installment_map.get(penalty.Date_Started, penalty.Date_Started)
                combinedPenaltyPaymentView.append({
                    "Date_Started": penalty.Date_Started,
                    "Date_Ended": penalty.Date_Ended,
                    "Amount": penalty.Amount,
                    "Penalty_Calc": penalty.Penalty_Calc,
                    "Penalty_Paid": penalty.Penalty_Paid,
                    "Status": penalty.Status,
                    "Payment_Amount": "-",  # No payment on this row
                    "Payment_Date": "-",
                    "Installment_Due_Date": penalty.Installment_Due_Date
                })
                current_penalty_outstanding += penalty.Penalty_Calc - penalty.Penalty_Paid
                total_penalty_calc += penalty.Penalty_Calc
                total_penalty_paid += penalty.Penalty_Paid
                penaltyIndx += 1
            else:
                # Process payment if its date is earlier
                combinedPenaltyPaymentView.append({
                    "Date_Started": "-",
                    "Date_Ended": "-",
                    "Amount": "-",
                    "Penalty_Calc": "-",
                    "Penalty_Paid": "-",
                    "Status": "-",
                    "Payment_Amount": penalty_payment.Amount_Paid,
                    "Payment_Date": penalty_payment.Date_Paid,
                    "Installment_Due_Date": penalty.Installment_Due_Date  # No installment date for payment rows
                })
                current_penalty_outstanding -= penalty_payment.Amount_Paid
                penaltyPaymentIndx += 1

        # Add any remaining penalties
        while penaltyIndx < len(list(Penalties)):
            penalty = list(Penalties)[penaltyIndx]
            # installment_due_date = penalty_to_installment_map.get(penalty.Date_Started, penalty.Date_Started)
            combinedPenaltyPaymentView.append({
                "Date_Started": penalty.Date_Started,
                "Date_Ended": penalty.Date_Ended,
                "Amount": penalty.Amount,
                "Penalty_Calc": penalty.Penalty_Calc,
                "Penalty_Paid": penalty.Penalty_Paid,
                "Status": penalty.Status,
                "Payment_Amount": "-",
                "Payment_Date": "-",
                "Installment_Due_Date": penalty.Installment_Due_Date
            })
            current_penalty_outstanding += penalty.Penalty_Calc - penalty.Penalty_Paid
            total_penalty_calc += penalty.Penalty_Calc
            total_penalty_paid += penalty.Penalty_Paid
            penaltyIndx += 1

        # Add any remaining penalty payments
        while penaltyPaymentIndx < len(list(PenaltyPayments)):
            penalty_payment = list(PenaltyPayments)[penaltyPaymentIndx]
            combinedPenaltyPaymentView.append({
                "Date_Started": "-",
                "Date_Ended": "-",
                "Amount": "-",
                "Penalty_Calc": "-",
                "Penalty_Paid": "-",
                "Status": "-",
                "Payment_Amount": penalty_payment.Amount_Paid,
                "Payment_Date": penalty_payment.Date_Paid,
                "Installment_Due_Date": penalty.Installment_Due_Date  # No installment date for payment rows
            })
            current_penalty_outstanding -= penalty_payment.Amount_Paid
            penaltyPaymentIndx += 1

        # Sort combinedPenaltyPaymentView by Installment_Due_Date (penalties first, then payments)
        def sort_key(item):
            if item['Installment_Due_Date'] is not None:
                return (0, item['Installment_Due_Date'])  # Penalties first
            else:
                return (1, item['Payment_Date'] if item['Payment_Date'] != '-' else None)  # Payments second
        
        combinedPenaltyPaymentView.sort(key=sort_key)
        
        print('Total_Loan_Amount',Total_Loan_Amount)
        return render(request,'microfinance/LoanDetail.html',{
            'Total_Penalty': round(total_penalty_calc, 1),
            'Total_Loan_Amount': Loan.Principle_Amount + Loan.Principle_Amount * Loan.Intrest_Rate / 100,
            'Installment':combinedInstallmentPaymentView,
            'Loan':Loan,
            'Client':Client,
            'Penalty':Penalties,
            'Total_Pending':round(totalPending,1),
            'amnt_pen':round(AmntBal ,1),
            'lastinst':lastinst,
            'Penalties':Penalties,
            'Payments':Payment,
            'Installments':Installment,
            'combinedPenaltyPaymentView':combinedPenaltyPaymentView,
            'Total_Penalty_Paid': round(total_penalty_paid, 1),
            'Principal_Amount': Loan.Principle_Amount,
            'Total_Amount_Paid': Total_Amount_Paid,
        })


class ClientFilter(BaseFilter):
    search_fields = {
        'search_name' : ['Name'],
        'search_id' : { 'operator' : '__exact', 'fields' : ['pk'] },
        'search_phone' : ['Phone_no1','Phone_no2']
    }

class ClientSearchList(LoginRequiredMixin, SearchListView):

    model = Clients
    template_name = "microfinance/Client_Result.html"
    form_class = ClientSearchForm
    filter_class = ClientFilter


@login_required(login_url="/accounts/login/")
def Loanidsearch(request):
    loanid=request.POST.get('loan_id')
    if len(loanid)==0  or loanid ==0:
        return redirect('/Home')
    loan = Loans.objects.get(pk=int(loanid))
    Clientid= Clients.objects.filter(pk=loan.Account.Client.pk)
    return redirect('microfinance:loandetail',pk=loan.pk)



@login_required(login_url="/accounts/login/")
def Reports(request):
    staff =Staff.objects.all().distinct()
    return render(request,'microfinance/Reports.html',{'users':staff})

# @login_required(login_url="/accounts/login/")
# def Officer_And_Frequency_Wise_Report(request):
#     Staff_pk=int(request.POST.get('name'))
#     status =(request.POST.get('status'))
#     if status == 'False':
#         Loanstat =Loans.objects.all().filter(Status=False)
#     else:
#         Loanstat =Loans.objects.all().filter(Status=True)
#     Frequency=int(request.POST.get('loan'))
#     if Staff_pk != 0 and Frequency != 0: 
#         Loan =Loanstat.filter(Loan_Collector=Staff_pk,Frequency =Frequency)
#     if Staff_pk == 0 and Frequency !=0:
#         Loan =Loanstat.filter(Frequency =Frequency).exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10)
#     if Staff_pk !=0 and Frequency ==0:
#         Loan =Loanstat.filter(Loan_Collector=Staff_pk)
#     if Staff_pk == 0 and Frequency == 0:
#         Loan =Loanstat.exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10)
#     Installment = Installments.objects.filter(Loan__in=Loan).order_by('Date_Due').filter(Date_Due__lte =datetime.now())
#     Advance_Inst =Installments.objects.filter(Date_Due__gt=datetime.now()).filter(Date_Paid=datetime.now())
#     Today = datetime.now()
#     Total_Daily_inst = 0
#     Total_Amnt_to_be_coll=0
#     Total_amnt_col =0
#     Total_bal = 0
#     Dic1 ={}
#     Dic2={}
#     dic3={}
#     dic4={}
#     for l in Loan:
#         Total_Daily_inst =Total_Daily_inst + l.installments_set.first().Installment_Due
#         Total_Amnt_to_be_coll=0
#         Total_amnt_col =0
#         Total_bal = 0
#         All1 =Installments.objects.all().filter(Loan =l).order_by('Date_Due').filter(Date_Due__lte = datetime.now())
#         All = Installments.objects.all().filter(Loan =l).order_by('Date_Due').exclude(Date_Due__lte= datetime.now())
#         All2 =  Installments.objects.all().filter(Loan =l).order_by('Date_Due').filter(Date_Paid__isnull = False)
#         for a in All1:
#             Total_Amnt_to_be_coll = Total_Amnt_to_be_coll + a.Installment_Due
#         for a in All2:
#             Total_amnt_col = Total_amnt_col + a.Installment_Paid
#         Total_bal = Total_bal + Total_Amnt_to_be_coll - Total_amnt_col
#         for a in All:
#             Total_bal = Total_bal + a.Installment_Due
#         Dic1[l.pk]=round(Total_Amnt_to_be_coll,1)
#         Dic2[l.pk]=round(Total_amnt_col,1)
#         dic3[l.pk] = round(abs(Dic1[l.pk]-Dic2[l.pk]),1)
#         dic4[l.pk]=round(Total_bal,1)
        
#     Total_Amnt_Pending=0
#     Dic ={}
#     for l in Loan:
#         Total_Amnt_Pending=0
#         All =Installments.objects.all().filter(Loan =l).order_by('Date_Due')
#         for a in All:
#             Total_Amnt_Pending = Total_Amnt_Pending + a.Installment_Due - a.Installment_Paid
#         Dic[l.pk]=Total_Amnt_Pending
    
#     Total_Amnt_Pending=0
    
#     for i,j in dic3.items():
#         Total_Amnt_Pending+=j
#     Total_Amnt_balance=0
#     for i,j in Dic.items():
#         Total_Amnt_balance+=j
       
#     if Advance_Inst is not None:
#         return render(request,'microfinance/Officer_And_Frequency_Wise_Report.html',{'adv':Advance_Inst,'loans':Loan,'insts':Installment,'Today':Today,'Staff':Staff_pk,'Frequency':Frequency,'totalpendingdict':Dic,'TotalAmnt':Total_Amnt_Pending,'Total_bal_dic':dic4,'Total_amt_to_be_col_dic':Dic1,'Total_amt_col_dic':Dic2,'Total_Pen_dic':dic3,'Total_Daily_inst':Total_Daily_inst,'Total_Amnt_balance':Total_Amnt_balance})
#     else:
#         return render(request,'microfinance/Officer_And_Frequency_Wise_Report.html',{'loans':Loan,'insts':Installment,'Today':Today,'Staff':Staff_pk,'Frequency':Frequency,'totalpendingdict':Dic,'TotalAmnt':Total_Amnt_Pending,'Total_bal_dic':dic4,'Total_amt_to_be_col_dic':Dic1,'Total_amt_col_dic':Dic2,'Total_Pen_dic':dic3,'Total_Daily_inst':Total_Daily_inst,'Total_Amnt_balance':Total_Amnt_balance})

# @login_required(login_url="/accounts/login/")
# def Officer_And_Frequency_Wise_pdf(request):
#     if request.method =="POST":
#         List = request.POST.getlist('Check') 
        
#         status =(request.POST.get('status'))
#         Loan = Loans.objects.none()
#         for i in List:
#             n = Loans.objects.filter(id=i)            
#             Loan= Loan | n
        
#         Installment = Installments.objects.filter(Loan__in=Loan).order_by('Date_Due').filter(Date_Due__lte =datetime.now())
#         Advance_Inst =Installments.objects.filter(Date_Due__gt=datetime.now()).filter(Date_Paid=datetime.now())
#         Today = datetime.now()
        
#         Total_Amnt_to_be_coll=0
#         Total_amnt_col =0
#         Total_bal = 0
#         Dic1 ={}
#         Dic2={}
#         dic3={}
#         dic4={}
#         for l in Loan:
            
#             Total_Amnt_to_be_coll=0
#             Total_amnt_col =0
#             Total_bal = 0
#             All1 =Installments.objects.all().filter(Loan =l).order_by('Date_Due').filter(Date_Due__lte = datetime.now())
#             All = Installments.objects.all().filter(Loan =l).order_by('Date_Due').exclude(Date_Due__lte= datetime.now())
#             All2 =  Installments.objects.all().filter(Loan =l).order_by('Date_Due').filter(Date_Paid__isnull = False)
#             for a in All1:
#                 Total_Amnt_to_be_coll = Total_Amnt_to_be_coll + a.Installment_Due
#             for a in All2:
#                 Total_amnt_col = Total_amnt_col + a.Installment_Paid
#             Total_bal = Total_bal + Total_Amnt_to_be_coll - Total_amnt_col
#             for a in All:
#                 Total_bal = Total_bal + a.Installment_Due
#             Dic1[l.pk]=round(Total_Amnt_to_be_coll,1)
#             Dic2[l.pk]=round(Total_amnt_col,1)
#             dic3[l.pk] = round(abs(Dic1[l.pk]-Dic2[l.pk]),1)
#             dic4[l.pk]=round(Total_bal,1)
            
#         Total_Amnt_Pending=0
#         Dic ={}
#         for l in Loan:
#             Total_Amnt_Pending=0
#             All =Installments.objects.all().filter(Loan =l).order_by('Date_Due')
#             for a in All:
#                 Total_Amnt_Pending = Total_Amnt_Pending + a.Installment_Due - a.Installment_Paid
#             Dic[l.pk]=Total_Amnt_Pending
        
#         Total_Amnt_Pending=0
#         for i,j in Dic.items():
#             Total_Amnt_Pending+=j
#         if Advance_Inst is not None:
#             return render(request,'microfinance/pdfs/Officer_And_Frequency_Wise_pdf.html',{'adv':Advance_Inst,'loans':Loan,'insts':Installment,'Today':Today,'totalpendingdict':Dic,'TotalAmnt':Total_Amnt_Pending,'Total_bal_dic':dic4,'Total_amt_to_be_col_dic':Dic1,'Total_amt_col_dic':Dic2,'Total_Pen_dic':dic3})
#         else:
#             return render(request,'microfinance/pdfs/Officer_And_Frequency_Wise_pdf.html',{'loans':Loan,'insts':Installment,'Today':Today,'totalpendingdict':Dic,'TotalAmnt':Total_Amnt_Pending,'Total_bal_dic':dic4,'Total_amt_to_be_col_dic':Dic1,'Total_amt_col_dic':Dic2,'Total_Pen_dic':dic3})


@login_required(login_url="/accounts/login/")
def Total_Finance_And_Collection_Report(request):
    start=request.POST.get('from')
    end=request.POST.get('to')
    if(start == '' or end == ''):
        return render(request,'microfinance/error/report_datenull.html')
    sdate = parse_date(start)    
    edate =parse_date(end)
    dd = [sdate + timedelta(days=x) for x in range((edate-sdate).days + 1)]
    Today= datetime.now()
    Lo = Loans.objects.filter(First_Due_Date__range=[start,end])
    Loan = Loans.objects.filter(Q(installments__Date_Due__range=[start,end])|Q(installments__Date_Paid__range=[start,end])).distinct()
    Installment =Installments.objects.filter(Q(Date_Due__range=[start,end])|Q(Date_Paid__range=[start,end])).order_by("Loan")
    Installment2 = Installments.objects.filter(Date_Due__range=[start,end]).order_by('Loan')
    Penalties =Penalty.objects.filter(Date_Started__range=[start,end])
    Pen =Penalty.objects.filter(Penalty_Paid_Date__range=[start,end])
    Total_Amnt_Financed =0
    Total_FileCharge=0
    Total_Amnt_Collected=0
    Total_Amnt_To_Be_Collected=0
    Total_Intrest_To_Be_Collected=0
    Total_Intrest_Collected=0
    Total_Penalty =0
    Total_Penalty_Coll =0
    for Inst in Installment2:
        Total_Amnt_To_Be_Collected = Total_Amnt_To_Be_Collected + Inst.Installment_Due   
        Total_Intrest_To_Be_Collected =Total_Intrest_To_Be_Collected + Inst.Installment_Due * Inst.Loan.Intrest_Rate/100
    for p in Penalties:
        if p.Status == True:
            Total_Penalty= Total_Penalty + p.Penalty_Paid
            
        else:
            Total_Penalty= Total_Penalty + p.Penalty_Calc
            
    for p in Pen:
        Total_Penalty_Coll =Total_Penalty_Coll + p.Penalty_Paid
    for L in Lo:
        Total_Amnt_Financed = Total_Amnt_Financed + L.Principle_Amount
        Total_FileCharge = Total_FileCharge + L.File_Charge_Percent*L.Principle_Amount/100

    for Inst in Installment:
        Total_Intrest_Collected = Total_Intrest_Collected + Inst.Installment_Paid*Inst.Loan.Intrest_Rate/100
        Total_Amnt_Collected = Total_Amnt_Collected + Inst.Installment_Paid
            
    return render(request,'microfinance/Total_Finance_And_Collection_Report.html',{'Total_pencol':Total_Penalty_Coll,'start':start,'end':end,'loans':Loan,'insts':Installment,'dates':dd,'totalloan':Total_Amnt_Financed,'totalfc':Total_FileCharge,'totalinst':Total_Amnt_Collected,
    'totalamnt':Total_Amnt_To_Be_Collected,'intrest':Total_Intrest_To_Be_Collected,'totalpenalty':Total_Penalty,'intrestrec':Total_Intrest_Collected})

@login_required(login_url="/accounts/login/")
def Total_Finance_And_Collection_pdf(request):
    start=request.POST.get('from')
    end=request.POST.get('to')
    sdate = parse_date(start)
    edate =parse_date(end)
    dd = [sdate + timedelta(days=x) for x in range((edate-sdate).days + 1)]
    Today= datetime.now()
    Loan = Loans.objects.filter(Q(installments__Date_Due__range=[start,end])|Q(installments__Date_Paid__range=[start,end])).distinct()
    Installment =Installments.objects.filter(Date_Due__range=[start,end]).order_by("Loan")
    Installment2 = Installments.objects.filter(Date_Due__range=[start,end]).order_by('Loan')
    Penalties =Penalty.objects.filter(Date_Started__range=[start,end])
    Pen =Penalty.objects.filter(Penalty_Paid_Date__range=[start,end])
    Total_Amnt_Financed =0
    Total_FileCharge=0
    Total_Amnt_Collected=0
    Total_Amnt_To_Be_Collected=0
    Total_Intrest_To_Be_Collected=0
    Total_Intrest_Collected=0
    Total_Penalty =0
    Total_Penalty_Coll =0
    for Inst in Installment2:
        Total_Amnt_To_Be_Collected = Total_Amnt_To_Be_Collected + Inst.Installment_Due        
        Total_Intrest_To_Be_Collected =Total_Intrest_To_Be_Collected + Inst.Installment_Due * Inst.Loan.Intrest_Rate/100
    for p in Penalties:
        if p.Status == True:
            Total_Penalty= Total_Penalty + p.Penalty_Paid
        else:
            Total_Penalty= Total_Penalty + p.Penalty_Calc
    for p in Pen:
        Total_Penalty_Coll =Total_Penalty_Coll + p.Penalty_Paid
    for L in Loan:
        Total_Amnt_Financed = Total_Amnt_Financed + L.Principle_Amount
        Total_FileCharge = Total_FileCharge + L.File_Charge_Percent*L.Principle_Amount/100
    for Inst in Installment:
        Total_Intrest_Collected = Total_Intrest_Collected + Inst.Installment_Paid*Inst.Loan.Intrest_Rate/100
        Total_Amnt_Collected = Total_Amnt_Collected + Inst.Installment_Paid
    return render(request,'microfinance/pdfs/Total_Finance_And_Collection_pdf.html',{'Total_pencol':Total_Penalty_Coll,'start':start,'end':end,'loans':Loan,'insts':Installment,'dates':dd,'totalloan':Total_Amnt_Financed,'totalfc':Total_FileCharge,'totalinst':Total_Amnt_Collected,
    'totalamnt':Total_Amnt_To_Be_Collected,'intrest':Total_Intrest_To_Be_Collected,'totalpenalty':Total_Penalty,'intrestrec':Total_Intrest_Collected})


@login_required(login_url="/accounts/login/")
def Officerwise_Total_Finance_And_Collection_Report(request):
    Staff_pk=int(request.POST.get('name'))
    Frequency=int(request.POST.get('loan'))
    start=request.POST.get('from')
    end=request.POST.get('to')
    if(start == '' or end == ''):
        return render(request,'microfinance/error/report_datenull.html')
    sdate = parse_date(start)
    edate =parse_date(end)
    
    Today= datetime.now()
    if Staff_pk != 0 and Frequency != 0: 
        Loan = Loans.objects.filter(Loan_Collector_id=Staff_pk).filter(Frequency=Frequency).filter(Q(installments__Date_Paid__range=[start,end])|Q(installments__Date_Due__range=[start,end])).distinct().order_by("id")
        Loan2 = Loans.objects.filter(Loan_Collector_id=Staff_pk).filter(Frequency=Frequency).filter(penalty__Penalty_Paid_Date__range=[start,end]).distinct().order_by("id")
        Loan3 =Loans.objects.filter(Loan_Collector_id=Staff_pk).filter(Frequency=Frequency).filter(Loan_Date__range=[start,end]).distinct()
 
    if Staff_pk == 0 and Frequency !=0:
        Loan = Loans.objects.filter(Frequency=Frequency).exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10).filter(Q(installments__Date_Paid__range=[start,end])|Q(installments__Date_Due__range=[start,end])).distinct().order_by("id")
        Loan2 = Loans.objects.filter(Frequency=Frequency).exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10).filter(penalty__Penalty_Paid_Date__range=[start,end]).distinct().order_by("id")
        Loan3 =Loans.objects.filter(Frequency=Frequency).filter(Loan_Date__range=[start,end]).distinct()

    if Staff_pk !=0 and Frequency ==0:
        Loan = Loans.objects.filter(Loan_Collector_id=Staff_pk).filter(Q(installments__Date_Paid__range=[start,end])|Q(installments__Date_Due__range=[start,end])).distinct().order_by("id")
        Loan2 = Loans.objects.filter(Loan_Collector_id=Staff_pk).filter(penalty__Penalty_Paid_Date__range=[start,end]).distinct().order_by("id")
        Loan3 =Loans.objects.filter(Loan_Collector_id=Staff_pk).filter(Loan_Date__range=[start,end]).distinct()

    if Staff_pk == 0 and Frequency == 0:
        Loan = Loans.objects.filter(Q(installments__Date_Paid__range=[start,end])|Q(installments__Date_Due__range=[start,end])).exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10).distinct().order_by("id")
        Loan2 = Loans.objects.filter(penalty__Penalty_Paid_Date__range=[start,end]).exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10).distinct().order_by("id")
        Loan3 =Loans.objects.filter(Loan_Date__range=[start,end]).distinct()

    AmntCollected =PenaltyCollected=File_ChargeCollected =AmntToBeCollected= 0
    Amnt_Collected = {}
    Penalty_Collected = {}
    File_Charge={}
    Amnt_To_Be_Collected = {}
    
        
    for i in Loan3:
        File_Charge[i.pk] = i.Principle_Amount*i.File_Charge_Percent/100
        File_ChargeCollected = File_ChargeCollected + File_Charge[i.pk]
    for i in Loan:
        Amnt_Collected[i.pk] = Installments.objects.filter(Loan=i).filter(Date_Paid__range=[start,end]).distinct().aggregate(Sum('Installment_Paid'))
        Amnt_To_Be_Collected[i.pk] = Installments.objects.filter(Loan=i).filter(Date_Due__range=[start,end]).distinct().aggregate(Sum('Installment_Due'))
        if Amnt_Collected[i.pk]["Installment_Paid__sum"]:
            AmntCollected = AmntCollected + Amnt_Collected[i.pk]["Installment_Paid__sum"]
        if Amnt_To_Be_Collected[i.pk]["Installment_Due__sum"]:
            AmntToBeCollected = AmntToBeCollected + Amnt_To_Be_Collected[i.pk]["Installment_Due__sum"] 
    for i in Loan2:
        Penalty_Collected[i.pk]=Penalty.objects.filter(Loan=i).filter(Penalty_Paid_Date__range=[start,end]).distinct().aggregate(Sum('Penalty_Paid'))
        PenaltyCollected = PenaltyCollected + Penalty_Collected[i.pk]["Penalty_Paid__sum"]
    return render(request,'microfinance/Officerwise_Total_Finance_And_Collection_Report.html',{'start':start,'end':end,'Staff':Staff_pk,'amnt_collected':Amnt_Collected,'Loan':Loan,'Loan3':Loan3,'Loan2':Loan2,'amntcollected':AmntCollected,'amnttobecollected':AmntToBeCollected,'amnt_to_be_collected':Amnt_To_Be_Collected,'penalty_collected':Penalty_Collected,'penaltycollected':PenaltyCollected,'file_charge':File_Charge,'filecollected':File_ChargeCollected})


@login_required(login_url="/accounts/login/")
def Officerwise_Total_Finance_And_Collection_pdf(request):
    Staff_pk=int(request.POST.get('name'))
    Frequency=int(request.POST.get('loan'))
    start=request.POST.get('from')
    end=request.POST.get('to')
    if(start == '' or end == ''):
        return render(request,'microfinance/error/report_datenull.html')
    sdate = parse_date(start)
    edate =parse_date(end)
    dd = [sdate + timedelta(days=x) for x in range((edate-sdate).days + 1)]
    Today= datetime.now()
    if Staff_pk != 0 and Frequency != 0: 
        Loan = Loans.objects.filter(Loan_Collector_id=Staff_pk).filter(Frequency=Frequency).filter(Q(installments__Date_Due__range=[start,end])|Q(installments__Date_Paid__range=[start,end])).distinct().order_by("id").filter(Status=False)
    if Staff_pk == 0 and Frequency !=0:
        Loan = Loans.objects.filter(Frequency=Frequency).exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10).filter(Q(installments__Date_Due__range=[start,end])|Q(installments__Date_Paid__range=[start,end])).distinct().order_by("id").filter(Status=False)
    if Staff_pk !=0 and Frequency ==0:
        Loan = Loans.objects.filter(Loan_Collector_id=Staff_pk).filter(Q(installments__Date_Due__range=[start,end])|Q(installments__Date_Paid__range=[start,end])).distinct().order_by("id").filter(Status=False)
    if Staff_pk == 0 and Frequency == 0:
        Loan = Loans.objects.filter(Q(installments__Date_Due__range=[start,end])|Q(installments__Date_Paid__range=[start,end])).exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10).distinct().order_by("id").filter(Status=False)
    Installment =Installments.objects.filter(Q(Date_Due__range=[start,end])|Q(Date_Paid__range=[start,end])).filter(Loan__in=Loan).order_by("Loan")
    Installment2 = Installments.objects.filter(Date_Due__range=[start,end]).filter(Loan__in=Loan)
    Installment5 = Installments.objects.filter(Date_Paid__range=[start,end]).filter(Loan__in=Loan)
    Total_Amnt_Pending=0
    Amnt_Collected = 0
    Dic ={}
    Dic2={}
    for l in Loan:
        Total_Amnt_Pending=0
        Amnt_Collected = 0
        All =Installments.objects.all().filter(Loan =l).filter(Date_Due__lte=end).order_by('Date_Due')
        for a in All:
            Total_Amnt_Pending = Total_Amnt_Pending + a.Installment_Due - a.Installment_Paid
            
        Dic[l.pk]=Total_Amnt_Pending
        install= Installments.objects.all().filter(Q(Date_Due__lte=end)|Q(Date_Paid__lte=end)).filter(Loan =l).order_by('Date_Due')
        for x in install:
            Amnt_Collected = Amnt_Collected + x.Installment_Paid
        Dic2[l.pk]=Amnt_Collected
    Total_Amnt_Financed =0
    Total_Amnt_Collected=0
    Total_Intrest_Collected=0
    for Inst in Installment5:
        Total_Intrest_Collected = Total_Intrest_Collected + Inst.Installment_Paid*Inst.Loan.Intrest_Rate/100
        Total_Amnt_Collected = Total_Amnt_Collected + Inst.Installment_Paid
    return render(request,'microfinance/pdfs/Officerwise_Total_Finance_And_Collection_pdf.html',{'Dic':Dic,'Dic2':Dic2,'loans':Loan,'insts':Installment,'dates':dd,'totalinst':Total_Amnt_Collected,
    'start':start,'end':end,'intrestrec':Total_Intrest_Collected,'Freq':Frequency,'Staff':Staff_pk})

@login_required(login_url="/accounts/login/")
def All_Clients_List(request):
    Staff_pk=int(request.POST.get('name'))
    if Staff_pk !=0 :
        Loan=Loans.objects.all().filter(Loan_Collector_id=Staff_pk).filter(Status=False).filter(Frequency=1)
    else:
        Loan=Loans.objects.all().filter(Status=False).filter(Frequency=1).exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10)
    Total_Amount_To_Be_Collected = 0
    for i in Loan:
        Total_Amount_To_Be_Collected = Total_Amount_To_Be_Collected + i.installments_set.first().Installment_Due
    return render(request,'microfinance/All_Clients_List.html',{'loanee':Loan,'Staff':Staff_pk,'Total_Amount_To_Be_Collected':Total_Amount_To_Be_Collected})


@login_required(login_url="/accounts/login/")
def SMSselect(request):

    if request.method =='POST' and 'DateWiseSms' in request.POST:
        Date =request.POST.get('DatePaid')
        if Date == '':
            Date=timezone.now().date()    
        Loan = Loans.objects.filter(installments__Date_Paid=Date).distinct()
        dic ={}
        for l in Loan:
            Installment = Installments.objects.filter(Date_Paid = Date).filter(Loan =l).order_by('Date_Due','-Installment_To_Be_Paid').first()
            dic[l] = Installment.Installment_Paid
        return render(request,'microfinance/SMSLIST.html',{'Date':Date,'loan':Loan,'dic':dic})
    elif request.method =='POST' and 'CustomSmsSendList' in request.POST:
        Loan = Loans.objects.filter(Status=False)
        Acc = Accounts.objects.filter(loans__in= Loan).distinct()
        Client = Clients.objects.filter(accounts__in=Acc)  
        Date =timezone.now().date()
        return render(request,'microfinance/SMSLIST.html',{'Date':Date,'Client':Client})
    else:
        return render(request,'microfinance/Homepage.html')

@login_required(login_url="/accounts/login/")
def SMS(request):

    List = request.POST.getlist('Check')
    Date =request.POST.get('Date')
    if request.method=='POST' and 'Datewise' in request.POST:      
        for l in List:
            Loan = Loans.objects.get(pk=int(l))
            Installment = Installments.objects.filter(Loan=Loan).filter(Date_Paid=Date).order_by('Date_Due','-Installment_To_Be_Paid').first()
            x=str(Loan.Account.Client.Phone_no1)
            name = str(Loan.Account.Client.Name)
            Amount_Paid = str(Installment.Installment_Paid)    
            cid = str(Loan.Account.Client.pk) 
                
            from_num = 'whatsapp:+14155238886'
            to_num =  'whatsapp:+919810897802'
            TWILIO_ACCOUNT_SID='AC4d6c8a4366514eb2023d5bfec126db50'
            TWILIO_AUTH_TOKEN='cf743112770219fc1964b4b731beb6d5'
            # client = twilioClient(TWILIO_ACCOUNT_SID,TWILIO_AUTH_TOKEN)  
            client.messages.create(body='Ess Arr Finance: Hi '+name+' this is to confirm that we have recieved a deposit of Rs.'+Amount_Paid+' in your account having client id: '+cid+' and loan id: '+l+' Thank you!',from_=from_num,to=to_num)
            return HttpResponse('done')
            #response = sendPostRequest(URL, 'WTI5CKKSHCQX0R2DPS0NPCRELPIWAANG', '062SNUSN0LQX2ZMG', 'stage',x, 'essarr', 'ESSARR FINANCE : '+y+', Amount paid: '+ Amount_Paid + ' on Date:' + Date )
    elif request.method == 'POST' and 'CustomSms' in request.POST:
        message = request.POST.get('message')
        for i in List:
            Client = Clients.objects.get(pk =int(i))
            x=str(Client.Phone_no1)
            #response = sendPostRequest(URL, 'WTI5CKKSHCQX0R2DPS0NPCRELPIWAANG', '062SNUSN0LQX2ZMG', 'stage',x, 'essarr', 'ESSARR FINANCE :'+message  )

    return redirect('microfinance:home')

@login_required(login_url="/accounts/login/")
def ViewGuarantorDocs(request,pk):
    Guarantor = Guarantor_Documents.objects.filter(Guarantor_id = pk)
    return render(request,'microfinance/ViewGuarantorDocs.html',{'GDocs':Guarantor})

@login_required(login_url="/accounts/login/")
def ViewClientDocs(request,pk):
    ClientDocs = Documents.objects.filter(Client_id = pk)
    return render(request,'microfinance/ViewClientDocs.html',{'CDocs':ClientDocs})
    
@login_required(login_url="/accounts/login/")
def Total_Amount_Collected_Report(request):
    Date=request.POST.get('Date')
    Installment=Installments.objects.filter(Date_Paid=Date).filter(Installment_Paid__gt=0).order_by('Loan__Loan_Collector')
    Loan =Loans.objects.filter(Loan_Date=Date)
    pen =Penalty.objects.filter(Penalty_Paid_Date=Date)
    Total_File_Charge=0
    Total_Collection=0
    tot_pen = 0
    filec ={}
    for p in pen:
        tot_pen = tot_pen + p.Penalty_Paid
    for l in Loan:
        Total_File_Charge+=l.Principle_Amount*l.File_Charge_Percent/100
        filec[l.pk] = l.Principle_Amount*l.File_Charge_Percent/100
    for i in Installment:
        Total_Collection+=i.Installment_Paid    
    return render(request,'microfinance/Total_Amnt_Collected_Report.html',{'tot_pen':tot_pen,'Date':Date,'Inst':Installment,'Total_coll':Total_Collection,'file_charge':Total_File_Charge,'pen':pen,'Loan':Loan,'filec':filec})



def EditClient(request,pk):
    Client = Clients.objects.all().get(pk=pk)
    if request.method=='POST':  

        
        form=EditClientDetail(request.POST,request.FILES,instance=Client)
        if form.is_valid():
            
           
            form.save()
            
        return redirect('microfinance:clientdetail',pk=pk)
    else:
        form=EditClientDetail(instance=Client)
        return render(request,'microfinance/EditClient.html',{'form':form})

@login_required(login_url="/accounts/login/")
def Client_Detail_Pdf(request,pk):    
    Client =Clients.objects.get(pk=pk)
    Account =Accounts.objects.get(Client=Client)
    Loan = Loans.objects.filter(Account =Account).distinct()

    if request.method == "POST":
        
        return render(request,'microfinance/pdfs/clientform.html',{'Client':Client,'Account':Account,'Loan':Loan})
    else:        
        return render(request,'microfinance/Client_Detail.html',{'Client':Client,'Account':Account,'Loan':Loan})

@login_required(login_url="/accounts/login/")
def Home(request):
    loan=Loans.objects.filter(reminder__lte=datetime.now()).filter(Status=False).distinct()    
    dic={}
    for i in Loans.objects.all().filter(reminder__lt=datetime.now()).filter(Status=False).distinct():
        if i.reminder < datetime.now().date():
            if i.installments_set.order_by('-Date_Due').first().Date_Due <datetime.now().date():
                i.reminder=datetime.now().date()            
            
            else:
                if i.installments_set.filter(Date_Due__gt=datetime.now()).filter(Date_Paid__isnull=True).order_by('Date_Paid').first() is not None:
                    i.Reminder= i.installments_set.filter(Date_Due__gt=datetime.now()).filter(Date_Paid__isnull=True).order_by('Date_Paid').first().Date_Due
            i.Remark ='None'
            i.save()
    for l in loan:
        i = Installments.objects.all().filter(Loan_id =l.pk).filter(Date_Due__lte=datetime.now()).filter(Installment_Due__gt=0).filter(Date_Paid__isnull=True).aggregate(Sum('Installment_Due')) 
        
        j= Installments.objects.all().filter(Loan_id =l.pk).filter(Date_Due__lte=datetime.now()).filter(Installment_Due=0).filter(Date_Paid__isnull=True).aggregate(Sum('Installment_To_Be_Paid'))
        if j['Installment_To_Be_Paid__sum'] and i['Installment_Due__sum']:
            i['Installment_Due__sum']+=j['Installment_To_Be_Paid__sum']
        if j['Installment_To_Be_Paid__sum'] and not i['Installment_Due__sum']:
            i['Installment_Due__sum']=j['Installment_To_Be_Paid__sum']
        if not j['Installment_To_Be_Paid__sum'] and not i['Installment_Due__sum']:
            i['Installment_Due__sum']=0
        dic[l.pk]=i['Installment_Due__sum']
    staff =Staff.objects.all().distinct()
    if request.method == 'POST':
        user_filter = LoanFilter(request.POST, queryset=loan)
        return render(request,'microfinance/Homepage.html',{'month':timezone.now().date().month,'loan':loan,'filter': user_filter,'users':staff,'dic':dic})
    else:
        return render(request,'microfinance/Homepage.html',{'month':timezone.now().date().month,'users':staff})


@login_required(login_url="/accounts/login/")
def DeleteIntsallment(request):
    if request.user.is_superuser: 
        List = request.POST.getlist('Check')
        for l in List:
            x=Installments.objects.filter(pk=l).delete()
        return redirect('microfinance:home')
        
        
    else:
        return HttpResponse('you dont have access to this page. Contact admin')

@login_required(login_url="/accounts/login/")
def EditInstallment(request,pk):
    if request.user.is_superuser: 
        Installment =Installments.objects.get(pk=pk)        
        if request.method=='POST':
            form=EditInstallmentDetail(request.POST,request.FILES)
            instance=form.save(commit=False)
            if form.is_valid():            
                instance.save()
                try:
                    Penal=Penalty.objects.get(Installment=Installment)
                    Penal.delete()
                    Installment.delete()
                except:
                    Installment.delete()
            return redirect('microfinance:loandetail',pk=instance.Loan.pk)
        else:
            form = form=EditInstallmentDetail(instance=Installment)
            return render(request,'microfinance/EditIInstallment.html',{'form':form})
            
    else:
        return HttpResponse('you dont have access to this page. Contact admin')

@login_required(login_url="/accounts/login/")
def InstallmentList(request,pk):
    if request.user.is_superuser: 
        loan=Loans.objects.get(pk=pk)
        Installment =Installments.objects.filter(Loan=loan)
        return render(request,'microfinance/IntsallmentList.html',{'Installment':Installment,'loan':loan})
    else:
        return HttpResponse('you dont have access to this page. Contact admin')

@login_required(login_url="/accounts/login/")
def AddInstallment(request,pk):
    if request.user.is_superuser:
        loan=Loans.objects.get(pk=pk)
        if request.method=="POST":
            form=AddInstallments(request.POST,request.FILES)
            instance=form.save(commit=False)
            instance.Loan=loan
            if form.is_valid():
                instance.save()
            return redirect('microfinance:loandetail',pk=instance.Loan.pk)
        else:
            form = form=AddInstallments()
            return render(request,'microfinance/EditIInstallment.html',{'form':form})
            
    else:
        return HttpResponse('you dont have access to this page. Contact admin')


@login_required(login_url="/accounts/login/")
def Week_Chart_List(request):
    Staff_pk=int(request.POST.get('name'))
    Weekday = int(request.POST.get('Weekday'))  
    sdate= (datetime.now() - timedelta(days=1)).date()
    edate= (datetime.now() - timedelta(days=7)).date()
    dd = [sdate - timedelta(days=x) for x in range((sdate-edate).days)]
    lon = Loans.objects.none()
    if Staff_pk !=0 and Weekday !=0:
        Loan=Loans.objects.all().filter(Loan_Collector_id=Staff_pk).filter(Status=False).filter(Frequency=2).filter(First_Due_Date__week_day = Weekday)
        lon = Loans.objects.all().filter(Loan_Collector_id=Staff_pk).filter(Status=False).filter(Frequency=2).exclude(First_Due_Date__week_day = Weekday)
    elif Staff_pk != 0 and Weekday == 0:
        Loan=Loans.objects.all().filter(Loan_Collector_id=Staff_pk).filter(Status=False).filter(Frequency=2)
   
    elif Staff_pk == 0 and Weekday != 0:
        Loan=Loans.objects.all().filter(Status=False).filter(Frequency=2).filter(First_Due_Date__week_day = Weekday)
        lon=Loans.objects.all().filter(Status=False).filter(Frequency=2).exclude(First_Due_Date__week_day = Weekday)
    else:
        Loan=Loans.objects.all().filter(Status=False).filter(Frequency=2)

    dic ={}
    dic2 ={}
    Dic1={0:0,1:0,2:0,3:0,4:0,5:0,6:0}
    Dic2={0:0,1:0,2:0,3:0,4:0,5:0,6:0} 
    Def1=0
    Def2=0
    x=Loans.objects.none()
    if lon:
        for i in dd:
            for j in lon.filter(First_Due_Date__week_day = (i.isoweekday()%7)+1):
                if j.installments_set.filter(Date_Paid__isnull=False).order_by('-Date_Paid','-Date_Due').first():
                    if j.installments_set.filter(Date_Paid__isnull=False).order_by('-Date_Paid','-Date_Due').first().Date_Paid < i:
                        x|= lon.filter(pk=j.pk)     
                else:   
                    x|= lon.filter(pk=j.pk)  
                    
    if x:   
        for l in x:
        
            Def1 = Def1 + l.installments_set.first().Installment_Due
            totalPending =0
            inst =Installments.objects.filter(Loan=l).filter(Q(Date_Paid__lte=datetime.now())|Q(Date_Due__lte=datetime.now())).distinct()
            for i in inst:
                            
                totalPending  = totalPending + (i.Installment_Due - i.Installment_Paid)
            dic2[l.pk]=totalPending
            Def2 = Def2 + totalPending
            if totalPending<= 0:
                x=x.exclude(pk=l.pk)
    for l in Loan:

        Dic1[int(l.installments_set.first().Date_Due.weekday())] = Dic1[int(l.installments_set.first().Date_Due.weekday())] + l.installments_set.first().Installment_Due
        totalPending =0
        inst =Installments.objects.filter(Loan=l).filter(Q(Date_Paid__lte=datetime.now())|Q(Date_Due__lte=datetime.now())).distinct()
        for i in inst:
            Dic2[int(i.Date_Due.weekday())] =Dic2[int(i.Date_Due.weekday())] + (i.Installment_Due-i.Installment_Paid)             
            totalPending  = totalPending + (i.Installment_Due - i.Installment_Paid)
        dic[l.pk]=totalPending
    
    if int(Weekday) == 0:               
        return render(request,'microfinance/Week_Chart.html',{'Loan':Loan,'dic':dic,'Staff':Staff_pk,'Total':Dic1,'TotalPen':Dic2})
    else:
        
        return render(request,'microfinance/week_chart2.html',{'Loan':Loan,'dic':dic,'dic2':dic2,'Staff':Staff_pk,'Total':Dic1,'TotalPen':Dic2,'Def1':Def1,'Def2':Def2,'lon':x})
   


@login_required(login_url="/accounts/login/")
def EditLoan(request,pk):
    print("=" * 50)
    print("EDITLOAN VIEW CALLED!")
    print(f"Loan ID: {pk}")
    print(f"Request method: {request.method}")
    print(f"User: {request.user}")
    print(f"Is superuser: {request.user.is_superuser}")
    print("=" * 50)
    if request.user.is_superuser: 
        Loan=Loans.objects.get(pk=pk)
        acc=Loan.Account.pk
        gk=Loan.Guarantor.pk
                
        if request.method=='POST' and 'edit' in request.POST:
            print("Edit button clicked - showing form")
            form=EditLoanDetail(instance=Loan)
            return render(request,'microfinance/EditLoan.html',{'form':form})
        if request.method=='POST' and 'changeLoan' in request.POST:
            print("ChangeLoan button clicked - processing form")  
            print(f"POST data: {request.POST}")
            form=EditLoanDetail(request.POST, instance=Loan)
            if form.is_valid():
                # Store the original first due date to check if it changed
                original_first_due_date = Loan.First_Due_Date
                print(f"=== INSTALLMENT UPDATE DEBUG ===")
                print(f"Original first due date: {original_first_due_date} (type: {type(original_first_due_date)})")
                
                # Get the new first due date from the form data
                new_first_due_date = form.cleaned_data.get('First_Due_Date')
                print(f"New first due date: {new_first_due_date} (type: {type(new_first_due_date)})")
                
                # Also check the initial form data to see what the original value was
                initial_first_due_date = request.POST.get('initial-First_Due_Date')
                print(f"Initial first due date from form: {initial_first_due_date}")
                
                # Update the existing loan with new values
                form.save()
                print(f"Form saved successfully")
                
                # Check if first due date actually changed
                # Convert initial date string to date object for comparison
                from datetime import datetime
                if initial_first_due_date:
                    initial_date_obj = datetime.strptime(initial_first_due_date, '%Y-%m-%d').date()
                else:
                    initial_date_obj = original_first_due_date
                
                print(f"Comparing: {initial_date_obj} != {new_first_due_date} = {initial_date_obj != new_first_due_date}")
                if initial_date_obj != new_first_due_date:
                    print(f"FIRST DUE DATE CHANGED - UPDATING INSTALLMENTS")
                    # Delete existing installments and recreate them with new dates
                    deleted_count = Installments.objects.filter(Loan=Loan).count()
                    print(f"Deleting {deleted_count} existing installments")
                    Installments.objects.filter(Loan=Loan).delete()
                    
                    # Recreate installments with updated schedule
                    Installment = (Loan.Principle_Amount + (Loan.Principle_Amount/100*Loan.Intrest_Rate))/Loan.No_Of_Installments
                    print(f"Calculated installment amount: {Installment}")
                    print(f"Loan frequency: {Loan.Frequency}")
                    print(f"Number of installments: {Loan.No_Of_Installments}")
                    
                    # Create first installment
                    if Loan.Frequency != 2:
                        Inst = round(Installment, 1)
                        print(f"Creating first installment (non-weekly): Amount={Inst}, Date={new_first_due_date}")
                        Installments_Inst = Installments(
                            Installment_Paid=0, 
                            Loan=Loan, 
                            Date_Due=new_first_due_date, 
                            Installment_Due=Inst,
                            Installment_To_Be_Paid=Inst,
                            Pending_Amount=Inst
                        )
                    else:
                        Inst = round(Installment, 1)
                        print(f"Creating first installment (weekly): Amount={round(Inst*7)}, Date={new_first_due_date}")
                        Installments_Inst = Installments(
                            Installment_Paid=0, 
                            Loan=Loan, 
                            Date_Due=new_first_due_date, 
                            Installment_Due=round(Inst*7),
                            Installment_To_Be_Paid=round(Inst*7),
                            Pending_Amount=round(Inst*7)
                        )
                    Installments_Inst.save()
                    print(f"First installment saved with ID: {Installments_Inst.pk}")
                    
                    # Create remaining installments based on frequency
                    if Loan.Frequency == 1:  # Daily
                        print(f"Creating {Loan.No_Of_Installments - 1} additional daily installments")
                        Date_Due = new_first_due_date 
                        for i in range(1, Loan.No_Of_Installments):
                            Inst = round(Installment, 1)
                            Date_Due = Date_Due + timedelta(days=1)
                            Installments_Inst = Installments(
                                Installment_Paid=0, 
                                Loan=Loan,
                                Date_Due=Date_Due, 
                                Installment_Due=round(Installment, 1),
                                Installment_To_Be_Paid=round(Installment, 1),
                                Pending_Amount=round(Installment, 1)
                            )
                            Installments_Inst.save()
                    elif Loan.Frequency == 2:  # Weekly
                        Date_Due = new_first_due_date 
                        Extra_Days = Loan.No_Of_Installments % 7
                        for i in range(1, int(Loan.No_Of_Installments/7)):
                            Inst = Installment
                            Date_Due = Date_Due + timedelta(days=7)
                            Installments_Inst = Installments(
                                Installment_Paid=0, 
                                Loan=Loan, 
                                Date_Due=Date_Due, 
                                Installment_Due=round(Inst*7),
                                Installment_To_Be_Paid=round(Inst*7),
                                Pending_Amount=round(Inst*7)
                            )
                            Installments_Inst.save()
                        if Extra_Days > 0:
                            Inst = Installment
                            Date_Due = Date_Due + timedelta(days=Extra_Days)
                            Installments_Inst = Installments(
                                Installment_Paid=0, 
                                Loan=Loan,
                                Date_Due=Date_Due, 
                                Installment_Due=round(Inst*Extra_Days),
                                Installment_To_Be_Paid=round(Inst*Extra_Days),
                                Pending_Amount=round(Inst*Extra_Days)
                            )
                            Installments_Inst.save()
                    elif Loan.Frequency == 3:  # Monthly
                        Date_Due = new_first_due_date 
                        for i in range(1, Loan.No_Of_Installments):
                            Inst = round(Installment, 1)
                            Date_Due = Date_Due + relativedelta(months=1)
                            Installments_Inst = Installments(
                                Installment_Paid=0, 
                                Loan=Loan,
                                Date_Due=Date_Due, 
                                Installment_Due=round(Installment, 1),
                                Installment_To_Be_Paid=round(Installment, 1),
                                Pending_Amount=round(Installment, 1)
                            )
                            Installments_Inst.save()
                    
                    # Final count check
                    final_count = Installments.objects.filter(Loan=Loan).count()
                    print(f"Final installment count: {final_count}")
                    print(f"=== INSTALLMENT UPDATE COMPLETE ===")
                
                return redirect('microfinance:clientdetail', pk=Loan.Account.Client.pk)
            else:
                # Form is not valid, show errors
                print(f"Form is not valid. Errors: {form.errors}")
                return render(request,'microfinance/EditLoan.html',{'form':form})
   
        if 'del' in request.POST:
            Pen =Penalty.objects.filter(Loan=Loan).delete()
            inst=Installments.objects.filter(Loan=Loan).delete()
            Loan.delete()
            return redirect('microfinance:clientdetail' ,pk=Loan.Account.Client.pk)
        
        # Default case: show the edit form
        form=EditLoanDetail(instance=Loan)
        return render(request,'microfinance/EditLoan.html',{'form':form})
                
    else:
        print(f"User {request.user} is not a superuser - access denied")
        return HttpResponse('you dont have access to this page. Contact admin')


@login_required(login_url="/accounts/login/")
def optimizeimg(request):
    Client =Clients.objects.all()
    for j in Client:
        try:
           
            # image = Image.open(i.Image.path)
            # image.save(i.Image.path,quality=20,optimize=True)
            i = Image.open(j.Image)
            thumb_io = BytesIO()
            i.save(thumb_io, format='JPEG', quality=20)
            inmemory_uploaded_file = InMemoryUploadedFile(thumb_io, None, 'foo.jpeg', 
                                              'image/jpeg', thumb_io.tell(), None)
            j.Image = inmemory_uploaded_file
            j.save()
        except:
            print(j.pk)
    return HttpResponse('Images OP')



@login_required(login_url="/accounts/login/")
def temporary(request):
    inst =  Installments.objects.filter(Date_Due__lte ="2020-10-24").distinct()
    inst2 =  Installments.objects.filter(Date_Paid__lte ="2020-10-24").distinct()
    Loan = Loans.objects.filter(installments__in=inst).distinct()
    Amnt_Collected = {}
    Amnt_To_Be_Collected = {}
    AmntCollected=AmntToBeCollected=0
    inst3 = Installments.objects.filter(Loan__in = Loan).exclude(id__in=inst).distinct()
    inst4 = Installments.objects.filter(Loan__in = Loan).exclude(id__in=inst2).distinct()
    Amnt_Collected2 = {}
    Amnt_To_Be_Collected2 = {}
    AmntCollected2=AmntToBeCollected2=0    
    amnt_pen ={}
    for i in Loan:
        Amnt_To_Be_Collected[i.pk]=inst.filter(Loan = i).aggregate(Sum('Installment_Due')) 
        Amnt_Collected[i.pk]=inst2.filter(Loan = i).aggregate(Sum('Installment_Paid'))
        if Amnt_To_Be_Collected[i.pk]["Installment_Due__sum"]:
            AmntToBeCollected = AmntToBeCollected + Amnt_To_Be_Collected[i.pk]["Installment_Due__sum"] 
            amnt_pen[i.pk]=Amnt_To_Be_Collected[i.pk]["Installment_Due__sum"]
        if Amnt_Collected[i.pk]["Installment_Paid__sum"]:
            AmntCollected = AmntCollected + Amnt_Collected[i.pk]["Installment_Paid__sum"]
            amnt_pen[i.pk]-= Amnt_Collected[i.pk]["Installment_Paid__sum"]
        Amnt_To_Be_Collected2[i.pk]=inst3.filter(Loan = i).aggregate(Sum('Installment_Due')) 
        Amnt_Collected2[i.pk]=inst4.filter(Loan = i).aggregate(Sum('Installment_Paid'))
        if Amnt_Collected2[i.pk]["Installment_Paid__sum"]:
            AmntCollected2 = AmntCollected2 + Amnt_Collected2[i.pk]["Installment_Paid__sum"]
        if Amnt_To_Be_Collected2[i.pk]["Installment_Due__sum"]:
            AmntToBeCollected2 = AmntToBeCollected2 + Amnt_To_Be_Collected2[i.pk]["Installment_Due__sum"] 
            amnt_pen[i.pk]+=Amnt_To_Be_Collected2[i.pk]["Installment_Due__sum"]
    Loan2 = Loan.filter(Status =True)
    Loan = Loan.exclude(id__in =Loan2)
    return render(request,'microfinance/temp.html',{'amnt_pen':amnt_pen,'amnt_collected':Amnt_Collected,'amnt_collected2':Amnt_Collected2,'Loan':Loan,'amntcollected':AmntCollected,'amnttobecollected':AmntToBeCollected,'amnt_to_be_collected':Amnt_To_Be_Collected,'amnttobecollected2':AmntToBeCollected2,'amntcollected2':AmntCollected2,'Loan2':Loan2})

   
def _perform_calculation(loan):
    """
    Core penalty calculation logic - optimized for performance.
    """
    today = timezone.now().date()
    
    # Single query for all installments
    installments = Installments.objects.filter(
        Loan=loan,
        Installment_Due__gt=0
    ).values('Date_Due', 'Installment_Due').order_by('Date_Due')
    
    # Single query for all payments
    payments = Payments.objects.filter(
        Loan=loan,
        Payment_Type=1
    ).values('Date_Paid', 'Amount_Paid').order_by('Date_Paid')
    
    # Convert to lists for faster processing
    installments_list = list(installments)
    payments_list = list(payments)
    
    if not installments_list:
        return _get_default_result()
    
    # Use individual penalty approach for better debugging
    return _calculate_individual_penalties(loan, installments_list, payments_list, today)


def calculate_penalties(loan):
        """
        Calculate penalties for a loan - optimized for speed.
        """        
        try:
            result = _perform_calculation(loan)
            return result
            
        except Exception as e:
            print(f"Error calculating penalties for loan {loan.id}: {str(e)}")
            return _get_default_result()
            
        
    

def _calculate_individual_penalties_new(loan, installments, payments, today):
    """
    Calculate penalties by creating individual penalty entries for each overdue installment.
    This makes debugging easier and provides detailed breakdown in the UI.
    """
    print(f"=== INDIVIDUAL PENALTY CALCULATION ===")
    print(f"Today's date: {today}")
    print(f"Processing {len(installments)} installments")
    
    penalty_periods = []
    total_outstanding = Decimal('0')
    
    # Create individual penalties for each overdue installment
    # First, sort payments by date to process them chronologically
    sorted_payments = sorted(payments, key=lambda x: x['Date_Paid'])
    
    # Track remaining payment amounts for allocation
    payment_allocations = []
    for payment in sorted_payments:
        payment_allocations.append({
            'date': payment['Date_Paid'],
            'amount': Decimal(str(payment['Amount_Paid'])),
            'remaining': Decimal(str(payment['Amount_Paid']))
        })
    
    # Process installments in chronological order
    sorted_installments = sorted(installments, key=lambda x: x['Date_Due'])
    
    for inst in sorted_installments:
        due_date = inst['Date_Due']
        amount = Decimal(str(inst['Installment_Due']))
        
        if due_date < today:
            remaining_amount = amount
            current_date = due_date
            
            # Process payments chronologically to create penalty periods
            for payment_allocation in payment_allocations:
                payment_date = payment_allocation['date']
                available_amount = payment_allocation['remaining']
                
                # If payment is after current date and we have remaining amount
                if payment_date > current_date and remaining_amount > 0 and available_amount > 0:
                    # Create penalty period from current_date to payment_date
                    if current_date < payment_date:
                        days_overdue = (payment_date - current_date).days
                        if days_overdue > 0:
                            penalty_periods.append({
                                'start_date': current_date,
                                'end_date': payment_date,
                                'amount': remaining_amount,
                                'days': days_overdue
                            })
                            total_outstanding += remaining_amount
                            print(f"Penalty period: {current_date} to {payment_date}, amount: {remaining_amount}, days: {days_overdue}")
                    
                    # Allocate payment to this installment
                    allocation_amount = min(remaining_amount, available_amount)
                    remaining_amount -= allocation_amount
                    payment_allocation['remaining'] -= allocation_amount
                    
                    # Update current date to payment date
                    current_date = payment_date
                    
                    # If installment is fully paid, break
                    if remaining_amount <= 0:
                        break
            
            # If installment is still not fully paid, create penalty until today
            if remaining_amount > 0 and current_date < today:
                days_overdue = (today - current_date).days
                if days_overdue > 0:
                    penalty_periods.append({
                        'start_date': current_date,
                        'end_date': today,
                        'amount': remaining_amount,
                        'days': days_overdue
                    })
                    total_outstanding += remaining_amount
                    print(f"Final penalty period: {current_date} to {today}, amount: {remaining_amount}, days: {days_overdue}")
        else:
            print(f"Future installment: {due_date}, amount: {amount}")
    
    # Apply payments to reduce outstanding amounts
    total_payments = Decimal('0')
    for payment in payments:
        payment_amount = Decimal(str(payment['Amount_Paid']))
        total_payments += payment_amount
        print(f"Payment: {payment['Date_Paid']}, amount: {payment_amount}")
    
    print(f"Total outstanding: {total_outstanding}")
    print(f"Total payments: {total_payments}")
    print(f"Created {len(penalty_periods)} individual penalty periods")
    
    # Calculate total penalty
    total_penalty = _calculate_total_penalty(loan, penalty_periods)
    
    # Delete existing penalties and create new ones
    Penalty.objects.filter(Loan=loan).delete()
    for p in penalty_periods:
        if p['days'] > 0:
            # Calculate penalty amount based on days overdue and penalty percentage (default 2%)
            # Use penalty percentage from Penalty model default (2%) instead of interest rate
            penalty_percentage = Decimal('2')  # Default penalty percentage
            penalty_amount = p['amount'] * penalty_percentage / Decimal('100') * p['days']
            p['penalty'] = penalty_amount
            
            getOrCreatePenalties(loan, p['start_date'], p['end_date'], p['amount'], penalty_amount)
            print(f"Created penalty: {p['start_date']} to {p['end_date']}, amount: {p['amount']}, penalty: {penalty_amount} (2% per day)")
    
    return {
        'total_penalty': total_penalty,
        'current_outstanding': max(total_outstanding - total_payments, Decimal('0')),
        'penalty_details': penalty_periods,
        'summary': {
            'total_installments': len(installments),
            'overdue_installments': len(penalty_periods),
            'total_outstanding': total_outstanding,
            'total_payments': total_payments
        }
    }

def _calculate_individual_penalties(loan, installments, payments, today):
    return _calculate_individual_installment_penalties(loan, installments, payments, today)

    """
    Calculate penalties by creating individual penalty entries for each overdue installment.
    This makes debugging easier and provides detailed breakdown in the UI.
    """
    print(f"=== INDIVIDUAL PENALTY CALCULATION ===")
    print(f"Today's date: {today}")
    print(f"Processing {len(installments)} installments")
    
    penalty_periods = []
    total_outstanding = Decimal('0')
    
    # Create individual penalties for each overdue installment
    # First, sort payments by date to process them chronologically
    sorted_payments = sorted(payments, key=lambda x: x['Date_Paid'])
    
    # Track remaining payment amounts for allocation
    payment_allocations = []
    for payment in sorted_payments:
        payment_allocations.append({
            'date': payment['Date_Paid'],
            'amount': Decimal(str(payment['Amount_Paid'])),
            'remaining': Decimal(str(payment['Amount_Paid']))
        })
    
    # Process installments in chronological order
    sorted_installments = sorted(installments, key=lambda x: x['Date_Due'])
    
    for inst in sorted_installments:
        due_date = inst['Date_Due']
        amount = Decimal(str(inst['Installment_Due']))
        
        if due_date < today:
            remaining_amount = amount
            current_date = due_date
            
            # Process payments chronologically to create penalty periods
            for payment_allocation in payment_allocations:
                payment_date = payment_allocation['date']
                available_amount = payment_allocation['remaining']
                
                # If payment is after current date and we have remaining amount
                if payment_date > current_date and remaining_amount > 0 and available_amount > 0:
                    # Create penalty period from current_date to payment_date
                    if current_date < payment_date:
                        days_overdue = (payment_date - current_date).days
                        if days_overdue > 0:
                            penalty_periods.append({
                                'start_date': current_date,
                                'end_date': payment_date,
                                'amount': remaining_amount,
                                'days': days_overdue
                            })
                            total_outstanding += remaining_amount
                            print(f"Penalty period: {current_date} to {payment_date}, amount: {remaining_amount}, days: {days_overdue}")
                    
                    # Allocate payment to this installment
                    allocation_amount = min(remaining_amount, available_amount)
                    remaining_amount -= allocation_amount
                    payment_allocation['remaining'] -= allocation_amount
                    
                    # Update current date to payment date
                    current_date = payment_date
                    
                    # If installment is fully paid, break
                    if remaining_amount <= 0:
                        break
            
            # If installment is still not fully paid, create penalty until today
            if remaining_amount > 0 and current_date < today:
                days_overdue = (today - current_date).days
                if days_overdue > 0:
                    penalty_periods.append({
                        'start_date': current_date,
                        'end_date': today,
                        'amount': remaining_amount,
                        'days': days_overdue
                    })
                    total_outstanding += remaining_amount
                    print(f"Final penalty period: {current_date} to {today}, amount: {remaining_amount}, days: {days_overdue}")
        else:
            print(f"Future installment: {due_date}, amount: {amount}")
    
    # Apply payments to reduce outstanding amounts
    total_payments = Decimal('0')
    for payment in payments:
        payment_amount = Decimal(str(payment['Amount_Paid']))
        total_payments += payment_amount
        print(f"Payment: {payment['Date_Paid']}, amount: {payment_amount}")
    
    print(f"Total outstanding: {total_outstanding}")
    print(f"Total payments: {total_payments}")
    print(f"Created {len(penalty_periods)} individual penalty periods")
    
    # Calculate total penalty
    total_penalty = _calculate_total_penalty(loan, penalty_periods)
    
    # Delete existing penalties and create new ones
    Penalty.objects.filter(Loan=loan).delete()
    for p in penalty_periods:
        if p['days'] > 0:
            # Calculate penalty amount based on days overdue and penalty percentage (default 2%)
            # Use penalty percentage from Penalty model default (2%) instead of interest rate
            penalty_percentage = Decimal('2')  # Default penalty percentage
            penalty_amount = p['amount'] * penalty_percentage / Decimal('100') * p['days']
            p['penalty'] = penalty_amount
            
            getOrCreatePenalties(loan, p['start_date'], p['end_date'], p['amount'], penalty_amount)
            print(f"Created penalty: {p['start_date']} to {p['end_date']}, amount: {p['amount']}, penalty: {penalty_amount} (2% per day)")
    
    return {
        'total_penalty': total_penalty,
        'current_outstanding': max(total_outstanding - total_payments, Decimal('0')),
        'penalty_details': penalty_periods,
        'summary': {
            'total_installments': len(installments),
            'overdue_installments': len(penalty_periods),
            'total_outstanding': total_outstanding,
            'total_payments': total_payments
        }
    }

def _calculate_with_running_balance(loan, installments, payments, today):
    """
    Calculate penalties using running balance approach.
    Most efficient method for real-time calculation.
    """
    # Create date-based maps for O(1) lookup
    installment_map = {}
    payment_map = {}
    
    # Build installment map
    for inst in installments:
        date_key = inst['Date_Due']
        installment_map[date_key] = inst['Installment_Due']
    
    # Build payment map
    for payment in payments:
        date_key = payment['Date_Paid']
        if date_key not in payment_map:
            payment_map[date_key] = Decimal('0')
        payment_map[date_key] += Decimal(str(payment['Amount_Paid']))
    
    # Get all significant dates
    all_dates = set(installment_map.keys()) | set(payment_map.keys()) | {today}
    sorted_dates = sorted(all_dates)
    
    # Calculate running balance and penalty periods
    return _process_date_sequence(loan,sorted_dates, installment_map, payment_map, today)

def _process_date_sequence( loan,sorted_dates, installment_map, payment_map, today):
    """
    Process dates in sequence to calculate penalties.
    """
    running_balance = Decimal('0')
    penalty_periods = []
    current_penalty_start = None
    current_penalty_amount = Decimal('0')
    
    for date in sorted_dates:
        # Add installments due on this date
        if date in installment_map:
            running_balance += Decimal(str(installment_map[date]))
            
            # Start penalty period if overdue and no existing penalty
            if date < today and current_penalty_start is None and running_balance > 0:
                current_penalty_start = date
                current_penalty_amount = running_balance
                print(f"Started penalty period: {date}, amount: {current_penalty_amount}")
            # If we already have a penalty period and this installment is overdue, add to the amount
            elif date < today and current_penalty_start is not None:
                current_penalty_amount += Decimal(str(installment_map[date]))
                print(f"Added to penalty period: {date}, installment: {installment_map[date]}, total: {current_penalty_amount}")
        
        # Apply payments made on this date
        if date in payment_map:
            running_balance -= payment_map[date]
            
            # Handle penalty period changes
            if current_penalty_start is not None:
                if running_balance <= 0:
                    # Payment covers all outstanding - close penalty period
                    penalty_periods.append({
                        'start_date': current_penalty_start,
                        'end_date': date,
                        'amount': current_penalty_amount,
                        'days': (date - current_penalty_start).days
                    })
                    current_penalty_start = None
                    current_penalty_amount = Decimal('0')
                else:
                    # Partial payment - close current period, start new one
                    penalty_periods.append({
                        'start_date': current_penalty_start,
                        'end_date': date,
                        'amount': current_penalty_amount,
                        'days': (date - current_penalty_start).days
                    })
                    current_penalty_start = date
                    current_penalty_amount = running_balance
    
    # Close any remaining penalty period
    if current_penalty_start is not None and current_penalty_start < today:
        penalty_periods.append({
            'start_date': current_penalty_start,
            'end_date': today,
            'amount': current_penalty_amount,
            'days': (today - current_penalty_start).days
        })
    
    # Calculate total penalty
    total_penalty = _calculate_total_penalty(loan,penalty_periods)
    Penalty.objects.filter(Loan=loan).delete()
    print(f"Creating {len(penalty_periods)} penalty periods:")
    for p in penalty_periods:
        print(f"Penalty: {p['start_date']} to {p['end_date']}, amount: {p['amount']}, penalty: {p['penalty']}, days: {p['days']}")
        if p['days']>0:
            getOrCreatePenalties(loan,p['start_date'],p['end_date'],p['amount'],p['penalty'])    
        else: removePenalty(loan,p['start_date'])
    print([p for p in penalty_periods if p['days'] > 0])
    return {
        'total_penalty': total_penalty,
        'current_outstanding': max(running_balance, Decimal('0')),
        'penalty_details': penalty_periods,
        'summary': {
            'overdue_installments': len([p for p in penalty_periods if p['days'] > 0]),
            'days_overdue': max([p['days'] for p in penalty_periods], default=0),
            'penalty_rate': _get_penalty_rate(loan)
        }
    }

def _calculate_total_penalty( loan,penalty_periods):
    """
    Calculate total penalty amount from periods.
    """
    total_penalty = Decimal('0')
    penalty_rate = _get_penalty_rate(loan)
    daily_rate = penalty_rate / 100
    
    for period in penalty_periods:
        if period['days'] > 0:
            period_penalty = period['amount'] * daily_rate * period['days']
            period['penalty'] = period_penalty
            total_penalty += period_penalty
    
    return total_penalty

def _get_penalty_rate(loan):
    """Get penalty rate for the loan."""
    penalty = Penalty.objects.filter(Loan=loan)
    return Decimal(str(penalty[0].Percent)) if penalty else Decimal('2')  # Default 2% annual

def _get_default_result():
    """Return default result for error cases."""
    return {
        'total_penalty': Decimal('0'),
        'current_outstanding': Decimal('0'),
        'penalty_details': [],
        'summary': {
            'overdue_installments': 0,
            'days_overdue': 0,
            'penalty_rate': Decimal('2')
        }
    }

# Batch processing for multiple loans
def batch_calculate_penalties(loan_ids):
    """
    Calculate penalties for multiple loans efficiently.
    """
    results = {}
    
    # Use select_related/prefetch_related for better performance
    loans = Loans.objects.filter(id__in=loan_ids).select_related()
    
    for loan in loans:
        try:
            results[loan.id] = calculate_penalties(loan)
        except Exception as e:
            print(f"Error calculating penalties for loan {loan.id}: {str(e)}")
            results[loan.id] = None
    
    return results

@login_required(login_url="/accounts/login/")
def dashboard(request):
    """
    Dashboard view with comprehensive financial insights and date range filtering
    """
    today = timezone.now().date()
    
    # Handle date range filtering
    selected_range = request.GET.get('date_range', 'today')
    start_date = None
    end_date = None
    
    if selected_range == 'today':
        start_date = end_date = today
    elif selected_range == 'last_week':
        end_date = today
        start_date = today - timedelta(days=7)
    elif selected_range == 'last_month':
        end_date = today
        start_date = today - timedelta(days=30)
    elif selected_range == 'custom':
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                # Default to today if invalid dates
                start_date = end_date = today
        else:
            # Default to today if no custom dates provided
            start_date = end_date = today
    else:
        # Default case
        start_date = end_date = today
    
    # Ensure start_date is not after end_date
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    
    # Calculate filtered days
    filtered_days = (end_date - start_date).days + 1
    
    # Get active loans only
    active_loans = Loans.objects.filter(Status=False)
    
    # === PERIOD-BASED METRICS ===
    
    # 1. Collections in the selected period
    period_payments = Payments.objects.filter(
        Loan__in=active_loans,
        Date_Paid__range=[start_date, end_date],
        Payment_Type=1  # Installment payments
    )
    amount_collected_period = period_payments.aggregate(
        total=Sum('Amount_Paid')
    )['total'] or 0
    
    # 2. Amount due in the selected period
    period_installments = Installments.objects.filter(
        Loan__in=active_loans,
        Date_Due__range=[start_date, end_date],
        Installment_Due__gt=0
    )
    amount_due_period = period_installments.aggregate(
        total=Sum('Installment_Due')
    )['total'] or 0
    
    # 3. Clients with dues in the period
    clients_due_period = period_installments.values_list(
        'Loan__Account__Client', flat=True
    ).distinct()
    clients_due_period_count = len(clients_due_period)
    
    # 4. Penalty collections in the period
    penalty_collected_period = Payments.objects.filter(
        Loan__in=active_loans,
        Date_Paid__range=[start_date, end_date],
        Payment_Type=2  # Penalty payments
    ).aggregate(total=Sum('Amount_Paid'))['total'] or 0
    
    # 5. File charges from new loans in the period
    period_loans = active_loans.filter(
        Loan_Date__range=[start_date, end_date]
    )
    loans_created_period = period_loans.count()
    
    # Total loan amount disbursed in the period
    total_loan_amount_period = period_loans.aggregate(
        total=Sum('Principle_Amount')
    )['total'] or 0
    
    file_charges_period = sum(
        (loan.Principle_Amount * loan.File_Charge_Percent / 100) 
        for loan in period_loans
    )
    
    # 6. Interest earned in the period (approximate calculation)
    interest_earned_period = 0
    for payment in period_payments:
        # Calculate interest portion based on loan's interest rate
        principal_portion = payment.Amount_Paid / (1 + (payment.Loan.Intrest_Rate / 100))
        interest_portion = payment.Amount_Paid - principal_portion
        interest_earned_period += interest_portion
    
    # === PERFORMANCE METRICS ===
    
    # Collection efficiency for the period
    period_collection_efficiency = 0
    if amount_due_period > 0:
        period_collection_efficiency = (amount_collected_period / amount_due_period) * 100
    
    # Net performance (collected - due)
    period_net_performance = amount_collected_period - amount_due_period
    
    # Daily average collection (average amount collected per day in the selected period)
    daily_average_collection = amount_collected_period / filtered_days if filtered_days > 0 else 0
    
    # Collection rate
    period_collection_rate = period_collection_efficiency
    
    # === DEFAULTERS (NEEDED FOR PERFORMANCE METRICS) ===
    
    # Use a more efficient query to get defaulters with related data
    overdue_installments = Installments.objects.filter(
        Loan__in=active_loans,
        Installment_Due__gt=0,
        Date_Due__lt=today
    ).select_related('Loan__Account__Client').order_by('Date_Due')
    
    # Group by client to get total overdue per client
    defaulters_dict = {}
    for installment in overdue_installments:
        client_id = installment.Loan.Account.Client.pk
        if client_id not in defaulters_dict:
            defaulters_dict[client_id] = {
                'client': installment.Loan.Account.Client,
                'total_overdue': 0,
                'days_overdue': (today - installment.Date_Due).days,
                'loans': 0,
                'latest_loan_id': installment.Loan.pk
            }
        
        defaulters_dict[client_id]['total_overdue'] += installment.Installment_Due
        defaulters_dict[client_id]['loans'] += 1
        defaulters_dict[client_id]['latest_loan_id'] = installment.Loan.pk
    
    # Convert to list and sort by total overdue amount
    defaulters_data = list(defaulters_dict.values())
    defaulters_data.sort(key=lambda x: x['total_overdue'], reverse=True)
    
    # Calculate totals
    total_overdue = sum(d['total_overdue'] for d in defaulters_data)
    total_defaulters = len(defaulters_data)
    
    # === PORTFOLIO VALUE (NEEDED FOR PERFORMANCE METRICS) ===
    
    # Portfolio value
    total_portfolio_value = active_loans.aggregate(
        total=Sum('Principle_Amount')
    )['total'] or 0
    
    # Outstanding amount (total expected - total received)
    total_expected = 0
    total_received = 0
    
    for loan in active_loans:
        loan_total = loan.Principle_Amount + (loan.Principle_Amount * loan.Intrest_Rate / 100)
        total_expected += loan_total
        
        loan_received = Payments.objects.filter(
            Loan=loan,
            Payment_Type=1
        ).aggregate(total=Sum('Amount_Paid'))['total'] or 0
        total_received += loan_received
    
    total_outstanding = total_expected - total_received
    
    # Calculate total collected overall (for financial summary)
    total_collected_overall = Payments.objects.filter(
        Loan__in=active_loans,
        Payment_Type=1
    ).aggregate(total=Sum('Amount_Paid'))['total'] or 0
    
    # Average loan amount
    total_active_loans = active_loans.count()
    avg_loan_amount = 0
    if total_active_loans > 0:
        avg_loan_amount = total_portfolio_value / total_active_loans
    
    # === LOAN PERFORMANCE METRICS ===
    
    # Recovery rate (percentage of loans that are performing well)
    total_active_loans_count = active_loans.count()
    defaulter_client_ids = [defaulter['client'].pk for defaulter in defaulters_data] if defaulters_data else []
    performing_loans = active_loans.exclude(
        Account__Client__pk__in=defaulter_client_ids
    ).count() if defaulter_client_ids else total_active_loans_count
    recovery_rate = (performing_loans / total_active_loans_count * 100) if total_active_loans_count > 0 else 0
    
    # Default rate (percentage of loans that are overdue)
    default_rate = (total_defaulters / total_active_loans_count * 100) if total_active_loans_count > 0 else 0
    
    # Portfolio at Risk (PAR) - loans overdue by more than 30 days
    par_30_plus = sum(
        defaulter['total_overdue'] for defaulter in defaulters_data 
        if defaulter['days_overdue'] > 30
    )
    par_30_plus_rate = (par_30_plus / total_portfolio_value * 100) if total_portfolio_value > 0 else 0
    
    # Write-off rate (completed loans that were fully recovered vs total completed)
    completed_loans = Loans.objects.filter(Status=True)
    total_completed_count = completed_loans.count()
    fully_recovered_loans = 0
    for loan in completed_loans:
        total_expected = loan.Principle_Amount + (loan.Principle_Amount * loan.Intrest_Rate / 100)
        total_received = Payments.objects.filter(Loan=loan, Payment_Type=1).aggregate(
            total=Sum('Amount_Paid'))['total'] or 0
        if total_received >= total_expected * 0.95:  # 95% recovery threshold
            fully_recovered_loans += 1
    
    write_off_rate = ((total_completed_count - fully_recovered_loans) / total_completed_count * 100) if total_completed_count > 0 else 0
    
    # === PROFITABILITY ANALYSIS ===
    
    # Total interest earned (all time)
    total_interest_earned = 0
    for loan in active_loans:
        total_received = Payments.objects.filter(Loan=loan, Payment_Type=1).aggregate(
            total=Sum('Amount_Paid'))['total'] or 0
        if total_received > loan.Principle_Amount:
            total_interest_earned += (total_received - loan.Principle_Amount)
    
    # Total file charges collected (all time)
    total_file_charges_collected = sum(
        (loan.Principle_Amount * loan.File_Charge_Percent / 100) 
        for loan in active_loans
    )
    
    # Total penalties collected (all time)
    total_penalties_collected = Payments.objects.filter(
        Loan__in=active_loans,
        Payment_Type=2  # Penalty payments
    ).aggregate(total=Sum('Amount_Paid'))['total'] or 0
    
    # Total revenue (interest + file charges + penalties)
    total_revenue = total_interest_earned + total_file_charges_collected + total_penalties_collected
    
    # Net profit margin (revenue / total portfolio value)
    net_profit_margin = (total_revenue / total_portfolio_value * 100) if total_portfolio_value > 0 else 0
    
    # Return on Investment (ROI) - revenue / total disbursed
    total_disbursed = sum(loan.Principle_Amount for loan in active_loans)
    roi_percentage = (total_revenue / total_disbursed * 100) if total_disbursed > 0 else 0
    
    # Average interest rate across portfolio
    avg_interest_rate = active_loans.aggregate(
        avg_rate=models.Avg('Intrest_Rate')
    )['avg_rate'] or 0
    
    
    # === TOP COLLECTORS FOR THE PERIOD ===
    
    # Get staff performance for the period
    staff_collections = {}
    for payment in period_payments:
        staff_id = payment.Loan.Loan_Collector.pk
        staff_name = payment.Loan.Loan_Collector.Officer_Name
        
        if staff_id not in staff_collections:
            staff_collections[staff_id] = {
                'name': staff_name,
                'collected_amount': 0,
                'due_amount': 0,
                'loans_count': set()
            }
        
        staff_collections[staff_id]['collected_amount'] += payment.Amount_Paid
        staff_collections[staff_id]['loans_count'].add(payment.Loan.pk)
    
    # Add due amounts for efficiency calculation
    for installment in period_installments:
        staff_id = installment.Loan.Loan_Collector.pk
        if staff_id in staff_collections:
            staff_collections[staff_id]['due_amount'] += installment.Installment_Due
    
    # Calculate efficiency and convert to list
    top_collectors_period = []
    for staff_id, data in staff_collections.items():
        efficiency = 0
        if data['due_amount'] > 0:
            efficiency = (data['collected_amount'] / data['due_amount']) * 100
        
        top_collectors_period.append({
            'name': data['name'],
            'collected_amount': data['collected_amount'],
            'due_amount': data['due_amount'],
            'efficiency': efficiency,
            'loans_count': len(data['loans_count'])
        })
    
    # Sort by collected amount
    top_collectors_period.sort(key=lambda x: x['collected_amount'], reverse=True)
    top_collectors_period = top_collectors_period[:5]  # Top 5
    
    # === PERIOD COLLECTION TREND ===
    
    period_collections = []
    current_date = start_date
    
    # Limit the date range to prevent performance issues
    max_days = 90  # Maximum 90 days for chart
    if (end_date - start_date).days > max_days:
        start_date = end_date - timedelta(days=max_days)
        current_date = start_date
    
    while current_date <= end_date:
        try:
            daily_collection = Payments.objects.filter(
                Date_Paid=current_date,
                Payment_Type=1,
                Loan__in=active_loans
            ).aggregate(total=Sum('Amount_Paid'))['total'] or 0
            
            daily_due = Installments.objects.filter(
                Date_Due=current_date,
                Loan__in=active_loans,
                Installment_Due__gt=0
            ).aggregate(total=Sum('Installment_Due'))['total'] or 0
            
            period_collections.append({
                'date': current_date,
                'amount': float(daily_collection),
                'due_amount': float(daily_due)
            })
        except Exception as e:
            # Handle any database errors gracefully
            period_collections.append({
                'date': current_date,
                'amount': 0,
                'due_amount': 0
            })
        
        current_date += timedelta(days=1)
    
    # === RECENT PAYMENTS IN PERIOD ===
    
    recent_payments_period = Payments.objects.filter(
        Loan__in=active_loans,
        Date_Paid__range=[start_date, end_date]
    ).select_related(
        'Loan__Account__Client'
    ).order_by('-Date_Paid', '-Amount_Paid')[:20]
    
    # === TODAY'S DUE INSTALLMENTS ===
    
    # Get all installments due today
    todays_due_installments = Installments.objects.filter(
        Loan__in=active_loans,
        Date_Due=today,
        Installment_Due__gt=0
    ).select_related(
        'Loan__Account__Client',
        'Loan__Loan_Collector'
    ).order_by('Loan__Account__Client__Name')
    
    # Group by client for better display
    todays_due_dict = {}
    for installment in todays_due_installments:
        client_id = installment.Loan.Account.Client.pk
        if client_id not in todays_due_dict:
            todays_due_dict[client_id] = {
                'client': installment.Loan.Account.Client,
                'total_due': 0,
                'installments': [],
                'collector': installment.Loan.Loan_Collector,
                'loans_count': 0,
                'loan_id': installment.Loan.pk
            }
        
        todays_due_dict[client_id]['total_due'] += installment.Installment_Due
        todays_due_dict[client_id]['installments'].append(installment)
        todays_due_dict[client_id]['loans_count'] += 1
        # Ensure we always have a valid loan_id (use the first loan if multiple)
        if not todays_due_dict[client_id]['loan_id']:
            todays_due_dict[client_id]['loan_id'] = installment.Loan.pk
    
    # Convert to list and sort by total due amount
    todays_due_data = list(todays_due_dict.values())
    todays_due_data.sort(key=lambda x: x['total_due'], reverse=True)
    
    # Calculate total amount due today
    total_due_today = sum(client['total_due'] for client in todays_due_data)
    clients_due_today_count = len(todays_due_data)
    
    
    # Ensure all numeric values are properly formatted
    def safe_float(value):
        """Convert value to float, return 0 if None or invalid"""
        try:
            return float(value) if value is not None else 0.0
        except (ValueError, TypeError):
            return 0.0
    
    # Apply safe conversion to all monetary values
    amount_collected_period = safe_float(amount_collected_period)
    amount_due_period = safe_float(amount_due_period)
    penalty_collected_period = safe_float(penalty_collected_period)
    file_charges_period = safe_float(file_charges_period)
    interest_earned_period = safe_float(interest_earned_period)
    period_net_performance = safe_float(period_net_performance)
    daily_average_collection = safe_float(daily_average_collection)
    total_loan_amount_period = safe_float(total_loan_amount_period)
    total_portfolio_value = safe_float(total_portfolio_value)
    total_outstanding = safe_float(total_outstanding)
    total_collected_overall = safe_float(total_collected_overall)
    avg_loan_amount = safe_float(avg_loan_amount)
    total_overdue = safe_float(total_overdue)
    
    # Apply safe conversion to performance metrics
    recovery_rate = safe_float(recovery_rate)
    default_rate = safe_float(default_rate)
    par_30_plus = safe_float(par_30_plus)
    par_30_plus_rate = safe_float(par_30_plus_rate)
    write_off_rate = safe_float(write_off_rate)
    
    # Apply safe conversion to profitability metrics
    total_interest_earned = safe_float(total_interest_earned)
    total_file_charges_collected = safe_float(total_file_charges_collected)
    total_penalties_collected = safe_float(total_penalties_collected)
    total_revenue = safe_float(total_revenue)
    net_profit_margin = safe_float(net_profit_margin)
    roi_percentage = safe_float(roi_percentage)
    avg_interest_rate = safe_float(avg_interest_rate)
    
    # Loan frequency distribution
    frequency_distribution = active_loans.values('Frequency').annotate(
        count=Count('pk'),
        total_amount=Sum('Principle_Amount')
    )
    
    frequency_labels = {1: 'Daily', 2: 'Weekly', 3: 'Monthly'}
    for item in frequency_distribution:
        item['frequency_label'] = frequency_labels.get(item['Frequency'], 'Unknown')
    
    # === LOAN SIZE DISTRIBUTION ===
    
    # Define loan size categories
    small_loans = active_loans.filter(Principle_Amount__lte=25000)
    medium_loans = active_loans.filter(Principle_Amount__gt=25000, Principle_Amount__lte=100000)
    large_loans = active_loans.filter(Principle_Amount__gt=100000)
    
    loan_size_distribution = [
        {
            'category': 'Small (≤₹25K)',
            'count': small_loans.count(),
            'amount': small_loans.aggregate(total=Sum('Principle_Amount'))['total'] or 0,
            'percentage': (small_loans.count() / total_active_loans_count * 100) if total_active_loans_count > 0 else 0
        },
        {
            'category': 'Medium (₹25K-₹1L)',
            'count': medium_loans.count(),
            'amount': medium_loans.aggregate(total=Sum('Principle_Amount'))['total'] or 0,
            'percentage': (medium_loans.count() / total_active_loans_count * 100) if total_active_loans_count > 0 else 0
        },
        {
            'category': 'Large (>₹1L)',
            'count': large_loans.count(),
            'amount': large_loans.aggregate(total=Sum('Principle_Amount'))['total'] or 0,
            'percentage': (large_loans.count() / total_active_loans_count * 100) if total_active_loans_count > 0 else 0
        }
    ]
    
    # Top loan amounts
    top_loans = active_loans.order_by('-Principle_Amount')[:5].select_related('Account__Client')
    
    # Loan amount statistics
    loan_amount_stats = {
        'min_amount': active_loans.aggregate(min_amount=models.Min('Principle_Amount'))['min_amount'] or 0,
        'max_amount': active_loans.aggregate(max_amount=models.Max('Principle_Amount'))['max_amount'] or 0,
        'median_amount': 0  # Will calculate if needed
    }
    
    # Calculate median
    loan_amounts = list(active_loans.values_list('Principle_Amount', flat=True).order_by('Principle_Amount'))
    if loan_amounts:
        n = len(loan_amounts)
        if n % 2 == 0:
            loan_amount_stats['median_amount'] = (loan_amounts[n//2-1] + loan_amounts[n//2]) / 2
        else:
            loan_amount_stats['median_amount'] = loan_amounts[n//2]
    
    context = {
        # Date filter context
        'selected_range': selected_range,
        'start_date': start_date,
        'end_date': end_date,
        'filtered_days': filtered_days,
        
        # Period-based metrics
        'amount_collected_period': amount_collected_period,
        'amount_due_period': amount_due_period,
        'clients_due_period_count': clients_due_period_count,
        'penalty_collected_period': penalty_collected_period,
        'file_charges_period': file_charges_period,
        'loans_created_period': loans_created_period,
        'total_loan_amount_period': total_loan_amount_period,
        'interest_earned_period': interest_earned_period,
        
        # Performance metrics
        'period_collection_efficiency': round(period_collection_efficiency, 2),
        'period_net_performance': period_net_performance,
        'daily_average_collection': daily_average_collection,
        'period_collection_rate': round(period_collection_rate, 2),
        
        # Loan performance metrics
        'recovery_rate': round(recovery_rate, 2),
        'default_rate': round(default_rate, 2),
        'par_30_plus': par_30_plus,
        'par_30_plus_rate': round(par_30_plus_rate, 2),
        'write_off_rate': round(write_off_rate, 2),
        
        # Profitability metrics
        'total_interest_earned': total_interest_earned,
        'total_file_charges_collected': total_file_charges_collected,
        'total_penalties_collected': total_penalties_collected,
        'total_revenue': total_revenue,
        'net_profit_margin': round(net_profit_margin, 2),
        'roi_percentage': round(roi_percentage, 2),
        'avg_interest_rate': round(avg_interest_rate, 2),
        
        # Period-specific data
        'top_collectors_period': top_collectors_period,
        'period_collections': period_collections,
        'recent_payments_period': recent_payments_period,
        
        # Today's due installments
        'todays_due_data': todays_due_data,
        'total_due_today': safe_float(total_due_today),
        'clients_due_today_count': clients_due_today_count,
        
        # Lists
        'defaulters_data': defaulters_data,  # All defaulters, not just top 10
        'total_overdue': total_overdue,
        'total_defaulters': total_defaulters,
        
        # Additional context for templates
        'performing_loans': performing_loans,
        'total_active_loans_count': total_active_loans_count,
        'total_completed_count': total_completed_count,
        
        # Portfolio metrics
        'total_portfolio_value': total_portfolio_value,
        'total_outstanding': total_outstanding,
        'total_collected_overall': total_collected_overall,
        'avg_loan_amount': avg_loan_amount,
        'total_active_loans': total_active_loans,
        'frequency_distribution': frequency_distribution,
        'loan_size_distribution': loan_size_distribution,
        'top_loans': top_loans,
        'loan_amount_stats': loan_amount_stats,
        
        # Current date
        'today': today,
        
        # Backward compatibility (keeping original variables)
        'amount_collected_today': amount_collected_period if selected_range == 'today' else 0,
        'amount_due_today': amount_due_period if selected_range == 'today' else 0,
        'clients_due_today_count': clients_due_period_count if selected_range == 'today' else 0,
        'collection_efficiency': round(period_collection_efficiency, 2),
        'penalty_outstanding': penalty_collected_period,  # For backward compatibility
        'file_charge_amount': file_charges_period,
        'loans_created_today_count': loans_created_period if selected_range == 'today' else 0,
        'loans_created_this_month': loans_created_period if selected_range == 'last_month' else 0,
        'recent_payments': recent_payments_period[:10],  # For backward compatibility
        'weekly_collections': period_collections,  # For backward compatibility
    }
    
    return render(request, 'microfinance/dashboard.html', context)





def _calculate_individual_installment_penalties(loan, installments, payments, today):
    """
    Calculate penalties for each individual installment separately.
    This creates separate penalty records for each overdue installment.
    """
    print(f"=== INDIVIDUAL INSTALLMENT PENALTIES ===")
    print(f"Today's date: {today}")
    print(f"Processing {len(installments)} installments")
    
    # Convert payments to list and sort by date
    payment_list = []
    for pay in payments:
        payment_list.append({
            'date': pay['Date_Paid'],
            'amount': Decimal(str(pay['Amount_Paid']))
        })
    payment_list.sort(key=lambda x: x['date'])
    
    # Create payment pool for allocation (FIFO)
    payment_pool = []
    for payment in payment_list:
        payment_pool.append({
            'date': payment['date'],
            'original_amount': payment['amount'],
            'remaining_amount': payment['amount']
        })
    
    print("Payment pool:")
    for payment in payment_pool:
        print(f"  {payment['date']}: {payment['original_amount']}")
    
    # Process each installment individually
    penalty_periods = []
    
    for inst in installments:
        due_date = inst['Date_Due']
        amount = Decimal(str(inst['Installment_Due']))
        
        # Skip future installments
        if due_date >= today:
            print(f"\nSkipping future installment: {due_date}")
            continue
            
        print(f"\nProcessing installment: {due_date}, amount: {amount}")
        
        # Check if there are any payments that can be applied to this installment
        # We need to check both advance payments (before due date) and regular payments (on or after due date)
        remaining_installment = amount
        installment_fully_paid = False
        
        # First, check for advance payments (payments made before the due date)
        advance_payments = [p for p in payment_pool if p['remaining_amount'] > 0 and p['date'] < due_date]
        advance_payments.sort(key=lambda x: x['date'])  # Sort by date
        
        for payment in advance_payments:
            if remaining_installment <= 0:
                break
                
            payment_date = payment['date']
            available_payment = payment['remaining_amount']
            
            # Apply advance payment to this installment
            payment_application = min(remaining_installment, available_payment)
            remaining_installment -= payment_application
            payment['remaining_amount'] -= payment_application
            
            print(f"  Applied advance payment: {payment_application} on {payment_date}, remaining installment: {remaining_installment}")
            
            # If installment is fully paid by advance payment, no penalty needed
            if remaining_installment <= 0:
                print(f"  Installment fully paid in advance - no penalty")
                installment_fully_paid = True
                break
        
        # If installment is fully paid by advance payments, skip penalty calculation
        if installment_fully_paid:
            continue
        
        # If installment is not fully paid by advance payments, check for regular payments
        # and calculate penalties for the remaining amount
        regular_payments = [p for p in payment_pool if p['remaining_amount'] > 0 and p['date'] >= due_date]
        regular_payments.sort(key=lambda x: x['date'])  # Sort by date
        
        if not regular_payments:
            # No regular payments available - penalty runs from due date to today for remaining amount
            if remaining_installment > 0:
                days = (today - due_date).days
                if days > 0:
                    penalty_periods.append({
                        'start_date': due_date,
                        'end_date': today,
                        'amount': remaining_installment,
                        'days': days,
                        'installment_due': due_date,
                        'description': f"No payment for {due_date} installment"
                    })
                    print(f"  No payment - penalty: {due_date} to {today} ({days} days)")
            continue
        
        # Process regular payments chronologically to create penalty periods
        current_date = due_date
        
        for payment in regular_payments:
            payment_date = payment['date']
            available_payment = payment['remaining_amount']
            
            if remaining_installment <= 0:
                break
                
            # Create penalty period before this payment
            if current_date < payment_date:
                days = (payment_date - current_date).days
                if days > 0:
                    penalty_periods.append({
                        'start_date': current_date,
                        'end_date': payment_date,
                        'amount': remaining_installment,
                        'days': days,
                        'installment_due': due_date,
                        'description': f"Penalty for {due_date} installment until payment on {payment_date}"
                    })
                    print(f"  Penalty period: {current_date} to {payment_date} ({days} days) for {remaining_installment}")
            
            # Apply payment to this installment
            payment_application = min(remaining_installment, available_payment)
            remaining_installment -= payment_application
            payment['remaining_amount'] -= payment_application
            
            print(f"  Applied payment: {payment_application} on {payment_date}, remaining installment: {remaining_installment}")
            
            # Update current date
            current_date = payment_date
            
            # If installment is fully paid, stop processing
            if remaining_installment <= 0:
                break
        
        # If installment still has remaining amount, penalty continues until today
        if remaining_installment > 0 and current_date < today:
            days = (today - current_date).days
            if days > 0:
                penalty_periods.append({
                    'start_date': current_date,
                    'end_date': today,
                    'amount': remaining_installment,
                    'days': days,
                    'installment_due': due_date,
                    'description': f"Final penalty for {due_date} installment from {current_date} to today"
                })
                print(f"  Final penalty: {current_date} to {today} ({days} days) for {remaining_installment}")
    
    # Create penalty database records
    penalty_rate = Decimal('2')  # 2% per day
    total_penalty = Decimal('0')
    
    # Delete existing penalties
    Penalty.objects.filter(Loan=loan).delete()
    
    print(f"\nCreating penalty records:")
    for period in penalty_periods:
        penalty_amount = period['amount'] * penalty_rate / Decimal('100') * period['days']
        total_penalty += penalty_amount
        
        penalty_obj = Penalty(
            Loan=loan,
            Date_Started=period['start_date'],
            Date_Ended=period['end_date'],
            Amount=period['amount'],
            Penalty_Calc=penalty_amount,
            Status=False,
            Penalty_Paid=Decimal('0'),
            Installment_Due_Date=period.get('installment_due', period['start_date'])
        )
        penalty_obj.save()
        
        print(f"  {period['start_date']} to {period['end_date']}: "
              f"installment {period['installment_due']}, amount {period['amount']}, "
              f"penalty {penalty_amount} ({penalty_rate}% × {period['days']} days)")
    
    print(f"Total penalty: {total_penalty}")
    print(f"=== END INDIVIDUAL INSTALLMENT PENALTIES ===")
    
    return {
        'total_penalty': total_penalty,
        'penalty_periods': penalty_periods
    }


def _calculate_individual_penalties_corrected(loan, installments_data, payments_data, today):
    """
    Updated wrapper function to use individual installment penalty calculation.
    """
    return _calculate_individual_installment_penalties(loan, installments_data, payments_data, today)


# Alternative detailed approach if you want even more granular control
def _calculate_installment_by_installment_penalties(loan, installments, payments, today):
    """
    Even more detailed approach - tracks each installment independently
    and shows exactly how payments are allocated.
    """
    print(f"=== INSTALLMENT-BY-INSTALLMENT PENALTIES ===")
    
    # Create detailed tracking for each installment
    installment_ledger = {}
    for inst in installments:
        due_date = inst['Date_Due']
        amount = Decimal(str(inst['Installment_Due']))
        
        if due_date < today:  # Only track overdue installments
            installment_ledger[due_date] = {
                'original_amount': amount,
                'remaining_balance': amount,
                'payments_applied': [],
                'penalty_periods': []
            }
    
    # Sort installments by due date for FIFO payment allocation
    sorted_due_dates = sorted(installment_ledger.keys())
    
    # Process each payment
    for pay in sorted(payments, key=lambda x: x['Date_Paid']):
        payment_date = pay['Date_Paid']
        payment_amount = Decimal(str(pay['Amount_Paid']))
        remaining_payment = payment_amount
        
        print(f"\nProcessing payment: {payment_date}, amount: {payment_amount}")
        
        # Allocate payment to installments (FIFO - oldest first)
        for due_date in sorted_due_dates:
            if remaining_payment <= 0:
                break
                
            installment = installment_ledger[due_date]
            if installment['remaining_balance'] > 0 and payment_date > due_date:
                
                # Calculate allocation
                allocation = min(installment['remaining_balance'], remaining_payment)
                
                # Record the allocation
                installment['payments_applied'].append({
                    'date': payment_date,
                    'amount': allocation
                })
                
                # Update balances
                installment['remaining_balance'] -= allocation
                remaining_payment -= allocation
                
                print(f"  Allocated {allocation} to {due_date} installment, "
                      f"remaining balance: {installment['remaining_balance']}")
    
    # Calculate penalty periods for each installment
    all_penalty_periods = []
    
    for due_date in sorted_due_dates:
        installment = installment_ledger[due_date]
        original_amount = installment['original_amount']
        
        print(f"\nCalculating penalties for {due_date} installment:")
        
        # Track penalty periods for this specific installment
        current_date = due_date
        current_balance = original_amount
        
        # Process payments chronologically
        for payment_info in sorted(installment['payments_applied'], key=lambda x: x['date']):
            payment_date = payment_info['date']
            payment_amount = payment_info['amount']
            
            # Create penalty period before payment
            if current_date < payment_date and current_balance > 0:
                days = (payment_date - current_date).days
                if days > 0:
                    penalty_period = {
                        'start_date': current_date,
                        'end_date': payment_date,
                        'amount': current_balance,
                        'days': days,
                        'installment_due': due_date
                    }
                    all_penalty_periods.append(penalty_period)
                    installment['penalty_periods'].append(penalty_period)
                    print(f"  Penalty: {current_date} to {payment_date}, "
                          f"amount: {current_balance}, days: {days}")
            
            # Apply payment
            current_balance -= payment_amount
            current_date = payment_date
        
        # Final penalty period if balance remains
        if current_balance > 0 and current_date < today:
            days = (today - current_date).days
            if days > 0:
                penalty_period = {
                    'start_date': current_date,
                    'end_date': today,
                    'amount': current_balance,
                    'days': days,
                    'installment_due': due_date
                }
                all_penalty_periods.append(penalty_period)
                installment['penalty_periods'].append(penalty_period)
                print(f"  Final penalty: {current_date} to {today}, "
                      f"amount: {current_balance}, days: {days}")
    
    # Create penalty database records
    penalty_rate = Decimal('2')
    total_penalty = Decimal('0')
    
    Penalty.objects.filter(Loan=loan).delete()
    
    for period in all_penalty_periods:
        penalty_amount = period['amount'] * penalty_rate / Decimal('100') * period['days']
        total_penalty += penalty_amount
        
        penalty_obj = Penalty(
            Loan=loan,
            Date_Started=period['start_date'],
            Date_Ended=period['end_date'],
            Amount=period['amount'],
            Penalty_Calc=penalty_amount,
            Status=False,
            Installment_Due_Date=period.get('installment_due', period['start_date'])
        )
        penalty_obj.save()
    
    print(f"\nTotal penalty: {total_penalty}")
    print(f"=== END INSTALLMENT-BY-INSTALLMENT PENALTIES ===")
    
    return {
        'total_penalty': total_penalty,
        'penalty_periods': all_penalty_periods,
        'installment_ledger': installment_ledger
    }