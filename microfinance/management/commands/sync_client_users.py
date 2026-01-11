import re
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Permission
from microfinance.models import Clients

class Command(BaseCommand):
    help = 'Ensures all clients have a linked User account for login'

    def handle(self, *args, **options):
        clients_without_user = Clients.objects.filter(ClientUser__isnull=True)
        self.stdout.write(f"Found {clients_without_user.count()} clients without users.")

        permission = Permission.objects.get(codename='client_view')
        
        count = 0
        for client in clients_without_user:
            try:
                # 1. Clean Username (Digits only from Phone_no1)
                username = re.sub(r'\D', '', str(client.Phone_no1))
                if not username:
                    self.stdout.write(self.style.WARNING(f"Skipping {client.Name} (ID: {client.pk}): No valid phone number"))
                    continue

                # 2. Generate Password
                name_part = client.Name.replace(" ", "").upper()[:4]
                photo_id = client.Photo_Id_No
                if photo_id:
                    id_part = str(photo_id)[-4:]
                else:
                    id_part = username[-4:]
                
                password = name_part + id_part

                # 3. Create or Get User
                user, created = User.objects.get_or_create(username=username)
                if created:
                    user.set_password(password)
                    user.save()
                    user.user_permissions.add(permission)
                    self.stdout.write(self.style.SUCCESS(f"Created user for {client.Name}: {username} / {password}"))
                else:
                    self.stdout.write(f"User {username} already exists. Linking to {client.Name}")

                # 4. Link back to Client
                client.ClientUser = user
                client.save()
                count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing client {client.pk}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f"Finished. Synced {count} clients."))
