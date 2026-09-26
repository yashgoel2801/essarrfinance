# Deploy: nightly OverDraft sync

Pre-materializes every open OverDraft loan's interest/principal state once
a night, so the Overdue Loans screen and reports read pre-synced rows
instead of paying the replay cost on every page load, and so an overdue
loan is visible even if nobody has opened it recently. Runs the ordinary
incremental sync (`sync_overdraft_loan`) — never a rebuild — so it never
touches an already-settled Installment row; correction workflows (editing
or deleting a payment) still trigger their own rebuild on demand.

## Install (run once on the server, as root)

```bash
cp deploy/essarr-sync.service deploy/essarr-sync.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now essarr-sync.timer
systemctl list-timers essarr-sync.timer
```

Verify the next scheduled fire time actually is 4 AM IST before trusting it:

```bash
systemd-analyze calendar "*-*-* 04:00:00 Asia/Kolkata"
```

## Retry behavior

Two independent layers:

1. **Per-loan, inside one run.** Each loan syncs in its own transaction;
   one loan raising is logged and skipped, the rest still sync. See
   `microfinance/management/commands/sync_overdraft_loans.py`.
2. **Run-level, via systemd.** The command exits non-zero if any loan
   failed. `essarr-sync.service` restarts up to 3 times, 10 minutes apart,
   within a 1-hour window (`Restart=on-failure`, bounded by
   `StartLimitBurst`/`StartLimitIntervalSec`) — then stops. A loan still
   broken after that will be retried again at the next 4 AM run
   (`Persistent=true` also catches a run the server missed entirely, e.g.
   a reboot at 4 AM).

## Checking it ran

```bash
systemctl status essarr-sync.service
journalctl -u essarr-sync.service -n 50
```

The command's stdout ends with a summary line, `Synced N, failed M.` — that
line is what lands in the journal.

## Manual / targeted runs

```bash
cd /root/essarr-2026 && .venv/bin/python manage.py sync_overdraft_loans --dry-run
cd /root/essarr-2026 && .venv/bin/python manage.py sync_overdraft_loans --loan-id 2510
```

## Migration note

This branch's migration `0012_overdraft_principal_choice` drops
`Loans.Principal_Threshold_Percent` and adds `Payments.Apply_To_Principal`.
Run `manage.py migrate` **before** restarting the `essarr` service on
deploy — skipping it will 500 every `Loans`/`Payments` query.
