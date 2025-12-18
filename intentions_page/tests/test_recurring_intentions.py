from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.management import call_command
from io import StringIO
from datetime import date, timedelta
from intentions_page.models import Intention, RecurringIntention
from intentions_page.tools import (
    create_recurring_intention_executor,
    list_recurring_intentions_executor,
    pause_recurring_intention_executor,
    resume_recurring_intention_executor,
    update_recurring_intention_executor,
    delete_recurring_intention_executor,
)

User = get_user_model()


class RecurringIntentionModelDailyTest(TestCase):
    """Test daily recurrence patterns"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.start_date = date(2025, 1, 1)

    def test_daily_every_day(self):
        recurring = RecurringIntention.objects.create(
            title='Daily standup',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=True
        )

        # Should match every day
        should_gen, reason = recurring.should_generate_for_date(self.start_date)
        self.assertTrue(should_gen)

        should_gen, reason = recurring.should_generate_for_date(self.start_date + timedelta(days=1))
        self.assertTrue(should_gen)

        should_gen, reason = recurring.should_generate_for_date(self.start_date + timedelta(days=100))
        self.assertTrue(should_gen)

    def test_daily_every_three_days(self):
        recurring = RecurringIntention.objects.create(
            title='Every 3 days',
            creator=self.user,
            frequency='daily',
            interval=3,
            start_date=self.start_date,
            is_active=True
        )

        # Day 0: should match (start date)
        should_gen, _ = recurring.should_generate_for_date(self.start_date)
        self.assertTrue(should_gen)

        # Day 1: should not match
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=1))
        self.assertFalse(should_gen)

        # Day 2: should not match
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=2))
        self.assertFalse(should_gen)

        # Day 3: should match
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=3))
        self.assertTrue(should_gen)

        # Day 6: should match
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=6))
        self.assertTrue(should_gen)


class RecurringIntentionModelWeeklyTest(TestCase):
    """Test weekly recurrence patterns"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        # January 6, 2025 is a Monday
        self.start_date = date(2025, 1, 6)

    def test_weekly_mondays_only(self):
        recurring = RecurringIntention.objects.create(
            title='Monday meeting',
            creator=self.user,
            frequency='weekly',
            interval=1,
            days_of_week=[0],  # Monday
            start_date=self.start_date,
            is_active=True
        )

        # Monday (day 0)
        should_gen, _ = recurring.should_generate_for_date(self.start_date)
        self.assertTrue(should_gen)

        # Tuesday (day 1)
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=1))
        self.assertFalse(should_gen)

        # Next Monday (day 7)
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=7))
        self.assertTrue(should_gen)

    def test_weekly_multiple_days(self):
        recurring = RecurringIntention.objects.create(
            title='Workout',
            creator=self.user,
            frequency='weekly',
            interval=1,
            days_of_week=[0, 2, 4],  # Monday, Wednesday, Friday
            start_date=self.start_date,
            is_active=True
        )

        # Monday
        should_gen, _ = recurring.should_generate_for_date(self.start_date)
        self.assertTrue(should_gen)

        # Tuesday
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=1))
        self.assertFalse(should_gen)

        # Wednesday
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=2))
        self.assertTrue(should_gen)

        # Thursday
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=3))
        self.assertFalse(should_gen)

        # Friday
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=4))
        self.assertTrue(should_gen)

    def test_weekly_every_two_weeks(self):
        recurring = RecurringIntention.objects.create(
            title='Bi-weekly check-in',
            creator=self.user,
            frequency='weekly',
            interval=2,
            days_of_week=[0],  # Monday
            start_date=self.start_date,
            is_active=True
        )

        # First Monday
        should_gen, _ = recurring.should_generate_for_date(self.start_date)
        self.assertTrue(should_gen)

        # Next Monday (7 days later, week 1)
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=7))
        self.assertFalse(should_gen)

        # Monday 14 days later (week 2)
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=14))
        self.assertTrue(should_gen)

    def test_weekly_no_days_configured(self):
        recurring = RecurringIntention.objects.create(
            title='Broken weekly',
            creator=self.user,
            frequency='weekly',
            interval=1,
            days_of_week=None,
            start_date=self.start_date,
            is_active=True
        )

        should_gen, reason = recurring.should_generate_for_date(self.start_date)
        self.assertFalse(should_gen)
        self.assertIn('No days of week configured', reason)


