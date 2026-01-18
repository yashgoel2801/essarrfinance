from datetime import datetime, timedelta
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.db.models import Sum
from microfinance.models import Loans, Installments, Payments


@login_required(login_url="/accounts/login/")
def Month_Chart_List(request):
    if request.method != 'POST':
        return redirect('microfinance:reports')
    
    try:
        Staff_pk = int(request.POST.get('name', 0))
    except (ValueError, TypeError):
        Staff_pk = 0
    
    DueDate = request.POST.get('DueDate', 0)  # Specific date filter (1-31) or 0 for all
    try:
        DueDate = int(DueDate)
    except (ValueError, TypeError):
        DueDate = 0
    
    # Filter monthly loans (Frequency=3)
    if Staff_pk != 0 and DueDate != 0:
        Loan = Loans.objects.filter(Loan_Collector_id=Staff_pk, Status=False, Frequency=3, First_Due_Date__day=DueDate)
        lon = Loans.objects.filter(Loan_Collector_id=Staff_pk, Status=False, Frequency=3).exclude(First_Due_Date__day=DueDate)
    elif Staff_pk != 0 and DueDate == 0:
        Loan = Loans.objects.filter(Loan_Collector_id=Staff_pk, Status=False, Frequency=3)
        lon = Loans.objects.none()
    elif Staff_pk == 0 and DueDate != 0:
        Loan = Loans.objects.filter(Status=False, Frequency=3, First_Due_Date__day=DueDate)
        lon = Loans.objects.filter(Status=False, Frequency=3).exclude(First_Due_Date__day=DueDate)
    else:
        Loan = Loans.objects.filter(Status=False, Frequency=3)
        lon = Loans.objects.none()
    
    # Initialize dictionaries for tracking
    dic = {}
    dic2 = {}
    Dic1 = {i: 0 for i in range(1, 32)}  # Days 1-31
    Dic2 = {i: 0 for i in range(1, 32)}
    Def1 = 0
    Def2 = 0
    
    # Find defaulters (loans with missed payments in the last 60 days)
    sdate = (datetime.now() - timedelta(days=1)).date()
    edate = (datetime.now() - timedelta(days=60)).date()
    dd = [sdate - timedelta(days=x) for x in range((sdate - edate).days)]
    
    x = Loans.objects.none()
    if lon.exists():
        for i in dd:
            for j in lon.filter(First_Due_Date__day=i.day):
                last_payment = j.installments_set.filter(Date_Paid__isnull=False).order_by('-Date_Paid', '-Date_Due').first()
                if last_payment:
                    if last_payment.Date_Paid < i:
                        x |= lon.filter(pk=j.pk)
                else:
                    x |= lon.filter(pk=j.pk)
    
    today_date = datetime.now().date()
    
    # Calculate defaulter totals
    if x.exists():
        for l in x:
            first_inst = l.installments_set.first()
            if first_inst:
                Def1 += first_inst.Installment_Due
            
            # Robust Pending Calculation
            totalPending = 0
            due_insts = Installments.objects.filter(Loan=l, Date_Due__lte=today_date).order_by('Date_Due')
            total_paid_agg = Payments.objects.filter(Loan=l, Payment_Type=1, Date_Paid__lte=today_date).aggregate(Sum('Amount_Paid'))['Amount_Paid__sum']
            total_paid = total_paid_agg if total_paid_agg else 0
            
            for i in due_insts:
                amount_to_cover = i.Installment_Due
                used_amount = min(total_paid, amount_to_cover)
                total_paid -= used_amount
                pending = amount_to_cover - used_amount
                totalPending += pending
            
            dic2[l.pk] = totalPending
            Def2 += totalPending
            if totalPending <= 0:
                x = x.exclude(pk=l.pk)
    
    # Calculate main loan totals
    TotalPendingSum = 0
    for l in Loan:
        first_inst = l.installments_set.first()
        if first_inst:
            day_of_month = first_inst.Date_Due.day
            if 1 <= day_of_month <= 31:
                Dic1[day_of_month] += first_inst.Installment_Due
        
        # Robust Pending Calculation
        totalPending = 0
        due_insts = Installments.objects.filter(Loan=l, Date_Due__lte=today_date).order_by('Date_Due')
        total_paid_agg = Payments.objects.filter(Loan=l, Payment_Type=1, Date_Paid__lte=today_date).aggregate(Sum('Amount_Paid'))['Amount_Paid__sum']
        total_paid = total_paid_agg if total_paid_agg else 0
        
        for i in due_insts:
            amount_to_cover = i.Installment_Due
            used_amount = min(total_paid, amount_to_cover)
            total_paid -= used_amount
            pending = amount_to_cover - used_amount
            
            if pending > 0:
                day_idx = i.Date_Due.day
                if 1 <= day_idx <= 31:
                    Dic2[day_idx] += pending
                totalPending += pending
        
        dic[l.pk] = totalPending
        TotalPendingSum += totalPending
    
    DateName = f"Day {DueDate}" if DueDate != 0 else "All Monthly Loans"
    
    if DueDate == 0:
        return render(request, 'microfinance/Month_Chart.html', {
            'Loan': Loan,
            'dic': dic,
            'Staff': Staff_pk,
            'Total': Dic1,
            'TotalPen': Dic2,
            'TotalPendingSum': TotalPendingSum
        })
    else:
        return render(request, 'microfinance/month_chart2.html', {
            'Loan': Loan,
            'dic': dic,
            'dic2': dic2,
            'Staff': Staff_pk,
            'Total': Dic1,
            'TotalPen': Dic2,
            'Def1': Def1,
            'Def2': Def2,
            'lon': x,
            'TotalPendingSum': TotalPendingSum,
            'DateName': DateName,
            'DueDate': DueDate
        })
