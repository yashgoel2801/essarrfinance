from django.apps import AppConfig


class MicrofinanceConfig(AppConfig):
    name = 'microfinance'

    # def ready(self):
    #     import sys
    #     # Avoid running during migrations or helper commands
    #     if 'runserver' in sys.argv:
    #         from django.core.management import call_command
    #         try:
    #             # We use a slight delay or simple call
    #             # Note: This runs every time the server reloads in development
    #             print("Checking for unsynced client credentials...")
    #             call_command('sync_client_users')
    #         except Exception as e:
    #             print(f"Startup sync failed: {e}")