class RecurringIntentionModelMonthlyTest(TestCase):
    """Test monthly recurrence patterns"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.start_date = date(2025, 1, 15)

    def test_monthly_15th_of_month(self):
        recurring = RecurringIntention.objects.create(
            title='Monthly report',
            creator=self.user,
            frequency='monthly',
            interval=1,
            day_of_month=15,
            start_date=self.start_date,
            is_active=True
        )

        # January 15 (start date)
        should_gen, _ = recurring.should_generate_for_date(date(2025, 1, 15))
        self.assertTrue(should_gen)

        # January 16
        should_gen, _ = recurring.should_generate_for_date(date(2025, 1, 16))
        self.assertFalse(should_gen)

        # February 15
        should_gen, _ = recurring.should_generate_for_date(date(2025, 2, 15))
        self.assertTrue(should_gen)

        # March 15
        should_gen, _ = recurring.should_generate_for_date(date(2025, 3, 15))
        self.assertTrue(should_gen)

    def test_monthly_every_three_months(self):
        recurring = RecurringIntention.objects.create(
            title='Quarterly review',
            creator=self.user,
            frequency='monthly',
            interval=3,
            day_of_month=1,
            start_date=date(2025, 1, 1),
            is_active=True
        )

        # January 1 (month 0)
        should_gen, _ = recurring.should_generate_for_date(date(2025, 1, 1))
        self.assertTrue(should_gen)

        # February 1 (month 1)
        should_gen, _ = recurring.should_generate_for_date(date(2025, 2, 1))
        self.assertFalse(should_gen)

        # March 1 (month 2)
        should_gen, _ = recurring.should_generate_for_date(date(2025, 3, 1))
        self.assertFalse(should_gen)

        # April 1 (month 3)
        should_gen, _ = recurring.should_generate_for_date(date(2025, 4, 1))
        self.assertTrue(should_gen)

    def test_monthly_end_of_month_edge_case(self):
        """Test day 31 pattern in February (should use last day of month)"""
        recurring = RecurringIntention.objects.create(
            title='End of month task',
            creator=self.user,
            frequency='monthly',
            interval=1,
            day_of_month=31,
            start_date=date(2025, 1, 31),
            is_active=True
        )

        # January 31 (has 31 days)
        should_gen, _ = recurring.should_generate_for_date(date(2025, 1, 31))
        self.assertTrue(should_gen)

        # February 28 (last day of Feb, non-leap year)
        should_gen, _ = recurring.should_generate_for_date(date(2025, 2, 28))
        self.assertTrue(should_gen)

        # February 27 (not last day)
        should_gen, _ = recurring.should_generate_for_date(date(2025, 2, 27))
        self.assertFalse(should_gen)

        # March 31
        should_gen, _ = recurring.should_generate_for_date(date(2025, 3, 31))
        self.assertTrue(should_gen)

        # April 30 (April only has 30 days)
        should_gen, _ = recurring.should_generate_for_date(date(2025, 4, 30))
        self.assertTrue(should_gen)

    def test_monthly_no_day_configured(self):
        recurring = RecurringIntention.objects.create(
            title='Broken monthly',
            creator=self.user,
            frequency='monthly',
            interval=1,
            day_of_month=None,
            start_date=self.start_date,
            is_active=True
        )

        should_gen, reason = recurring.should_generate_for_date(self.start_date)
        self.assertFalse(should_gen)
        self.assertIn('No day of month configured', reason)


class RecurringIntentionModelYearlyTest(TestCase):
    """Test yearly recurrence patterns"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.start_date = date(2025, 3, 15)

    def test_yearly_march_15(self):
        recurring = RecurringIntention.objects.create(
            title='Tax deadline',
            creator=self.user,
            frequency='yearly',
            interval=1,
            month=3,
            day_of_month=15,
            start_date=self.start_date,
            is_active=True
        )

        # March 15, 2025 (start year)
        should_gen, _ = recurring.should_generate_for_date(date(2025, 3, 15))
        self.assertTrue(should_gen)

        # March 16, 2025
        should_gen, _ = recurring.should_generate_for_date(date(2025, 3, 16))
        self.assertFalse(should_gen)

        # March 15, 2026
        should_gen, _ = recurring.should_generate_for_date(date(2026, 3, 15))
        self.assertTrue(should_gen)

        # March 15, 2027
        should_gen, _ = recurring.should_generate_for_date(date(2027, 3, 15))
        self.assertTrue(should_gen)

    def test_yearly_every_two_years(self):
        recurring = RecurringIntention.objects.create(
            title='Biennial event',
            creator=self.user,
            frequency='yearly',
            interval=2,
            month=6,
            day_of_month=1,
            start_date=date(2025, 6, 1),
            is_active=True
        )

        # 2025 (year 0)
        should_gen, _ = recurring.should_generate_for_date(date(2025, 6, 1))
        self.assertTrue(should_gen)

        # 2026 (year 1)
        should_gen, _ = recurring.should_generate_for_date(date(2026, 6, 1))
        self.assertFalse(should_gen)

        # 2027 (year 2)
        should_gen, _ = recurring.should_generate_for_date(date(2027, 6, 1))
        self.assertTrue(should_gen)

    def test_yearly_leap_year_feb_29(self):
        """Test Feb 29 pattern in non-leap years (should use Feb 28)"""
        recurring = RecurringIntention.objects.create(
            title='Leap day celebration',
            creator=self.user,
            frequency='yearly',
            interval=1,
            month=2,
            day_of_month=29,
            start_date=date(2024, 2, 29),  # 2024 is a leap year
            is_active=True
        )

        # Feb 29, 2024 (leap year)
        should_gen, _ = recurring.should_generate_for_date(date(2024, 2, 29))
        self.assertTrue(should_gen)

        # Feb 28, 2025 (non-leap year, should use last day)
        should_gen, _ = recurring.should_generate_for_date(date(2025, 2, 28))
        self.assertTrue(should_gen)

        # Feb 29, 2028 (next leap year)
        should_gen, _ = recurring.should_generate_for_date(date(2028, 2, 29))
        self.assertTrue(should_gen)


