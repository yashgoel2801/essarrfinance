from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
import pytz
from microfinance.models import Loans,Installments,Payments
local_timezone = pytz.timezone('Asia/Kolkata')

@login_required(login_url="/accounts/login/")
def Officer_And_Frequency_Wise_pdf(request):
    if request.method =="POST":
        List = request.POST.getlist('Check') 
        status =(request.POST.get('status'))
        Loan = Loans.objects.none()
        for i in List:
            n = Loans.objects.filter(id=i)            
            Loan|= n
        
        Installment = Installments.objects.filter(Loan__in=Loan).order_by('Date_Due').filter(Date_Due__lte =datetime.now())
        Installment = Payments.objects.filter(Loan__in=Loan)

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
            payments = Payments.objects.filter(Loan=loan)
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
        return render(request,'microfinance/pdfs/Officer_And_Frequency_Wise_pdf.html',{'loans':Loan,'Today':today,'TotalAmnt':total_amnt_pending_for_all_cases,'Total_bal_dic':total_bal_dic,'Total_amt_to_be_col_dic':total_amnt_to_be_coll_dic,'Total_amt_col_dic':total_amnt_collected_dic,'Total_Pen_dic':total_amnt_pending_dic})
