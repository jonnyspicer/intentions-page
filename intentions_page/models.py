from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

def get_working_day_date():
    datetime = timezone.now()
    next_day_starts_at = 4
    if datetime.hour < next_day_starts_at:
        return datetime.date() - timezone.timedelta(days=1)
    else:
        return datetime.date()

class Intention(models.Model):
    title = models.CharField(max_length=500)
    date = models.DateField(default=get_working_day_date)
    created_datetime = models.DateTimeField(default=timezone.now)
    order = models.IntegerField(default=0, db_index=True)

    creator = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    recurring_intention = models.ForeignKey(
        'RecurringIntention',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_intentions'
    )

    completed = models.BooleanField(default=False)
    neverminded = models.BooleanField(default=False)
    sticky = models.BooleanField(default=False)
    froggy = models.BooleanField(default=False)
    anxiety_inducing = models.BooleanField(default=False)

    class Meta:
        ordering = ['order', 'created_datetime']

    def __str__(self):
        return self.title

    def get_status(self):
        if self.completed:
            return 'completed'
        elif self.neverminded:
            return 'neverminded'
        else:
            return 'active'

    @property
    def is_recurring(self):
        """Check if this intention has an associated recurring pattern"""
        if self.recurring_intention:
            return self.recurring_intention.is_active
        return False

    def get_or_create_recurring_pattern(self):
        """
        Get or create a daily RecurringIntention pattern for this intention.

        Only links the current intention to the pattern (not past intentions with same title).
        Flags default to False to avoid conflicts (e.g., multiple frogs per day).

        Returns:
            Tuple of (RecurringIntention, created: bool)
        """
        if self.recurring_intention:
            return self.recurring_intention, False

        # Create a new daily recurring pattern
        # Note: Flags default to False to avoid edge cases (e.g., froggy constraint)
        recurring = RecurringIntention.objects.create(
            title=self.title,
            creator=self.creator,
            frequency='daily',
            interval=1,
            start_date=self.date,
            is_active=True,
            default_sticky=False,
            default_froggy=False,
            default_anxiety_inducing=False
        )

        # Link only this intention to the pattern (not past intentions)
        self.recurring_intention = recurring
        self.save(update_fields=['recurring_intention'])

        return recurring, True

    @classmethod
    def copy_sticky_intentions_forward(cls, user, from_date, to_date):
        """Copy sticky intentions from from_date to to_date for a user"""
        sticky_intentions = cls.objects.filter(
            creator=user,
            date=from_date,
            sticky=True,
            neverminded=False
        )

        for intention in sticky_intentions:
            # Avoid duplicates
            existing = cls.objects.filter(
                creator=user,
                date=to_date,
                title=intention.title,
                sticky=True
            ).exists()

            if not existing:
                cls.objects.create(
                    title=intention.title,
                    date=to_date,
                    creator=user,
                    sticky=True,
                    completed=False,
                    neverminded=False
                )

class IntentionsDraft(models.Model):
    content = models.TextField()
    date = models.DateField(default=get_working_day_date)
    creator = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    created_datetime = models.DateTimeField(default=timezone.now)
    version = models.IntegerField(default=0)  # Needed for autosaving

    class Meta:
        constraints = [models.UniqueConstraint(fields=['date', 'creator'], name='One intentions draft per user per day')]

class Note(models.Model):
    content = models.TextField()
    date = models.DateField(default=get_working_day_date)
    created_datetime = models.DateTimeField(default=timezone.now)
    creator = models.ForeignKey(User, on_delete=models.CASCADE, null=True)

    version = models.IntegerField(default=0)  # Needed for autosaving

    class Meta:
        constraints =[models.UniqueConstraint(fields=['date','creator'],name='One note per user per day')]

        ordering = ['-created_datetime']

