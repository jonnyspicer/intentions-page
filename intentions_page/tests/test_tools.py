from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import date, timedelta
from intentions_page.models import Intention, get_working_day_date
from intentions_page.tools import ToolExecutor, create_intention_executor

User = get_user_model()


class CreateIntentionExecutorTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.today = get_working_day_date()

    def test_successful_intention_creation(self):
        tool_input = {
            'title': 'Test intention',
            'froggy': False,
            'sticky': False,
            'anxiety_inducing': False
        }

        result = create_intention_executor(tool_input, user=self.user)

        self.assertEqual(result['title'], 'Test intention')
        self.assertFalse(result['froggy'])
        self.assertEqual(result['date'], self.today.isoformat())
        self.assertIn('Successfully created intention', result['message'])

        intention = Intention.objects.get(id=result['intention_id'])
        self.assertEqual(intention.title, 'Test intention')
        self.assertEqual(intention.creator, self.user)

    def test_title_validation_empty(self):
        tool_input = {'title': '   '}

        with self.assertRaisesMessage(ValueError, 'Title is required and cannot be empty'):
            create_intention_executor(tool_input, user=self.user)

    def test_title_validation_too_long(self):
        tool_input = {'title': 'a' * 501}

        with self.assertRaisesMessage(ValueError, 'Title cannot exceed 500 characters'):
            create_intention_executor(tool_input, user=self.user)

    def test_invalid_date_format(self):
        tool_input = {
            'title': 'Test',
            'date': 'not-a-date'
        }

        with self.assertRaisesMessage(ValueError, 'Invalid date format'):
            create_intention_executor(tool_input, user=self.user)

    def test_specific_date(self):
        tomorrow = self.today + timedelta(days=1)
        tool_input = {
            'title': 'Future task',
            'date': tomorrow.isoformat()
        }

        result = create_intention_executor(tool_input, user=self.user)

        self.assertEqual(result['date'], tomorrow.isoformat())

    def test_frog_validation_only_one_per_day(self):
        Intention.objects.create(
            title='Existing frog',
            date=self.today,
            creator=self.user,
            froggy=True
        )

        tool_input = {
            'title': 'Second frog',
            'froggy': True
        }

        with self.assertRaisesMessage(ValueError, 'A frog already exists'):
            create_intention_executor(tool_input, user=self.user)

    def test_concurrent_frog_creation_prevented(self):
        from django.db import connection
        from threading import Thread
        from django.db.utils import OperationalError
        import time

        results = {'thread1': None, 'thread2': None}

        def create_frog(thread_name):
            try:
                # Small delay to increase chance of collision
                time.sleep(0.01)
                result = create_intention_executor(
                    {'title': f'Frog from {thread_name}', 'froggy': True},
                    user=self.user
                )
                results[thread_name] = {'success': True, 'result': result}
            except ValueError as e:
                results[thread_name] = {'success': False, 'error': str(e), 'error_type': 'ValueError'}
            except OperationalError as e:
                # SQLite database locking is expected in concurrent scenarios
                results[thread_name] = {'success': False, 'error': str(e), 'error_type': 'OperationalError'}

        connection.close()

        thread1 = Thread(target=create_frog, args=('thread1',))
        thread2 = Thread(target=create_frog, args=('thread2',))

        thread1.start()
        thread2.start()

        thread1.join(timeout=5)
        thread2.join(timeout=5)

        # Count successful creations
        success_count = sum(1 for r in results.values() if r and r.get('success'))

        # In SQLite, concurrent transactions may both fail with OperationalError
        # The important thing is that at most one frog exists in the database
        frogs = Intention.objects.filter(creator=self.user, date=self.today, froggy=True)
        self.assertLessEqual(frogs.count(), 1, "At most one frog should exist in database")

        # If any thread succeeded, exactly one should have succeeded
        if success_count > 0:
            self.assertEqual(success_count, 1, "If any thread succeeded, only one should have")
            self.assertEqual(frogs.count(), 1, "Database should have exactly one frog if creation succeeded")

    def test_flags_set_correctly(self):
        tool_input = {
            'title': 'Complex task',
            'froggy': True,
            'sticky': True,
            'anxiety_inducing': True
        }

        result = create_intention_executor(tool_input, user=self.user)

        self.assertTrue(result['froggy'])
        self.assertTrue(result['sticky'])
        self.assertTrue(result['anxiety_inducing'])


class ToolExecutorTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_unknown_tool(self):
        executor = ToolExecutor(user=self.user)
        result = executor.execute('nonexistent_tool', {})

        self.assertFalse(result['success'])
        self.assertIn('Unknown tool', result['error'])

    def test_tool_requires_user(self):
        executor = ToolExecutor(user=None)
        result = executor.execute('create_intention', {'title': 'Test'})

        self.assertFalse(result['success'])
        self.assertIn('User authentication required', result['error'])

    def test_execution_log(self):
        executor = ToolExecutor(user=self.user)
        executor.execute('create_intention', {'title': 'Test 1'})
        executor.execute('create_intention', {'title': 'Test 2'})

        self.assertEqual(len(executor.execution_log), 2)
        self.assertEqual(executor.execution_log[0]['tool_name'], 'create_intention')
        self.assertTrue(executor.execution_log[0]['success'])

    def test_execution_error_logged(self):
        executor = ToolExecutor(user=self.user)
        result = executor.execute('create_intention', {'title': ''})

        self.assertFalse(result['success'])
        self.assertEqual(len(executor.execution_log), 1)
        self.assertFalse(executor.execution_log[0]['success'])
        self.assertIsNotNone(executor.execution_log[0]['error'])