class RecurringIntentionModelConstraintsTest(TestCase):
    """Test is_active, start_date, and end_date constraints"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.start_date = date(2025, 1, 15)

    def test_inactive_pattern_never_generates(self):
        recurring = RecurringIntention.objects.create(
            title='Inactive task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=False
        )

        should_gen, reason = recurring.should_generate_for_date(self.start_date)
        self.assertFalse(should_gen)
        self.assertIn('not active', reason)

    def test_before_start_date(self):
        recurring = RecurringIntention.objects.create(
            title='Future task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=True
        )

        before_start = self.start_date - timedelta(days=1)
        should_gen, reason = recurring.should_generate_for_date(before_start)
        self.assertFalse(should_gen)
        self.assertIn('before start date', reason)

    def test_after_end_date(self):
        recurring = RecurringIntention.objects.create(
            title='Limited task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            end_date=self.start_date + timedelta(days=10),
            is_active=True
        )

        # Within range
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=5))
        self.assertTrue(should_gen)

        # On end date
        should_gen, _ = recurring.should_generate_for_date(self.start_date + timedelta(days=10))
        self.assertTrue(should_gen)

        # After end date
        after_end = self.start_date + timedelta(days=11)
        should_gen, reason = recurring.should_generate_for_date(after_end)
        self.assertFalse(should_gen)
        self.assertIn('after end date', reason)

    def test_no_end_date_continues_indefinitely(self):
        recurring = RecurringIntention.objects.create(
            title='Forever task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            end_date=None,
            is_active=True
        )

        # Far future should still match
        far_future = self.start_date + timedelta(days=365 * 10)
        should_gen, _ = recurring.should_generate_for_date(far_future)
        self.assertTrue(should_gen)


class RecurringIntentionGenerationTest(TestCase):
    """Test generate_intention_for_date method"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.today = date(2025, 1, 15)

    def test_successful_generation(self):
        recurring = RecurringIntention.objects.create(
            title='Daily task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=True
        )

        intention = recurring.generate_intention_for_date(self.today)

        self.assertIsNotNone(intention)
        self.assertEqual(intention.title, 'Daily task')
        self.assertEqual(intention.date, self.today)
        self.assertEqual(intention.creator, self.user)
        self.assertEqual(intention.recurring_intention, recurring)
        self.assertFalse(intention.completed)
        self.assertFalse(intention.neverminded)

    def test_duplicate_prevention(self):
        recurring = RecurringIntention.objects.create(
            title='Daily task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=True
        )

        # First generation succeeds
        intention1 = recurring.generate_intention_for_date(self.today)
        self.assertIsNotNone(intention1)

        # Second generation returns None (duplicate)
        intention2 = recurring.generate_intention_for_date(self.today)
        self.assertIsNone(intention2)

        # Only one intention exists
        count = Intention.objects.filter(
            creator=self.user,
            date=self.today,
            title='Daily task',
            recurring_intention=recurring
        ).count()
        self.assertEqual(count, 1)

    def test_default_flags_applied(self):
        recurring = RecurringIntention.objects.create(
            title='Flagged task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=True,
            default_sticky=True,
            default_anxiety_inducing=True
        )

        intention = recurring.generate_intention_for_date(self.today)

        self.assertTrue(intention.sticky)
        self.assertTrue(intention.anxiety_inducing)
        self.assertFalse(intention.froggy)

    def test_frog_generation_success(self):
        recurring = RecurringIntention.objects.create(
            title='Daily frog',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=True,
            default_froggy=True
        )

        intention = recurring.generate_intention_for_date(self.today)

        self.assertIsNotNone(intention)
        self.assertTrue(intention.froggy)

    def test_frog_constraint_prevents_generation(self):
        """If a frog already exists, don't create another"""
        # Create existing frog
        Intention.objects.create(
            title='Existing frog',
            date=self.today,
            creator=self.user,
            froggy=True
        )

        recurring = RecurringIntention.objects.create(
            title='Would-be frog',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=True,
            default_froggy=True
        )

        intention = recurring.generate_intention_for_date(self.today)

        # Should return None because frog already exists
        self.assertIsNone(intention)

        # Verify only the original frog exists
        frogs = Intention.objects.filter(creator=self.user, date=self.today, froggy=True)
        self.assertEqual(frogs.count(), 1)
        self.assertEqual(frogs.first().title, 'Existing frog')

    def test_last_generated_date_updated(self):
        recurring = RecurringIntention.objects.create(
            title='Daily task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=True
        )

        self.assertIsNone(recurring.last_generated_date)

        recurring.generate_intention_for_date(self.today)

        recurring.refresh_from_db()
        self.assertEqual(recurring.last_generated_date, self.today)

    def test_wont_generate_if_shouldnt(self):
        """If should_generate_for_date returns False, don't create"""
        recurring = RecurringIntention.objects.create(
            title='Weekly task',
            creator=self.user,
            frequency='weekly',
            interval=1,
            days_of_week=[0],  # Monday only
            start_date=date(2025, 1, 6),  # A Monday
            is_active=True
        )

        # Try to generate on Tuesday
        tuesday = date(2025, 1, 7)
        intention = recurring.generate_intention_for_date(tuesday)

        self.assertIsNone(intention)
        self.assertEqual(Intention.objects.filter(creator=self.user).count(), 0)


