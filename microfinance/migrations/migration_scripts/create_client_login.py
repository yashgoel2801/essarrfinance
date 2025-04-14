from django.db import migrations
from django.contrib.auth.models import User,Permission


def create_users_for_clients(apps, schema_editor):
    Client = apps.get_model('your_app_name', 'Client')  # Get the Client model
    permission = Permission.objects.get(codename='client_view') 
    for client in Client.objects.all():
        username = client.Phone_no1
        password = client.Name[:4]+ client.Photo_Id_No[-4:]  # First four letters of first name

        # Create the user if it doesn't exist
        if not User.objects.filter(username=username).exists():
            user = User.objects.create_user(
                username=username,
                password=password,
            )
            user.user_permissions.add(permission)
            # Link the user to the client
            client.ClientUser = user
            client.save()

class Migration(migrations.Migration):

    dependencies = [
        ('microfinance', ''),  # Replace with your app and migration dependency
    ]

    operations = [
        migrations.RunPython(create_users_for_clients),
    ]