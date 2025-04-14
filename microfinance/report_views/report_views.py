from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
import pytz
from microfinance.models import Loans,Installments,Payments,Penalty
from django.utils.dateparse import parse_date
from django.db.models import Q,Sum, F, Case, When,FloatField



local_timezone = pytz.timezone('Asia/Kolkata')


#officerWise Report
@login_required(login_url="/accounts/login/")
def Officer_And_Frequency_Wise_Report(request):
    Staff_pk=int(request.POST.get('name'))
    status =(request.POST.get('status'))
    Loanstat =Loans.objects.all().filter(Status=status)
    Frequency=int(request.POST.get('loan')) #loan type
    if Staff_pk != 0 and Frequency != 0: 
        Loan =Loanstat.filter(Loan_Collector=Staff_pk,Frequency =Frequency)
    if Staff_pk == 0 and Frequency !=0:
        Loan =Loanstat.filter(Frequency =Frequency).exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10)
    if Staff_pk !=0 and Frequency ==0:
        Loan =Loanstat.filter(Loan_Collector=Staff_pk)
    if Staff_pk == 0 and Frequency == 0:
        Loan =Loanstat.exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10)
    today = datetime.now(local_timezone)
    total_amnt_to_be_coll_dic ={}
    total_amnt_collected_dic={}
    total_amnt_pending_dic={}
    total_bal_dic={}
    total_amnt_pending_for_all_cases=0
    total_amnt_to_be_coll_for_all_cases=0
    total_amnt_bal_for_all_cases=0

    for loan in Loan:
        installments = Installments.objects.filter(Loan=loan,Installment_Due__gt = 0).order_by('Date_Due')
        payments = Payments.objects.filter(Loan=loan,Payment_Type=1)
        total_amnt_to_be_coll=0
        total_amnt_collected =0
        installments_with_date_due_lte_today =installments.filter(Date_Due__lte = datetime.now())
        for installment in installments_with_date_due_lte_today:
            total_amnt_to_be_coll += installment.Installment_Due
        
        for payment in payments:
            total_amnt_collected += payment.Amount_Paid

        total_bal = loan.Total - total_amnt_collected
    
        total_amnt_to_be_coll_dic[loan.pk]=round(total_amnt_to_be_coll,1)
        total_amnt_collected_dic[loan.pk]=round(total_amnt_collected,1)
        total_amnt_pending_dic[loan.pk] = round(total_amnt_to_be_coll_dic[loan.pk]-total_amnt_collected_dic[loan.pk],1)
        total_bal_dic[loan.pk]=round(total_bal,1)

    for i,j in total_amnt_pending_dic.items():
        total_amnt_pending_for_all_cases+=j

    for i,j in total_amnt_to_be_coll_dic.items():
        total_amnt_to_be_coll_for_all_cases+=j

    for i,j in total_bal_dic.items():
        total_amnt_bal_for_all_cases+=j

    return render(request,'microfinance/Officer_And_Frequency_Wise_Report.html',{'loans':Loan,'Today':today,'Staff':Staff_pk,'Frequency':Frequency,'Total_Amnt_Pending':total_amnt_pending_for_all_cases,'Total_bal_dic':total_bal_dic,'Total_amt_to_be_col_dic':total_amnt_to_be_coll_dic,'Total_amt_col_dic':total_amnt_collected_dic,'Total_Pen_dic':total_amnt_pending_dic,'Total_Amnt_to_be_Collected':total_amnt_to_be_coll_for_all_cases,'Total_Amnt_Balance':total_amnt_bal_for_all_cases})