class CreateRecurringIntentionToolTest(TestCase):
    """Test create_recurring_intention_executor tool"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.start_date = date(2025, 1, 15)

    def test_create_daily_pattern(self):
        tool_input = {
            'title': 'Daily standup',
            'frequency': 'daily',
            'interval': 1,
            'start_date': self.start_date.isoformat()
        }

        result = create_recurring_intention_executor(tool_input, user=self.user)

        self.assertEqual(result['title'], 'Daily standup')
        self.assertEqual(result['frequency'], 'daily')
        self.assertIn('daily', result['pattern'])
        self.assertTrue(result['is_active'])

        recurring = RecurringIntention.objects.get(id=result['recurring_intention_id'])
        self.assertEqual(recurring.frequency, 'daily')
        self.assertEqual(recurring.interval, 1)

    def test_create_weekly_pattern(self):
        tool_input = {
            'title': 'Weekly meeting',
            'frequency': 'weekly',
            'interval': 1,
            'days_of_week': [0, 2, 4],  # Mon, Wed, Fri
            'start_date': self.start_date.isoformat()
        }

        result = create_recurring_intention_executor(tool_input, user=self.user)

        self.assertEqual(result['frequency'], 'weekly')
        self.assertIn('Mon', result['pattern'])
        self.assertIn('Wed', result['pattern'])
        self.assertIn('Fri', result['pattern'])

    def test_create_monthly_pattern(self):
        tool_input = {
            'title': 'Monthly report',
            'frequency': 'monthly',
            'interval': 1,
            'day_of_month': 15,
            'start_date': self.start_date.isoformat()
        }

        result = create_recurring_intention_executor(tool_input, user=self.user)

        self.assertEqual(result['frequency'], 'monthly')
        self.assertIn('15', result['pattern'])

    def test_create_yearly_pattern(self):
        tool_input = {
            'title': 'Birthday',
            'frequency': 'yearly',
            'interval': 1,
            'month': 3,
            'day_of_month': 15,
            'start_date': self.start_date.isoformat()
        }

        result = create_recurring_intention_executor(tool_input, user=self.user)

        self.assertEqual(result['frequency'], 'yearly')
        self.assertIn('3/15', result['pattern'])

    def test_create_with_end_date(self):
        end_date = self.start_date + timedelta(days=30)
        tool_input = {
            'title': 'Limited task',
            'frequency': 'daily',
            'interval': 1,
            'start_date': self.start_date.isoformat(),
            'end_date': end_date.isoformat()
        }

        result = create_recurring_intention_executor(tool_input, user=self.user)

        self.assertEqual(result['end_date'], end_date.isoformat())

    def test_create_with_default_flags(self):
        tool_input = {
            'title': 'Flagged task',
            'frequency': 'daily',
            'interval': 1,
            'start_date': self.start_date.isoformat(),
            'default_sticky': True,
            'default_froggy': True,
            'default_anxiety_inducing': True
        }

        result = create_recurring_intention_executor(tool_input, user=self.user)

        recurring = RecurringIntention.objects.get(id=result['recurring_intention_id'])
        self.assertTrue(recurring.default_sticky)
        self.assertTrue(recurring.default_froggy)
        self.assertTrue(recurring.default_anxiety_inducing)

    def test_missing_title(self):
        tool_input = {
            'frequency': 'daily',
            'start_date': self.start_date.isoformat()
        }

        with self.assertRaisesMessage(ValueError, 'Title is required'):
            create_recurring_intention_executor(tool_input, user=self.user)

    def test_missing_frequency(self):
        tool_input = {
            'title': 'Task',
            'start_date': self.start_date.isoformat()
        }

        with self.assertRaisesMessage(ValueError, 'frequency is required'):
            create_recurring_intention_executor(tool_input, user=self.user)

    def test_invalid_frequency(self):
        tool_input = {
            'title': 'Task',
            'frequency': 'minutely',
            'start_date': self.start_date.isoformat()
        }

        with self.assertRaisesMessage(ValueError, 'Invalid frequency'):
            create_recurring_intention_executor(tool_input, user=self.user)

    def test_missing_start_date(self):
        tool_input = {
            'title': 'Task',
            'frequency': 'daily'
        }

        with self.assertRaisesMessage(ValueError, 'start_date is required'):
            create_recurring_intention_executor(tool_input, user=self.user)

    def test_end_date_before_start_date(self):
        tool_input = {
            'title': 'Task',
            'frequency': 'daily',
            'start_date': self.start_date.isoformat(),
            'end_date': (self.start_date - timedelta(days=1)).isoformat()
        }

        with self.assertRaisesMessage(ValueError, 'end_date cannot be before start_date'):
            create_recurring_intention_executor(tool_input, user=self.user)

    def test_weekly_missing_days_of_week(self):
        tool_input = {
            'title': 'Weekly task',
            'frequency': 'weekly',
            'start_date': self.start_date.isoformat()
        }

        with self.assertRaisesMessage(ValueError, 'days_of_week is required for weekly'):
            create_recurring_intention_executor(tool_input, user=self.user)

    def test_monthly_missing_day_of_month(self):
        tool_input = {
            'title': 'Monthly task',
            'frequency': 'monthly',
            'start_date': self.start_date.isoformat()
        }

        with self.assertRaisesMessage(ValueError, 'day_of_month is required for monthly'):
            create_recurring_intention_executor(tool_input, user=self.user)

    def test_yearly_missing_month(self):
        tool_input = {
            'title': 'Yearly task',
            'frequency': 'yearly',
            'day_of_month': 15,
            'start_date': self.start_date.isoformat()
        }

        with self.assertRaisesMessage(ValueError, 'month is required for yearly'):
            create_recurring_intention_executor(tool_input, user=self.user)


class ListRecurringIntentionsToolTest(TestCase):
    """Test list_recurring_intentions_executor tool"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.start_date = date(2025, 1, 15)

    def test_list_empty(self):
        tool_input = {}
        result = list_recurring_intentions_executor(tool_input, user=self.user)

        self.assertEqual(result['count'], 0)
        self.assertEqual(len(result['recurring_intentions']), 0)

    def test_list_active_only_default(self):
        # Create active pattern
        RecurringIntention.objects.create(
            title='Active task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=True
        )

        # Create inactive pattern
        RecurringIntention.objects.create(
            title='Inactive task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=False
        )

        tool_input = {}
        result = list_recurring_intentions_executor(tool_input, user=self.user)

        self.assertEqual(result['count'], 1)
        self.assertTrue(result['active_only'])
        self.assertEqual(result['recurring_intentions'][0]['title'], 'Active task')

    def test_list_all_including_inactive(self):
        RecurringIntention.objects.create(
            title='Active task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=True
        )

        RecurringIntention.objects.create(
            title='Inactive task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=False
        )

        tool_input = {'active_only': False}
        result = list_recurring_intentions_executor(tool_input, user=self.user)

        self.assertEqual(result['count'], 2)
        self.assertFalse(result['active_only'])

    def test_list_shows_pattern_details(self):
        RecurringIntention.objects.create(
            title='Weekly task',
            creator=self.user,
            frequency='weekly',
            interval=1,
            days_of_week=[0, 4],
            start_date=self.start_date,
            is_active=True,
            default_sticky=True
        )

        tool_input = {}
        result = list_recurring_intentions_executor(tool_input, user=self.user)

        ri = result['recurring_intentions'][0]
        self.assertEqual(ri['title'], 'Weekly task')
        self.assertEqual(ri['frequency'], 'weekly')
        self.assertIn('Mon', ri['pattern'])
        self.assertIn('Fri', ri['pattern'])
        self.assertTrue(ri['default_sticky'])
        self.assertTrue(ri['is_active'])

    def test_user_isolation(self):
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )

        RecurringIntention.objects.create(
            title='My task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=True
        )

        RecurringIntention.objects.create(
            title='Other task',
            creator=other_user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=True
        )

        tool_input = {}
        result = list_recurring_intentions_executor(tool_input, user=self.user)

        self.assertEqual(result['count'], 1)
        self.assertEqual(result['recurring_intentions'][0]['title'], 'My task')


