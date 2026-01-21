from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
import pytz
from microfinance.models import Loans,Installments,Payments,Penalty,Waiver
from django.utils.dateparse import parse_date
from django.db.models import Q,Sum, F



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
    today_date = datetime.now(local_timezone).date()
    loan_ids = list(Loan.values_list('pk', flat=True))

    # Bulk fetch Due Installments
    inst_data = Installments.objects.filter(
        Loan_id__in=loan_ids,
        Installment_Due__gt=0,
        Date_Due__lte=today_date
    ).values('Loan_id').annotate(total=Sum('Installment_Due'))
    inst_totals = {item['Loan_id']: item['total'] for item in inst_data}

    # Bulk fetch Payments
    payment_data = Payments.objects.filter(
        Loan_id__in=loan_ids,
        Payment_Type=1
    ).values('Loan_id').annotate(total=Sum('Amount_Paid'))
    payment_totals = {item['Loan_id']: item['total'] for item in payment_data}

    # Bulk fetch Waivers
    waiver_data = Waiver.objects.filter(
        Loan_id__in=loan_ids,
        Waiver_Type=2
    ).values('Loan_id').annotate(total=Sum('Amount'))
    waiver_totals = {item['Loan_id']: item['total'] for item in waiver_data}

    total_amnt_to_be_coll_dic ={}
    total_amnt_collected_dic={}
    total_amnt_pending_dic={}
    total_bal_dic={}
    total_amnt_pending_for_all_cases=0
    total_amnt_to_be_coll_for_all_cases=0
    total_amnt_bal_for_all_cases=0

    # Process all totals
    for loan in Loan:
        l_id = loan.pk
        total_amnt_to_be_coll = inst_totals.get(l_id, 0)
        total_amnt_collected = payment_totals.get(l_id, 0)
        total_interest_waived = waiver_totals.get(l_id, 0)
        
        # total_bal = loan.Total - total_amnt_collected - total_interest_waived
        loan_total_val = loan.Principle_Amount + (loan.Principle_Amount * loan.Intrest_Rate / 100)
        total_bal = loan_total_val - total_amnt_collected - total_interest_waived

        total_amnt_to_be_coll_dic[l_id] = round(total_amnt_to_be_coll, 1)
        total_amnt_collected_dic[l_id] = round(total_amnt_collected, 1)
        total_amnt_pending_dic[l_id] = round(total_amnt_to_be_coll_dic[l_id] - total_amnt_collected_dic[l_id], 1)
        total_bal_dic[l_id] = round(total_bal, 1)

        total_amnt_pending_for_all_cases += total_amnt_pending_dic[l_id]
        total_amnt_to_be_coll_for_all_cases += total_amnt_to_be_coll_dic[l_id]
        total_amnt_bal_for_all_cases += total_bal_dic[l_id]

    return render(request,'microfinance/Officer_And_Frequency_Wise_Report.html',{'loans':Loan,'Today':today_date,'Staff':Staff_pk,'Frequency':Frequency,'Total_Amnt_Pending':total_amnt_pending_for_all_cases,'Total_bal_dic':total_bal_dic,'Total_amt_to_be_col_dic':total_amnt_to_be_coll_dic,'Total_amt_col_dic':total_amnt_collected_dic,'Total_Pen_dic':total_amnt_pending_dic,'Total_Amnt_to_be_Collected':total_amnt_to_be_coll_for_all_cases,'Total_Amnt_Balance':total_amnt_bal_for_all_cases})



