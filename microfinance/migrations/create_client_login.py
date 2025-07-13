from django.db import migrations
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType


def create_users_for_clients(apps, schema_editor):
    Clients = apps.get_model('microfinance', 'Clients')

    # Get ContentType for Clients model
    content_type = ContentType.objects.get(app_label='microfinance', model='clients')

    # Create the permission if it doesn't exist
    permission, _ = Permission.objects.get_or_create(
        codename='client_view',
        name='Can view client details',
        content_type=content_type,
    )

    for client in Clients.objects.all()[:4]:
        username = str(client.Phone_no1)[3:] if client.Phone_no1 else None
        if not username:
            continue

        password = (client.Name[:4] + client.Photo_Id_No[-4:]) if client.Photo_Id_No else "pass1234"

        if not User.objects.filter(username=username).exists():
            user = User.objects.create_user(username=username, password=password)
            user.user_permissions.add(permission)
            user.save()

            # Assign the user to the client (assumes ForeignKey `ClientUser`)
            client.ClientUser_id = user.id
            client.save()


class Migration(migrations.Migration):

    dependencies = [
        ('microfinance', 'populate_payment_data'),  # replace with your last migration
    ]

    operations = [
        migrations.RunPython(create_users_for_clients),
        migrations.AlterModelOptions(
            name='clients',
            options={
                'permissions': [('client_view', 'Can view client details')],
            },
        ),
    ]