from django.core.management.base import BaseCommand
from django.db import transaction
from intentions_page.models import RecurringIntention, get_working_day_date
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate intentions from active recurring patterns for today (or specified date)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Generate for specific date (YYYY-MM-DD). Defaults to today.',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=0,
            help='Generate for next N days (including today). Default: 0 (today only)',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Only generate for specific user ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would be generated without creating intentions',
        )

    def handle(self, *args, **options):
        from django.utils.dateparse import parse_date

        # Parse target date
        if options['date']:
            target_date = parse_date(options['date'])
            if not target_date:
                self.stderr.write(self.style.ERROR(f"Invalid date format: {options['date']}"))
                return
        else:
            target_date = get_working_day_date()

        days_ahead = options['days']
        user_id = options['user_id']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No intentions will be created"))

        # Get active recurring intentions
        recurring_intentions = RecurringIntention.objects.filter(is_active=True)

        if user_id:
            recurring_intentions = recurring_intentions.filter(creator_id=user_id)
            self.stdout.write(f"Filtering to user ID: {user_id}")

        total_patterns = recurring_intentions.count()
        self.stdout.write(f"Found {total_patterns} active recurring pattern(s)")

        # Generate for each date in range
        total_created = 0
        total_skipped = 0

        for day_offset in range(days_ahead + 1):
            current_date = target_date + timedelta(days=day_offset)
            self.stdout.write(f"\n--- Processing {current_date} ---")

            created_count = 0
            skipped_count = 0

            for recurring in recurring_intentions:
                should_generate, reason = recurring.should_generate_for_date(current_date)

                if should_generate:
                    if dry_run:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  [DRY RUN] Would create: {recurring.title} "
                                f"(pattern #{recurring.id})"
                            )
                        )
                        created_count += 1
                    else:
                        # Use transaction for safety
                        with transaction.atomic():
                            intention = recurring.generate_intention_for_date(current_date)

                            if intention:
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"  Created intention #{intention.id}: {intention.title} "
                                        f"(from pattern #{recurring.id})"
                                    )
                                )
                                created_count += 1
                            else:
                                self.stdout.write(
                                    f"  Skipped (duplicate): {recurring.title}"
                                )
                                skipped_count += 1
                else:
                    # Only log verbose skip reasons if --verbosity >= 2
                    if options['verbosity'] >= 2:
                        self.stdout.write(
                            self.style.WARNING(f"  Skipped: {recurring.title} - {reason}")
                        )
                    skipped_count += 1

            self.stdout.write(
                f"  Summary for {current_date}: {created_count} created, {skipped_count} skipped"
            )

            total_created += created_count
            total_skipped += skipped_count

        # Final summary
        self.stdout.write(self.style.SUCCESS(f"\n=== TOTAL SUMMARY ==="))
        self.stdout.write(f"Total intentions created: {total_created}")
        self.stdout.write(f"Total skipped: {total_skipped}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes were made"))