#Officerwise collection report
@login_required(login_url="/accounts/login/")
def Officerwise_Total_Finance_And_Collection_Report(request):
    Staff_pk=int(request.POST.get('name'))
    Frequency=int(request.POST.get('loan'))
    start=request.POST.get('from')
    end=request.POST.get('to')
    print('1',datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))
    if(start == '' or end == ''):
        return render(request,'microfinance/error/report_datenull.html')
    if Staff_pk != 0 and Frequency != 0:     
        loans= Loans.objects.filter(Loan_Collector_id=Staff_pk).filter(Frequency=Frequency)
 
    if Staff_pk == 0 and Frequency !=0:
        loans= Loans.objects.filter(Frequency=Frequency).exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10)

    if Staff_pk !=0 and Frequency ==0:
        loans= Loans.objects.filter(Loan_Collector_id=Staff_pk)

    if Staff_pk == 0 and Frequency == 0:
        loans= Loans.objects.all()
    loanWithInstallmentsWithinDateRange = loans.filter(installments__Date_Due__range=[start,end],installments__Installment_Due__gt=0).distinct().order_by("id")
    loanWithPenaltiessWithinDateRange = loans.filter(penalty__Date_Started__range=[start,end]).distinct().order_by("id")
    paymentsCollectedWithinDateRange = loans.filter(payments__Date_Paid__range=[start,end]).distinct().order_by("id")
    loanswithLoanDateInRange =loans.filter(Loan_Date__range=[start,end]).distinct()
    
    loansWihtInstallmentOrPaidDateInRange = loanWithInstallmentsWithinDateRange|paymentsCollectedWithinDateRange.filter(payments__Payment_Type=1)
    loansWihtPenaltyOrItsPaidDateInRange = loanWithPenaltiessWithinDateRange|paymentsCollectedWithinDateRange.filter(payments__Payment_Type=2)
    print('2',datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))
    totalAmntCollected =totalPenaltyCollected=totalFileChargeCollected =totalAmntToBeCollected= totalAmntFinanced =0
    Amnt_Collected = {}
    Penalty_Collected = {}
    Penalty_To_Be_Collected = {}
    File_Charge={}
    Amnt_To_Be_Collected = {}
    
    for loan in loanswithLoanDateInRange:   
        File_Charge[loan.pk] = loan.Principle_Amount*loan.File_Charge_Percent/100
        totalAmntFinanced+= loan.Principle_Amount
        totalFileChargeCollected += File_Charge[loan.pk]
    print('3',datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))
    for loan in loansWihtPenaltyOrItsPaidDateInRange:  
        Penalty_Collected[loan.pk] = loansWihtPenaltyOrItsPaidDateInRange.filter(payments__Date_Paid__range=[start,end]).filter(pk=loan.pk,payments__Payment_Type=2).distinct().aggregate(Sum('payments__Amount_Paid'))
        # Penalty_Collected[loan.pk] = Payments.objects.filter(Loan=loan,Payment_Type=2,Date_Paid__range=[start,end]).distinct().aggregate(Sum('Amount_Paid'))
        if Penalty_Collected[loan.pk]["payments__Amount_Paid__sum"]:
            totalPenaltyCollected += Penalty_Collected[loan.pk]["payments__Amount_Paid__sum"] 
        
        penalties = Penalty.objects.filter(Loan=loan)
        for penalty in penalties:
            if(penalty.Status=='True'):
               Penalty_To_Be_Collected[loan.pk] += penalty.Penalty_Paid
            else:
                if(penalty.Date_Ended):
                    if(loan.pk in Penalty_To_Be_Collected):
                      Penalty_To_Be_Collected[loan.pk] += penalty.Penalty_Calc
                    else:
                        Penalty_To_Be_Collected[loan.pk]=penalty.Penalty_Calc
                else:
                    days = (datetime.now().date() - penalty.Date_Started).days  
                    penalty_Calc = penalty.Amount*penalty.Percent*days/100
                    if(penalty.Date_Started!=datetime.now(local_timezone)):
                        if(loan.pk in Penalty_To_Be_Collected):
                            Penalty_To_Be_Collected[loan.pk] += penalty_Calc
                        else:
                            Penalty_To_Be_Collected[loan.pk]=penalty_Calc
    print('4',datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))

    
    
    for i in loansWihtInstallmentOrPaidDateInRange:
        Amnt_To_Be_Collected[i.pk]=loansWihtInstallmentOrPaidDateInRange.filter(installments__Date_Due__range=[start,end]).filter(pk=i.pk).aggregate(Sum('installments__Installment_Due'))
        # Amnt_To_Be_Collected[i.pk] = Installments.objects.filter(Loan=i).filter(Date_Due__range=[start,end]).distinct().aggregate(Sum('Installment_Due'))
        if Amnt_To_Be_Collected[i.pk]["installments__Installment_Due__sum"]:
            totalAmntToBeCollected += Amnt_To_Be_Collected[i.pk]["installments__Installment_Due__sum"]
        Amnt_Collected[i.pk]=loansWihtInstallmentOrPaidDateInRange.filter(payments__Date_Paid__range=[start,end]).filter(pk=i.pk,payments__Payment_Type=1).aggregate(Sum('payments__Amount_Paid'))
        # Amnt_Collected[i.pk] = Payments.objects.filter(Loan=i).filter(Date_Paid__range=[start,end],Payment_Type=1).distinct().aggregate(Sum('Amount_Paid'))
        if Amnt_Collected[i.pk]["payments__Amount_Paid__sum"]:
            totalAmntCollected += Amnt_Collected[i.pk]["payments__Amount_Paid__sum"] 


    print('5',datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))
    return render(request,'microfinance/Officerwise_Total_Finance_And_Collection_Report.html',{'start':start,'end':end,'Staff':Staff_pk,'amnt_collected':Amnt_Collected,'Loan':loansWihtInstallmentOrPaidDateInRange,'Loan3':loanswithLoanDateInRange,'Loan2':loansWihtPenaltyOrItsPaidDateInRange,'amntcollected':totalAmntCollected,'amnttobecollected':totalAmntToBeCollected,'amnt_to_be_collected':Amnt_To_Be_Collected,'penalty_collected':Penalty_Collected,'penaltycollected':totalPenaltyCollected,'file_charge':File_Charge,'filecollected':totalFileChargeCollected,'penalty_to_be_collected':Penalty_To_Be_Collected})