class PauseRecurringIntentionToolTest(TestCase):
    """Test pause_recurring_intention_executor tool"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.start_date = date(2025, 1, 15)
        self.recurring = RecurringIntention.objects.create(
            title='Daily task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=True
        )

    def test_pause_active_pattern(self):
        tool_input = {'recurring_intention_id': self.recurring.id}
        result = pause_recurring_intention_executor(tool_input, user=self.user)

        self.assertFalse(result['is_active'])
        self.assertIn('paused', result['message'])

        self.recurring.refresh_from_db()
        self.assertFalse(self.recurring.is_active)

    def test_pause_already_paused(self):
        self.recurring.is_active = False
        self.recurring.save()

        tool_input = {'recurring_intention_id': self.recurring.id}
        result = pause_recurring_intention_executor(tool_input, user=self.user)

        self.assertFalse(result['is_active'])
        self.assertIn('already paused', result['message'])

    def test_pause_missing_id(self):
        tool_input = {}

        with self.assertRaisesMessage(ValueError, 'recurring_intention_id is required'):
            pause_recurring_intention_executor(tool_input, user=self.user)

    def test_pause_nonexistent_id(self):
        tool_input = {'recurring_intention_id': 99999}

        with self.assertRaisesMessage(ValueError, 'not found'):
            pause_recurring_intention_executor(tool_input, user=self.user)

    def test_pause_other_user_pattern(self):
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )

        tool_input = {'recurring_intention_id': self.recurring.id}

        with self.assertRaisesMessage(ValueError, 'not found'):
            pause_recurring_intention_executor(tool_input, user=other_user)


class ResumeRecurringIntentionToolTest(TestCase):
    """Test resume_recurring_intention_executor tool"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.start_date = date(2025, 1, 15)
        self.recurring = RecurringIntention.objects.create(
            title='Daily task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=False
        )

    def test_resume_paused_pattern(self):
        tool_input = {'recurring_intention_id': self.recurring.id}
        result = resume_recurring_intention_executor(tool_input, user=self.user)

        self.assertTrue(result['is_active'])
        self.assertIn('resumed', result['message'])

        self.recurring.refresh_from_db()
        self.assertTrue(self.recurring.is_active)

    def test_resume_already_active(self):
        self.recurring.is_active = True
        self.recurring.save()

        tool_input = {'recurring_intention_id': self.recurring.id}
        result = resume_recurring_intention_executor(tool_input, user=self.user)

        self.assertTrue(result['is_active'])
        self.assertIn('already active', result['message'])


