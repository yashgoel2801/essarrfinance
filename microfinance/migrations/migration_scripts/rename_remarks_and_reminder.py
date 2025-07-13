from django.db import migrations

def copy_fields(apps, schema_editor):
    Loan = apps.get_model('microfinance', 'Loan')
    for loan in Loan.objects.all():
        loan.Remarks = loan.remark
        loan.Reminders = loan.reminder
        loan.save(update_fields=['Remarks', 'Reminders'])

class Migration(migrations.Migration):

    dependencies = [
        ('microfinance', '0002_auto_add_remarks_reminders'),  # adjust based on your previous migration
    ]

    operations = [
        migrations.RunPython(copy_fields),
    ]