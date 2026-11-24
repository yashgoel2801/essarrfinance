from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
import pytz
from microfinance.models import Loans,Installments,Payments,Penalty,Waiver
from microfinance.overdraft import overdraft_total_owed
from microfinance.overdraft_sync import ensure_overdraft_installments
from microfinance.views import bulk_overdue_map
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

    # OverDraft dues are materialized lazily; bring them up to date before reading them.
    for loan in Loan:
        if loan.Frequency == 4:
            ensure_overdraft_installments(loan)
    overdue_by_loan = bulk_overdue_map(loan_ids, today_date)

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
        if loan.Frequency == 4:
            # OverDraft owes outstanding principal plus unpaid interest, not a flat P*(1+rate).
            total_bal = overdraft_total_owed(loan, as_of=today_date)

        total_amnt_to_be_coll_dic[l_id] = round(total_amnt_to_be_coll, 1)
        total_amnt_collected_dic[l_id] = round(total_amnt_collected, 1)
        total_amnt_pending_dic[l_id] = overdue_by_loan.get(l_id, 0)
        total_bal_dic[l_id] = round(total_bal, 1)

        total_amnt_pending_for_all_cases += total_amnt_pending_dic[l_id]
        total_amnt_to_be_coll_for_all_cases += total_amnt_to_be_coll_dic[l_id]
        total_amnt_bal_for_all_cases += total_bal_dic[l_id]

    return render(request,'microfinance/Officer_And_Frequency_Wise_Report.html',{'loans':Loan,'Today':today_date,'Staff':Staff_pk,'Frequency':Frequency,'Total_Amnt_Pending':total_amnt_pending_for_all_cases,'Total_bal_dic':total_bal_dic,'Total_amt_to_be_col_dic':total_amnt_to_be_coll_dic,'Total_amt_col_dic':total_amnt_collected_dic,'Total_Pen_dic':total_amnt_pending_dic,'Total_Amnt_to_be_Collected':total_amnt_to_be_coll_for_all_cases,'Total_Amnt_Balance':total_amnt_bal_for_all_cases})