class UpdateRecurringIntentionToolTest(TestCase):
    """Test update_recurring_intention_executor tool"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.start_date = date(2025, 1, 15)
        self.recurring = RecurringIntention.objects.create(
            title='Original title',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=True
        )

    def test_update_title(self):
        tool_input = {
            'recurring_intention_id': self.recurring.id,
            'title': 'New title'
        }
        result = update_recurring_intention_executor(tool_input, user=self.user)

        self.assertEqual(result['title'], 'New title')
        self.assertEqual(len(result['changes']), 1)

        self.recurring.refresh_from_db()
        self.assertEqual(self.recurring.title, 'New title')

    def test_update_frequency(self):
        tool_input = {
            'recurring_intention_id': self.recurring.id,
            'frequency': 'weekly',
            'days_of_week': [0, 2]
        }
        result = update_recurring_intention_executor(tool_input, user=self.user)

        self.recurring.refresh_from_db()
        self.assertEqual(self.recurring.frequency, 'weekly')
        self.assertEqual(self.recurring.days_of_week, [0, 2])

    def test_no_changes(self):
        tool_input = {
            'recurring_intention_id': self.recurring.id,
            'title': 'Original title'
        }
        result = update_recurring_intention_executor(tool_input, user=self.user)

        self.assertEqual(len(result['changes']), 0)
        self.assertIn('No changes made', result['message'])


class DeleteRecurringIntentionToolTest(TestCase):
    """Test delete_recurring_intention_executor tool"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.start_date = date(2025, 1, 15)
        self.recurring = RecurringIntention.objects.create(
            title='Task to delete',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.start_date,
            is_active=True
        )

    def test_delete_pattern(self):
        recurring_id = self.recurring.id
        tool_input = {'recurring_intention_id': recurring_id}
        result = delete_recurring_intention_executor(tool_input, user=self.user)

        self.assertEqual(result['recurring_intention_id'], recurring_id)
        self.assertIn('deleted', result['message'])

        with self.assertRaises(RecurringIntention.DoesNotExist):
            RecurringIntention.objects.get(id=recurring_id)

    def test_delete_preserves_generated_intentions(self):
        # Generate an intention
        intention = self.recurring.generate_intention_for_date(self.start_date)
        intention_id = intention.id

        # Delete the recurring pattern
        tool_input = {'recurring_intention_id': self.recurring.id}
        delete_recurring_intention_executor(tool_input, user=self.user)

        # Intention should still exist but with null recurring_intention
        intention.refresh_from_db()
        self.assertEqual(intention.id, intention_id)
        self.assertIsNone(intention.recurring_intention)


