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
    print('2',datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))
    
    # 0. Gather Loans financed in this period (for File Charges)
    loanswithLoanDateInRange = loans.filter(Loan_Date__range=[start, end])
    
    # Optimize ID Gathering: Query the child tables directly instead of complex unions on the parent.
    # This avoids the slow "OR/DISTINCT" patterns on the Loans table.
    
    # 1. Gather Installment Loan IDs
    inst_ids_query = Installments.objects.filter(
        Date_Due__range=[start, end],
        Installment_Due__gt=0
    )
    if Staff_pk != 0 or Frequency != 0:
        inst_ids_query = inst_ids_query.filter(Loan__in=loans)
    inst_loan_ids = list(inst_ids_query.values_list('Loan_id', flat=True).distinct())

    # 2. Gather Penalty Loan IDs
    pen_ids_query = Penalty.objects.filter(Date_Started__range=[start, end])
    if Staff_pk != 0 or Frequency != 0:
        pen_ids_query = pen_ids_query.filter(Loan__in=loans)
    pen_ids_list = list(pen_ids_query.values_list('Loan_id', flat=True).distinct())

    # 3. Gather Payment (Collection) Loan IDs
    pay_ids_query = Payments.objects.filter(Date_Paid__range=[start, end])
    if Staff_pk != 0 or Frequency != 0:
        pay_ids_query = pay_ids_query.filter(Loan__in=loans)
    
    # Split by payment type to match previous logic
    inst_pay_ids = list(pay_ids_query.filter(Payment_Type=1).values_list('Loan_id', flat=True).distinct())
    pen_pay_ids = list(pay_ids_query.filter(Payment_Type=2).values_list('Loan_id', flat=True).distinct())

    # Combine IDs for the lists
    installment_section_loan_ids = list(set(inst_loan_ids + inst_pay_ids))
    penalty_section_loan_ids = list(set(pen_ids_list + pen_pay_ids))
    
    # We'll use these IDs to fetch the Loan objects efficiently
    loansWihtInstallmentOrPaidDateInRange = Loans.objects.filter(id__in=installment_section_loan_ids).select_related('Account__Client', 'Loan_Collector')
    loansWihtPenaltyOrItsPaidDateInRange = Loans.objects.filter(id__in=penalty_section_loan_ids).select_related('Account__Client', 'Loan_Collector')
    
    print('3',datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))
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
    # Process Penalty Calculations
    print('3.5', 'Fetching penalties for', len(penalty_section_loan_ids), 'loans at', datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))
    today_date = datetime.now(local_timezone).date()
    
    # Fetching penalties and doing date math in Python is often faster than 
    # complex DB annotations on PostgreSQL if the Query Planner gets confused.
    penalties = Penalty.objects.filter(Loan_id__in=penalty_section_loan_ids).only(
        'Loan_id', 'Status', 'Penalty_Paid', 'Date_Ended', 'Penalty_Calc', 'Amount', 'Percent', 'Date_Started', 'Waived_Amount'
    )
    
    Penalty_To_Be_Collected = {}
    for p in penalties:
        val = 0
        if p.Status:
            val = p.Penalty_Paid
        elif p.Date_Ended:
            val = p.Penalty_Calc
        else:
            days = (today_date - p.Date_Started).days
            if days > 0:
                val = (p.Amount * p.Percent * days) / 100
        
        # Subtract Waived_Amount (individual)
        val = max(0, val - p.Waived_Amount)
        if val > 0:
            Penalty_To_Be_Collected[p.Loan_id] = Penalty_To_Be_Collected.get(p.Loan_id, 0) + val

    print('4', 'Processed', len(Penalty_To_Be_Collected), 'loans with penalties at', datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))
    
    # Bulk fetch Installment Totals
    inst_loan_ids = installment_section_loan_ids
    payment_loan_ids = list(set(installment_section_loan_ids + penalty_section_loan_ids)) # For Payment data below - include ALL loans
    # Bulk fetch Penalty Payments Within Date Range
    payment_data = Payments.objects.filter(
        Loan_id__in=payment_loan_ids,
        Date_Paid__range=[start, end]
    ).values('Loan_id', 'Payment_Type').annotate(total=Sum('Amount_Paid'))

    Penalty_Collected = {}
    totalPenaltyCollected = 0
    for item in payment_data:
        if item['Payment_Type'] == 2:
            Penalty_Collected[item['Loan_id']] = {'Amount_Paid__sum': item['total']}
            totalPenaltyCollected += item['total']

    # Bulk fetch Installment Totals
    inst_data = Installments.objects.filter(
        Loan_id__in=inst_loan_ids,
        Date_Due__range=[start, end]
    ).values('Loan_id').annotate(total=Sum('Installment_Due'))
    
    Amnt_To_Be_Collected = {}
    totalAmntToBeCollected = 0
    for item in inst_data:
        Amnt_To_Be_Collected[item['Loan_id']] = {'Installment_Due__sum': item['total']}
        totalAmntToBeCollected += item['total']

    # Bulk fetch Installment Payment Totals
    Amnt_Collected = {}
    totalAmntCollected = 0
    for item in payment_data:
        if item['Payment_Type'] == 1:
            Amnt_Collected[item['Loan_id']] = {'Amount_Paid__sum': item['total']}
            totalAmntCollected += item['total']

    # Fetch and subtract general waivers (Waiver model)
    all_general_waivers = Waiver.objects.filter(
        Loan_id__in=list(set(installment_section_loan_ids + penalty_section_loan_ids)),
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

    # Calculate total waivers for display
    total_penalty_waived_display = sum(item['total'] for item in all_general_waivers if item['Waiver_Type'] == 1)
    total_interest_waived_display = sum(item['total'] for item in all_general_waivers if item['Waiver_Type'] == 2)
    
    # Calculate payment status for each loan (Paid in Advance, On Track, Pending)
    # We need to compare total payments made vs total installments due up to today
    import pytz
    local_tz = pytz.timezone('Asia/Kolkata')
    today = datetime.now(local_tz).date()
    
    # Get all installments due up to today for these loans
    all_loan_ids = list(set(installment_section_loan_ids + penalty_section_loan_ids))
    total_due_to_date = Installments.objects.filter(
        Loan_id__in=all_loan_ids,
        Date_Due__lte=today
    ).values('Loan_id').annotate(total_due=Sum('Installment_Due'))
    total_due_dict = {item['Loan_id']: item['total_due'] for item in total_due_to_date}
    
    # Get all payments made (all time) for these loans
    total_paid_all_time = Payments.objects.filter(
        Loan_id__in=all_loan_ids,
        Payment_Type=1
    ).values('Loan_id').annotate(total_paid=Sum('Amount_Paid'))
    total_paid_dict = {item['Loan_id']: item['total_paid'] for item in total_paid_all_time}
    
    # Get waivers for accurate status
    waiver_totals_dict = {}
    for item in all_general_waivers:
        if item['Waiver_Type'] == 2:  # Interest waiver
            waiver_totals_dict[item['Loan_id']] = waiver_totals_dict.get(item['Loan_id'], 0) + item['total']
    
    # Calculate status for each loan
    Payment_Status = {}
    for loan_id in all_loan_ids:
        total_due = total_due_dict.get(loan_id, 0)
        total_paid = total_paid_dict.get(loan_id, 0)
        total_waived = waiver_totals_dict.get(loan_id, 0)
        
        # Adjust due amount for waivers
        adjusted_due = max(0, total_due - total_waived)
        
        if total_paid >= adjusted_due + 100:  # 100 rupee buffer for "paid in advance"
            Payment_Status[loan_id] = 'advance'
        elif total_paid >= adjusted_due - 50:  # 50 rupee tolerance for "on track"
            Payment_Status[loan_id] = 'on_track'
        else:
            Payment_Status[loan_id] = 'pending'
    
    # --- Expense Calculation START ---
    from microfinance.models import Expenditures
    
    expenses_query = Expenditures.objects.filter(Date__range=[start, end])
    
    if Staff_pk != 0:
        expenses_query = expenses_query.filter(To_id=Staff_pk)
        
    total_expenses = expenses_query.aggregate(Sum('Amount'))['Amount__sum'] or 0
    category_expenses = expenses_query.values('Category').annotate(total=Sum('Amount')).order_by('Category')
    # --- Expense Calculation END ---

    print('5',datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S"))
    return render(request,'microfinance/Officerwise_Total_Finance_And_Collection_Report.html',{
        'start':start,
        'end':end,
        'Staff':Staff_pk,
        'Freq':Frequency,
        'amnt_collected':Amnt_Collected,
        'Loan':loansWihtInstallmentOrPaidDateInRange,
        'Loan3':loanswithLoanDateInRange,
        'Loan2':loansWihtPenaltyOrItsPaidDateInRange,
        'amntcollected':totalAmntCollected,
        'amnttobecollected':totalAmntToBeCollected,
        'amnt_to_be_collected':Amnt_To_Be_Collected,
        'penalty_collected':Penalty_Collected,
        'penaltycollected':totalPenaltyCollected,
        'file_charge':File_Charge,
        'filecollected':totalFileChargeCollected,
        'penalty_to_be_collected':Penalty_To_Be_Collected,
        'total_penalty_waived': total_penalty_waived_display,
        'total_interest_waived': total_interest_waived_display,
        'payment_status': Payment_Status,
        'total_expenses': total_expenses,
        'category_expenses': category_expenses,
        'net_collection': totalAmntCollected + totalPenaltyCollected + totalFileChargeCollected - total_expenses
    })
