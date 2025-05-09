# Generated by Django 5.1 on 2024-09-16 14:40

import datetime
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('microfinance', '0019_alter_loans_reminder'),
    ]

    operations = [
        migrations.AlterField(
            model_name='loans',
            name='Frequency',
            field=models.IntegerField(choices=[(1, 'Daily'), (2, 'Weekly'), (3, 'Monthly'), (3, 'OverDraft')], default=1),
        ),
        migrations.AlterField(
            model_name='loans',
            name='reminder',
            field=models.DateField(blank=True, default=datetime.datetime(2024, 9, 16, 20, 10, 46, 324726), null=True),
        ),
        migrations.CreateModel(
            name='Payments',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('Date_Paid', models.DateField(blank=True, default=None, null=True)),
                ('Amount_Paid', models.FloatField(default=0)),
                ('Payment_Type', models.IntegerField(choices=[(1, 'installment'), (2, 'penalty')], default=1)),
                ('Loan', models.ForeignKey(default=0, on_delete=django.db.models.deletion.PROTECT, to='microfinance.loans')),
            ],
            options={
                'ordering': ['Loan_id', 'Date_Paid'],
            },
        ),
    ]