class ManagementCommandTest(TestCase):
    """Test generate_recurring_intentions management command"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.today = date(2025, 1, 15)

    def test_command_generates_for_today(self):
        RecurringIntention.objects.create(
            title='Daily task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=True
        )

        out = StringIO()
        call_command('generate_recurring_intentions', '--date', self.today.isoformat(), stdout=out)

        output = out.getvalue()
        self.assertIn('Daily task', output)
        self.assertIn('Created intention', output)

        # Verify intention was created
        intentions = Intention.objects.filter(creator=self.user, date=self.today)
        self.assertEqual(intentions.count(), 1)
        self.assertEqual(intentions.first().title, 'Daily task')

    def test_command_dry_run(self):
        RecurringIntention.objects.create(
            title='Daily task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=True
        )

        out = StringIO()
        call_command(
            'generate_recurring_intentions',
            '--date', self.today.isoformat(),
            '--dry-run',
            stdout=out
        )

        output = out.getvalue()
        self.assertIn('DRY RUN', output)
        self.assertIn('Would create', output)

        # Verify NO intention was created
        intentions = Intention.objects.filter(creator=self.user, date=self.today)
        self.assertEqual(intentions.count(), 0)

    def test_command_multiple_days(self):
        RecurringIntention.objects.create(
            title='Daily task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=True
        )

        out = StringIO()
        call_command(
            'generate_recurring_intentions',
            '--date', self.today.isoformat(),
            '--days', '3',
            stdout=out
        )

        # Should generate for today, tomorrow, and day after
        intentions = Intention.objects.filter(creator=self.user)
        self.assertEqual(intentions.count(), 4)  # 4 days total (0, 1, 2, 3)

    def test_command_user_filter(self):
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )

        RecurringIntention.objects.create(
            title='User 1 task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=True
        )

        RecurringIntention.objects.create(
            title='User 2 task',
            creator=other_user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=True
        )

        out = StringIO()
        call_command(
            'generate_recurring_intentions',
            '--date', self.today.isoformat(),
            '--user-id', str(self.user.id),
            stdout=out
        )

        # Only user 1's task should be created
        intentions = Intention.objects.filter(date=self.today)
        self.assertEqual(intentions.count(), 1)
        self.assertEqual(intentions.first().title, 'User 1 task')

    def test_command_skips_duplicates(self):
        recurring = RecurringIntention.objects.create(
            title='Daily task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=True
        )

        # Run command once
        call_command('generate_recurring_intentions', '--date', self.today.isoformat(), stdout=StringIO())

        # Run command again
        out = StringIO()
        call_command('generate_recurring_intentions', '--date', self.today.isoformat(), stdout=out)

        output = out.getvalue()
        self.assertIn('Skipped (duplicate)', output)

        # Still only one intention
        intentions = Intention.objects.filter(creator=self.user, date=self.today)
        self.assertEqual(intentions.count(), 1)

    def test_command_skips_inactive(self):
        RecurringIntention.objects.create(
            title='Inactive task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=self.today,
            is_active=False
        )

        out = StringIO()
        call_command('generate_recurring_intentions', '--date', self.today.isoformat(), stdout=out)

        # No intentions should be created
        intentions = Intention.objects.filter(creator=self.user, date=self.today)
        self.assertEqual(intentions.count(), 0)