class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('system', 'System'),
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]

    creator = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_datetime = models.DateTimeField(default=timezone.now)
    llm_provider = models.CharField(max_length=20, null=True, blank=True)  # 'claude' or 'openai'

    class Meta:
        ordering = ['created_datetime']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class AgentAction(models.Model):
    """
    Audit log for all agent tool executions.
    Records what actions the agent took on behalf of the user.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agent_actions')
    tool_name = models.CharField(max_length=100)
    tool_input = models.JSONField()  # The input parameters passed to the tool
    tool_output = models.JSONField(null=True, blank=True)  # The result returned by the tool
    success = models.BooleanField(default=True)
    error = models.TextField(null=True, blank=True)  # Error message if failed
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['tool_name']),
        ]

    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.tool_name} by {self.user.username} at {self.timestamp}"


class RecurringIntention(models.Model):
    """
    Defines a recurring pattern for automatically generating intentions.
    Supports daily, weekly, monthly, and yearly recurrence patterns.
    """
    # Core Fields
    title = models.CharField(max_length=500)
    creator = models.ForeignKey(User, on_delete=models.CASCADE, null=True)

    # Frequency Configuration
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    interval = models.PositiveIntegerField(default=1)  # Every N days/weeks/months/years

    # Pattern-specific fields
    days_of_week = models.JSONField(null=True, blank=True)  # [0-6] for weekly (0=Monday)
    day_of_month = models.PositiveIntegerField(null=True, blank=True)  # 1-31 for monthly
    month = models.PositiveIntegerField(null=True, blank=True)  # 1-12 for yearly

    # Active Period
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # Optional

    # Status
    is_active = models.BooleanField(default=True, db_index=True)

    # Default Flags for Generated Intentions
    default_sticky = models.BooleanField(default=False)
    default_froggy = models.BooleanField(default=False)
    default_anxiety_inducing = models.BooleanField(default=False)

    # Metadata
    created_datetime = models.DateTimeField(default=timezone.now)
    last_generated_date = models.DateField(null=True, blank=True)  # Track last generation

    class Meta:
        ordering = ['created_datetime']
        indexes = [
            models.Index(fields=['creator', 'is_active']),
            models.Index(fields=['is_active', 'frequency']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_frequency_display()})"

    def should_generate_for_date(self, target_date):
        """
        Determine if an intention should be generated for the given date.

        Args:
            target_date: datetime.date object

        Returns:
            (bool, str): (should_generate, reason_message)
        """
        import calendar
        import logging

        logger = logging.getLogger(__name__)

        # Check if active
        if not self.is_active:
            return False, "Recurring intention is not active"

        # Check if before start_date
        if target_date < self.start_date:
            return False, f"Date {target_date} is before start date {self.start_date}"

        # Check if after end_date (if set)
        if self.end_date and target_date > self.end_date:
            return False, f"Date {target_date} is after end date {self.end_date}"

        # Frequency-specific logic
        if self.frequency == 'daily':
            # Check interval: should generate every N days from start_date
            days_diff = (target_date - self.start_date).days
            if days_diff % self.interval == 0:
                return True, f"Daily pattern matches (every {self.interval} day(s))"
            return False, f"Daily interval {self.interval} doesn't match"

        elif self.frequency == 'weekly':
            # Check if target_date.weekday() is in days_of_week
            if not self.days_of_week:
                return False, "No days of week configured"

            weekday = target_date.weekday()  # 0=Monday, 6=Sunday
            if weekday in self.days_of_week:
                # Calculate weeks from the first occurrence of this weekday on or after start_date
                days_until_weekday = (weekday - self.start_date.weekday()) % 7
                first_occurrence = self.start_date + timezone.timedelta(days=days_until_weekday)

                # Check if target_date is before the first occurrence
                if target_date < first_occurrence:
                    return False, f"Date is before first occurrence ({first_occurrence})"

                # Check interval (every N weeks from first occurrence)
                weeks_diff = (target_date - first_occurrence).days // 7
                if weeks_diff % self.interval == 0:
                    return True, f"Weekly pattern matches (weekday {weekday})"
            return False, f"Weekly pattern doesn't match"

        elif self.frequency == 'monthly':
            # Check if target_date.day matches day_of_month
            if not self.day_of_month:
                return False, "No day of month configured"

            # Handle month-end edge cases (e.g., Feb 30 -> last day of Feb)
            last_day_of_month = calendar.monthrange(target_date.year, target_date.month)[1]
            target_day = min(self.day_of_month, last_day_of_month)

            if target_date.day == target_day:
                # Check interval (every N months from start_date)
                months_diff = (target_date.year - self.start_date.year) * 12 + (target_date.month - self.start_date.month)
                if months_diff % self.interval == 0:
                    return True, f"Monthly pattern matches (day {target_day})"
            return False, f"Monthly pattern doesn't match"

        elif self.frequency == 'yearly':
            # Check if target_date matches month + day_of_month
            if self.month and self.day_of_month:
                # Handle leap year edge cases
                last_day_of_month = calendar.monthrange(target_date.year, self.month)[1]
                target_day = min(self.day_of_month, last_day_of_month)

                if target_date.month == self.month and target_date.day == target_day:
                    # Check interval (every N years)
                    years_diff = target_date.year - self.start_date.year
                    if years_diff % self.interval == 0:
                        return True, f"Yearly pattern matches ({self.month}/{target_day})"
            return False, f"Yearly pattern doesn't match"

        return False, "Unknown frequency"

    def generate_intention_for_date(self, target_date):
        """
        Generate an Intention for target_date if it doesn't already exist.

        Args:
            target_date: datetime.date object

        Returns:
            Intention instance if created, None if duplicate exists or shouldn't generate
        """
        import logging

        logger = logging.getLogger(__name__)

        should_generate, reason = self.should_generate_for_date(target_date)

        if not should_generate:
            logger.debug(f"Not generating for {target_date}: {reason}")
            return None

        # Handle froggy constraint: can't create frog if one exists for this date
        if self.default_froggy:
            existing_frog = Intention.objects.filter(
                creator=self.creator,
                date=target_date,
                froggy=True
            ).exists()

            if existing_frog:
                logger.warning(
                    f"Skipping frog creation for {target_date}: frog already exists. "
                    f"Recurring pattern: {self.title}"
                )
                return None

        # Use get_or_create to prevent race conditions
        intention, created = Intention.objects.get_or_create(
            creator=self.creator,
            date=target_date,
            title=self.title,
            recurring_intention=self,
            defaults={
                'sticky': self.default_sticky,
                'froggy': self.default_froggy,
                'anxiety_inducing': self.default_anxiety_inducing,
                'completed': False,
                'neverminded': False
            }
        )

        if not created:
            logger.debug(f"Intention already exists for {target_date}: {self.title}")
            return None

        # Update last_generated_date
        self.last_generated_date = target_date
        self.save(update_fields=['last_generated_date'])

        logger.info(
            f"Generated recurring intention #{intention.id} for {target_date}: {self.title}"
        )

        return intention
