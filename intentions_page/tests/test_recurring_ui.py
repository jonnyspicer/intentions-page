from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from datetime import date
from intentions_page.models import Intention, RecurringIntention

User = get_user_model()


class IntentionIsRecurringPropertyTest(TestCase):
    """Test the is_recurring property"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.intention = Intention.objects.create(
            title='Test Intention',
            creator=self.user,
            date=date(2025, 1, 15)
        )

    def test_is_recurring_returns_false_when_no_pattern(self):
        """Intention without recurring pattern returns False"""
        self.assertFalse(self.intention.is_recurring)

    def test_is_recurring_returns_true_when_active_pattern(self):
        """Intention with active recurring pattern returns True"""
        recurring = RecurringIntention.objects.create(
            title='Test Intention',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=date(2025, 1, 15),
            is_active=True
        )
        self.intention.recurring_intention = recurring
        self.intention.save()

        self.assertTrue(self.intention.is_recurring)

    def test_is_recurring_returns_false_when_inactive_pattern(self):
        """Intention with inactive recurring pattern returns False"""
        recurring = RecurringIntention.objects.create(
            title='Test Intention',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=date(2025, 1, 15),
            is_active=False
        )
        self.intention.recurring_intention = recurring
        self.intention.save()

        self.assertFalse(self.intention.is_recurring)


class GetOrCreateRecurringPatternTest(TestCase):
    """Test the get_or_create_recurring_pattern method"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.intention = Intention.objects.create(
            title='Daily Task',
            creator=self.user,
            date=date(2025, 1, 15),
            sticky=True,
            froggy=True,
            anxiety_inducing=True
        )

    def test_creates_new_pattern_when_none_exists(self):
        """Creates a new RecurringIntention when none exists"""
        recurring, created = self.intention.get_or_create_recurring_pattern()

        self.assertTrue(created)
        self.assertIsNotNone(recurring)
        self.assertEqual(recurring.title, 'Daily Task')
        self.assertEqual(recurring.creator, self.user)
        self.assertEqual(recurring.frequency, 'daily')
        self.assertEqual(recurring.interval, 1)
        self.assertEqual(recurring.start_date, date(2025, 1, 15))
        self.assertTrue(recurring.is_active)

    def test_returns_existing_pattern_when_already_exists(self):
        """Returns existing pattern without creating a new one"""
        # Create pattern first
        recurring1, created1 = self.intention.get_or_create_recurring_pattern()

        # Try to create again
        recurring2, created2 = self.intention.get_or_create_recurring_pattern()

        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(recurring1.id, recurring2.id)

    def test_flags_default_to_false(self):
        """Flags default to False to avoid edge cases"""
        recurring, created = self.intention.get_or_create_recurring_pattern()

        # Even though the intention has flags set, the pattern should default to False
        self.assertFalse(recurring.default_sticky)
        self.assertFalse(recurring.default_froggy)
        self.assertFalse(recurring.default_anxiety_inducing)

    def test_only_links_current_intention(self):
        """Only links the current intention, not past intentions with same title"""
        # Create another intention with the same title
        past_intention = Intention.objects.create(
            title='Daily Task',
            creator=self.user,
            date=date(2025, 1, 10)
        )

        # Create recurring pattern from current intention
        recurring, created = self.intention.get_or_create_recurring_pattern()

        # Refresh to get updated FK
        self.intention.refresh_from_db()
        past_intention.refresh_from_db()

        # Current intention should be linked
        self.assertEqual(self.intention.recurring_intention, recurring)

        # Past intention should NOT be linked
        self.assertIsNone(past_intention.recurring_intention)

    def test_links_intention_to_pattern(self):
        """Intention is properly linked to the created pattern"""
        recurring, created = self.intention.get_or_create_recurring_pattern()

        self.intention.refresh_from_db()
        self.assertEqual(self.intention.recurring_intention, recurring)


class RecurringToggleViewTest(TestCase):
    """Test the view logic for toggling recurring status"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)

        self.intention = Intention.objects.create(
            title='Test Task',
            creator=self.user,
            date=date(2025, 1, 15)
        )

    def test_toggle_on_creates_pattern(self):
        """Toggling recurring ON creates a RecurringIntention"""
        response = self.client.post(
            f'/edit/{self.intention.id}',
            {'toggle_recurring': '1'}
        )

        # View returns the template render (200) - no redirect
        self.assertIn(response.status_code, [200, 302])

        # Check that pattern was created
        self.intention.refresh_from_db()
        self.assertIsNotNone(self.intention.recurring_intention)
        self.assertTrue(self.intention.is_recurring)

        # Check pattern properties
        pattern = self.intention.recurring_intention
        self.assertEqual(pattern.frequency, 'daily')
        self.assertEqual(pattern.interval, 1)
        self.assertTrue(pattern.is_active)

    def test_toggle_off_deactivates_pattern(self):
        """Toggling recurring OFF deactivates the pattern"""
        # First create a recurring pattern
        recurring = RecurringIntention.objects.create(
            title='Test Task',
            creator=self.user,
            frequency='daily',
            interval=1,
            start_date=date(2025, 1, 15),
            is_active=True
        )
        self.intention.recurring_intention = recurring
        self.intention.save()

        # Toggle it off
        response = self.client.post(
            f'/edit/{self.intention.id}',
            {'toggle_recurring': '1'}
        )

        self.assertIn(response.status_code, [200, 302])

        # Check that pattern was deactivated (not deleted)
        recurring.refresh_from_db()
        self.assertFalse(recurring.is_active)
        self.assertFalse(self.intention.is_recurring)

    def test_permission_denied_for_other_user(self):
        """Cannot toggle recurring for another user's intention"""
        # Create another user and log in as them
        other_user = User.objects.create_user(username='otheruser', password='testpass')
        self.client.force_login(other_user)

        # Try to toggle the original user's intention
        response = self.client.post(
            f'/edit/{self.intention.id}',
            {'toggle_recurring': '1'}
        )

        # Should be denied (403) or redirect to login (302)
        self.assertIn(response.status_code, [302, 403])


class RecurringToggleIntegrationTest(TestCase):
    """Integration tests for recurring toggle functionality"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)

    def test_toggle_on_then_off_then_on(self):
        """Can toggle recurring status multiple times"""
        intention = Intention.objects.create(
            title='Toggle Test',
            creator=self.user,
            date=date(2025, 1, 15)
        )

        # Toggle ON
        self.client.post(f'/edit/{intention.id}', {'toggle_recurring': '1'})
        intention.refresh_from_db()
        self.assertTrue(intention.is_recurring)
        pattern_id = intention.recurring_intention.id

        # Toggle OFF
        self.client.post(f'/edit/{intention.id}', {'toggle_recurring': '1'})
        intention.refresh_from_db()
        self.assertFalse(intention.is_recurring)

        # Pattern still exists but is inactive
        pattern = RecurringIntention.objects.get(id=pattern_id)
        self.assertFalse(pattern.is_active)

        # Toggle ON again - should reactivate the same pattern
        self.client.post(f'/edit/{intention.id}', {'toggle_recurring': '1'})
        intention.refresh_from_db()
        self.assertTrue(intention.is_recurring)
