# Generated by Django 3.0.5 on 2021-01-24 16:06

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('microfinance', '0010_auto_20210124_1605'),
    ]

    operations = [
        migrations.AlterField(
            model_name='loans',
            name='Reminder',
            field=models.DateField(default=datetime.datetime(2021, 1, 24, 16, 6, 43, 538299)),
        ),
    ]
