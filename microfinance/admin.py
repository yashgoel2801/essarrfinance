from django.contrib import admin
from django.contrib.auth.models import Group

# Register your models here.
from .models import Loans,Documents,Penalty,Guarantor_Documents,Guarantors,Accounts,Staff,Expenditures, Installments,Clients,Payments
 
admin.site.site_header='Essarrfinance'
admin.site.index_title="Essarrfinance"

admin.site.unregister(Group)




class ClientsAdmin(admin.ModelAdmin):
    list_display=('pk','Image','Name','Phone_no1','Reference_Name')
    search_fields = ['pk','Image','Name','Phone_no1','Reference_Name']
    list_display_links=('Name',)



class LoansAdmin(admin.ModelAdmin):
    list_display=('pk' ,'Client_Id','AccNo','Client','Principle_Amount','Frequency','FileCharge','NoOfInstallments')
    search_fields = ['pk','Account__Client__pk']
    #list_display_links=('Name',)
    def Client(self, obj):
        return obj.Account.Client.Name
    def Client_Id(self, obj):
        return obj.Account.Client.pk
    def FileCharge(self, obj):
        return obj.File_Charge_Percent * obj.Principle_Amount/100
    def NoOfInstallments(self,obj):
        if(obj.Frequency==2):
            if obj.No_Of_Installments%7!=0:
                return int(obj.No_Of_Installments/7 )+1
            else:
                return int(obj.No_Of_Installments/7)


class InstallmentsAdmin(admin.ModelAdmin):
    list_display=('Date_Due','Date_Paid','Loan','Client')
    search_fields = ['Loan__id']
    def Client(self, obj):
        return obj.Loan.Account.Client.Name
    


admin.site.register(Loans,LoansAdmin)
admin.site.register(Installments,InstallmentsAdmin)
admin.site.register(Clients,ClientsAdmin)
admin.site.register(Documents)
admin.site.register(Guarantors)
admin.site.register(Guarantor_Documents)
admin.site.register(Accounts)
admin.site.register(Staff)
admin.site.register(Expenditures)
admin.site.register(Penalty)
admin.site.register(Payments)



