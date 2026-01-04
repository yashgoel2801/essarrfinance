from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
import pytz
from microfinance.models import Loans,Installments,Payments,Waiver
from django.db.models import Sum
local_timezone = pytz.timezone('Asia/Kolkata')

@login_required(login_url="/accounts/login/")
def Officer_And_Frequency_Wise_pdf(request):
    if request.method =="POST":
        List = request.POST.getlist('Check') 
        status = request.POST.get('status')
        Loan = Loans.objects.filter(id__in=List)
        
        today = datetime.now(local_timezone)
        today_date = today.date()
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

        total_amnt_to_be_coll_dic = {}
        total_amnt_collected_dic = {}
        total_amnt_pending_dic = {}
        total_bal_dic = {}
        total_amnt_pending_for_all_cases = 0
        total_amnt_to_be_coll_for_all_cases = 0
        total_amnt_bal_for_all_cases = 0

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
        return render(request,'microfinance/pdfs/Officer_And_Frequency_Wise_pdf.html',{'loans':Loan,'Today':today,'TotalAmnt':total_amnt_pending_for_all_cases,'Total_bal_dic':total_bal_dic,'Total_amt_to_be_col_dic':total_amnt_to_be_coll_dic,'Total_amt_col_dic':total_amnt_collected_dic,'Total_Pen_dic':total_amnt_pending_dic})