#Officerwise collection report
@login_required(login_url="/accounts/login/")
def Officerwise_Total_Finance_And_Collection_Report(request):
    if request.method != 'POST':
        return redirect('microfinance:reports')

    Staff_pk = int(request.POST.get('name'))
    Frequency = int(request.POST.get('loan'))
    start = request.POST.get('from')
    end = request.POST.get('to')
    
    if not start or not end:
        return render(request, 'microfinance/error/report_datenull.html')

    # Base queries for all loans that could have activity in range
    # (Previously limited to active loans, but collections can happen on recently closed loans too)
    base_loans = Loans.objects.all()
    
    if Staff_pk != 0:
        base_loans = base_loans.filter(Loan_Collector_id=Staff_pk)
    else:
        # Match previous exclusion logic
        base_loans = base_loans.exclude(Loan_Collector_id=9).exclude(Loan_Collector_id=10)
        
    if Frequency != 0:
        base_loans = base_loans.filter(Frequency=Frequency)

    # 1. Main collection data QuerySet (Installments)
    Loan_QS = base_loans.filter(
        Q(installments__Date_Paid__range=[start, end]) | 
        Q(installments__Date_Due__range=[start, end])
    ).distinct().order_by("id")
    
    # 2. Loans with penalty payments in range (using Payments table as source of truth)
    Loan2_QS = base_loans.filter(
        payments__Payment_Type=2,
        payments__Date_Paid__range=[start, end]
    ).distinct().order_by("id")
    
    # 3. New loans registered in range
    Loan3_QS = base_loans.filter(
        Loan_Date__range=[start, end]
    ).distinct()

    totalAmntCollected = totalPenaltyCollected = totalFileChargeCollected = totalAmntToBeCollected = totalAmntFinanced = 0
    today_date = datetime.now(local_timezone).date()
    
    # Process Collection Data
    Collection_Data = []
    from django.db.models import Max
    for loan in Loan_QS:
        # Amount paid in range
        payments = Payments.objects.filter(Loan=loan, Payment_Type=1, Date_Paid__range=[start, end])
        collected = payments.aggregate(Sum('Amount_Paid'))['Amount_Paid__sum'] or 0
        totalAmntCollected += collected
        
        # Last payment date in range
        last_pay = payments.aggregate(Max('Date_Paid'))['Date_Paid__max']
        
        # Amount expected in range (Installments due)
        to_be_collected = Installments.objects.filter(Loan=loan, Date_Due__range=[start, end]).aggregate(Sum('Installment_Due'))['Installment_Due__sum'] or 0
        totalAmntToBeCollected += to_be_collected
        
        # Total Pending Penalty
        penalties = Penalty.objects.filter(Loan=loan, Status=False)
        pending_penalty = 0
        for p in penalties:
            # Simple calculation for penalty
            if not p.Date_Ended:
                days = (today_date - p.Date_Started).days
                val = (p.Amount * p.Percent * max(0, days)) / 100
                pending_penalty += (val - p.Penalty_Paid - p.Waived_Amount)
            else:
                pending_penalty += (p.Penalty_Calc - p.Penalty_Paid - p.Waived_Amount)
        
        # Calculate Overdue Amount as per USER request
        # 1. Total due till end date
        total_due_till_end = Installments.objects.filter(Loan=loan, Date_Due__lte=end).aggregate(Sum('Installment_Due'))['Installment_Due__sum'] or 0
        # 2. Total paid till end date
        total_paid_till_end = Payments.objects.filter(Loan=loan, Payment_Type=1, Date_Paid__lte=end).aggregate(Sum('Amount_Paid'))['Amount_Paid__sum'] or 0
        # 3. Cumulative overdue
        cumulative_overdue = max(0, total_due_till_end - total_paid_till_end)
        # 4. Final overdue capped at range to_be_collected
        overdue_amount = min(cumulative_overdue, to_be_collected)

        Collection_Data.append({
            'loan': loan,
            'collected': collected,
            'to_be_collected': to_be_collected,
            'last_pay': last_pay,
            'pending_penalty': max(0, pending_penalty),
            'overdue_amount': overdue_amount
        })

    # Process Penalty Data
    Penalty_Data = []
    for loan in Loan2_QS:
        paid = Payments.objects.filter(Loan=loan, Payment_Type=2, Date_Paid__range=[start, end]).aggregate(Sum('Amount_Paid'))['Amount_Paid__sum'] or 0
        totalPenaltyCollected += paid
        Penalty_Data.append({'loan': loan, 'paid': paid})

    # Process File Charges
    File_Charge_Data = []
    for loan in Loan3_QS:
        charge = loan.Principle_Amount * loan.File_Charge_Percent / 100
        totalFileChargeCollected += charge
        totalAmntFinanced += loan.Principle_Amount
        File_Charge_Data.append({'loan': loan, 'charge': charge})

    # Expense and Waiver Calculations (for full summary)
    total_penalty_waived = Waiver.objects.filter(Waiver_Type=1, Date_Applied__range=[start, end]).aggregate(Sum('Amount'))['Amount__sum'] or 0
    total_interest_waived = Waiver.objects.filter(Waiver_Type=2, Date_Applied__range=[start, end]).aggregate(Sum('Amount'))['Amount__sum'] or 0
    
    from microfinance.models import Expenditures
    exp_q = Expenditures.objects.filter(Date__range=[start, end])
    if Staff_pk != 0: exp_q = exp_q.filter(To_id=Staff_pk)
    total_expenses = exp_q.aggregate(Sum('Amount'))['Amount__sum'] or 0
    category_expenses = exp_q.values('Category').annotate(total=Sum('Amount')).order_by('Category')

    context = {
        'start': start,
        'end': end,
        'Staff': Staff_pk,
        'Freq': Frequency,
        'Collection_Data': Collection_Data,
        'Penalty_Data': Penalty_Data,
        'File_Charge_Data': File_Charge_Data,
        'amntcollected': totalAmntCollected,
        'amnttobecollected': totalAmntToBeCollected,
        'penaltycollected': totalPenaltyCollected,
        'filecollected': totalFileChargeCollected,
        'amntfinanced': totalAmntFinanced,
        'total_penalty_waived': total_penalty_waived,
        'total_interest_waived': total_interest_waived,
        'total_expenses': total_expenses,
        'category_expenses': category_expenses,
        'net_collection': totalAmntCollected + totalPenaltyCollected + totalFileChargeCollected - total_expenses,
        'Date': datetime.now(local_timezone).date(),
    }
    
    return render(request, 'microfinance/Officerwise_Total_Finance_And_Collection_Report.html', context)

