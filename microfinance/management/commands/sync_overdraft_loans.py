from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from microfinance.models import Loans
from microfinance.overdraft_sync import sync_overdraft_loan


class Command(BaseCommand):
    help = (
        "Pre-materializes every open OverDraft loan's Installments rows via "
        "the ordinary incremental sync (sync_overdraft_loan) -- never a "
        "rebuild, which is reserved for deliberate payment corrections. "
        "Intended to run nightly (see deploy/essarr-sync.service and "
        "deploy/essarr-sync.timer) so the Overdue Loans screen and reports "
        "read pre-synced rows instead of paying the replay cost on every "
        "page load, and so a genuinely overdue loan is visible even if "
        "nobody has opened it or recorded a payment recently."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Count open OverDraft loans without syncing any of them.',
        )
        parser.add_argument(
            '--loan-id', type=int, default=None,
            help='Sync only this one loan (for a targeted rerun after fixing a failure).',
        )

    def handle(self, *args, **options):
        loans = Loans.objects.filter(Frequency=4, Status=False)
        if options['loan_id'] is not None:
            loans = loans.filter(pk=options['loan_id'])

        if options['dry_run']:
            count = loans.count()
            self.stdout.write(f"Would sync {count} open OverDraft loan(s). No changes made.")
            return

        synced = 0
        failed = []
        for loan in loans:
            try:
                with transaction.atomic():
                    sync_overdraft_loan(loan)
                synced += 1
            except Exception as e:
                failed.append(loan.pk)
                self.stderr.write(self.style.ERROR(f"Loan {loan.pk} failed to sync: {e}"))

        self.stdout.write(f"Synced {synced}, failed {len(failed)}.")
        if failed:
            raise CommandError(
                f"{len(failed)} loan(s) failed to sync: {failed}. "
                f"Tonight's run will retry them automatically; for an "
                f"immediate rerun use --loan-id."
            )
