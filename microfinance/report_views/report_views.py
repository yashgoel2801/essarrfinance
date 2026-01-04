from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
import pytz
from microfinance.models import Loans,Installments,Payments,Penalty
from django.utils.dateparse import parse_date
from django.db.models import Q,Sum, F, Case, When,FloatField



local_timezone = pytz.timezone('Asia/Kolkata')


#officerWise Report
@login_required(login_url="/accounts/login/")
def Officer_And_Frequency_Wise_Report(request):
    if request.method != 'POST':
        return redirect('microfinance:reports')
        
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
        # Use Payments model for collected amounts
        payments = Payments.objects.filter(Loan=loan,Payment_Type=1)
        total_amnt_to_be_coll=0
        total_amnt_collected =0
        installments_with_date_due_lte_today =installments.filter(Date_Due__lte = datetime.now())
        for installment in installments_with_date_due_lte_today:
            total_amnt_to_be_coll += installment.Installment_Due
        
        for payment in payments:
            total_amnt_collected += payment.Amount_Paid

        total_interest_waived = Waiver.objects.filter(Loan=loan, Waiver_Type=2).aggregate(Sum('Amount'))['Amount__sum'] or 0
        total_bal = loan.Total - total_amnt_collected - total_interest_waived
    
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
    if request.method != 'POST':
        return redirect('microfinance:reports')

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
    
    # Pre-calculate File Charges and Total Financed for filtered loans
    loan_data = loanswithLoanDateInRange.annotate(
        file_charge_val=F('Principle_Amount') * F('File_Charge_Percent') / 100
    ).values('pk', 'Principle_Amount', 'file_charge_val')
    
    File_Charge = {item['pk']: item['file_charge_val'] for item in loan_data}
    totalAmntFinanced = sum(item['Principle_Amount'] for item in loan_data)
    totalFileChargeCollected = sum(item['file_charge_val'] for item in loan_data)
    print('3',datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))

    # Bulk fetch Penalty Payments Within Date Range
    # Use IDs to avoid slow subqueries with OR/DISTINCT
    penalty_loan_ids = list(loansWihtPenaltyOrItsPaidDateInRange.values_list('pk', flat=True))
    
    payment_data = Payments.objects.filter(
        Loan_id__in=penalty_loan_ids,
        Date_Paid__range=[start,end]
    ).values('Loan_id', 'Payment_Type').annotate(total=Sum('Amount_Paid'))

    Penalty_Collected = {}
    for item in payment_data:
        if item['Payment_Type'] == 2:
            Penalty_Collected[item['Loan_id']] = {'Amount_Paid__sum': item['total']}
            totalPenaltyCollected += item['total']

    # Bulk fetch Penalty Calculations
    print('3.5', 'Fetching penalties for', len(penalty_loan_ids), 'loans at', datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))
    Penalty_To_Be_Collected = {}
    penalties = Penalty.objects.filter(Loan_id__in=penalty_loan_ids).only('Loan_id', 'Status', 'Penalty_Paid', 'Date_Ended', 'Penalty_Calc', 'Amount', 'Percent', 'Date_Started')
    today_date = datetime.now().date()
    
    penalty_count = 0
    for penalty in penalties:
        penalty_count += 1
        val = 0
        if penalty.Status: 
            val = penalty.Penalty_Paid
        else:
            if penalty.Date_Ended:
                val = penalty.Penalty_Calc
            else:
                days = (today_date - penalty.Date_Started).days
                if days > 0:
                    val = penalty.Amount * penalty.Percent * days / 100
        
        if val > 0:
            loan_id = penalty.Loan_id
            # Subtract any individual penalty waiver
            val = max(0, val - penalty.Waived_Amount)
            Penalty_To_Be_Collected[loan_id] = Penalty_To_Be_Collected.get(loan_id, 0) + val

    print('4', 'Processed', penalty_count, 'penalties at', datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))

    # Bulk fetch Installment Totals
    inst_loan_ids = list(loansWihtInstallmentOrPaidDateInRange.values_list('pk', flat=True))
    inst_data = Installments.objects.filter(
        Loan_id__in=inst_loan_ids,
        Date_Due__range=[start,end]
    ).values('Loan_id').annotate(total=Sum('Installment_Due'))
    
    Amnt_To_Be_Collected = {}
    for item in inst_data:
        Amnt_To_Be_Collected[item['Loan_id']] = {'Installment_Due__sum': item['total']}
        totalAmntToBeCollected += item['total']

    # Bulk fetch Installment Payment Totals
    Amnt_Collected = {}
    for item in payment_data:
        if item['Payment_Type'] == 1:
            Amnt_Collected[item['Loan_id']] = {'Amount_Paid__sum': item['total']}
            totalAmntCollected += item['total']

    # Fetch and subtract general waivers (Waiver model)
    all_general_waivers = Waiver.objects.filter(
        Loan_id__in=list(set(inst_loan_ids + penalty_loan_ids)),
        Date_Applied__range=[start,end]
    ).values('Loan_id', 'Waiver_Type').annotate(total=Sum('Amount'))
    
    for item in all_general_waivers:
        lid = item['Loan_id']
        wtype = item['Waiver_Type']
        wamt = item['total']
        if wtype == 1: # Penalty waiver
            if lid in Penalty_To_Be_Collected:
                Penalty_To_Be_Collected[lid] = max(0, Penalty_To_Be_Collected[lid] - wamt)
        elif wtype == 2: # Interest/Principal waiver
            if lid in Amnt_To_Be_Collected:
                curr = Amnt_To_Be_Collected[lid].get('Installment_Due__sum', 0)
                Amnt_To_Be_Collected[lid]['Installment_Due__sum'] = max(0, curr - wamt)
                totalAmntToBeCollected -= min(wamt, curr)

    print('5',datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))
    return render(request,'microfinance/Officerwise_Total_Finance_And_Collection_Report.html',{'start':start,'end':end,'Staff':Staff_pk,'Freq':Frequency,'amnt_collected':Amnt_Collected,'Loan':loansWihtInstallmentOrPaidDateInRange,'Loan3':loanswithLoanDateInRange,'Loan2':loansWihtPenaltyOrItsPaidDateInRange,'amntcollected':totalAmntCollected,'amnttobecollected':totalAmntToBeCollected,'amnt_to_be_collected':Amnt_To_Be_Collected,'penalty_collected':Penalty_Collected,'penaltycollected':totalPenaltyCollected,'file_charge':File_Charge,'filecollected':totalFileChargeCollected,'penalty_to_be_collected':Penalty_To_Be_Collected})
