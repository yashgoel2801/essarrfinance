from django.db import migrations
from django.contrib.auth.models import User,Permission,ContentType

from microfinance.models import Clients


def create_users_for_clients(apps, schema_editor):
    content_type = ContentType.objects.get_for_model(Clients)
    permission, created = Permission.objects.get_or_create(
        codename='client_view',
        content_type=content_type,
        defaults={'name': 'Can view client details'}
    )   
    Client = apps.get_model('microfinance', 'Clients')  # Get the Client model
    permission = Permission.objects.get(codename='client_view') 
    for client in Client.objects.all():
        username = str(client.Phone_no1)[3:]
        password = client.Name[:4]+ client.Photo_Id_No[-4:]  # First four letters of first name
        if not username:
            continue
        # Create the user if it doesn't exist
        if not User.objects.filter(username=username).exists():
            user = User.objects.create_user(
                username=username,
                password=password,
            )
            user.user_permissions.add(permission)
            user.save()
            client.ClientUser_id = user.pk
            # Link the user to the client
            # Clients.objects.get(pk =client.pk).ClientUser = user
            client.save()

class Migration(migrations.Migration):

    dependencies = [
        ('microfinance', 'alter_clients_options'),  # Replace with your app and migration dependency
    ]

    operations = [
        migrations.RunPython(create_users_for_clients),
        migrations.AlterModelOptions(
            name='clients',
            options={'permissions': [('client_view', 'Can view sensitive client data')]},
        ),
    ]