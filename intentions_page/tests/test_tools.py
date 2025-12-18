from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import date, timedelta
from intentions_page.models import Intention, get_working_day_date
from intentions_page.tools import (
    ToolExecutor,
    create_intention_executor,
    reorder_intentions_executor,
    update_intention_status_executor,
    list_intentions_executor,
    get_intention_details_executor
)

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


class UpdateIntentionStatusExecutorTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.today = get_working_day_date()

        # Create test intention
        self.intention = Intention.objects.create(
            title='Test task',
            date=self.today,
            creator=self.user,
            completed=False,
            neverminded=False,
            sticky=False,
            froggy=False,
            anxiety_inducing=False
        )

    def test_mark_intention_completed(self):
        tool_input = {
            'intention_id': self.intention.id,
            'status_field': 'completed',
            'value': True
        }

        result = update_intention_status_executor(tool_input, user=self.user)

        self.assertEqual(result['intention_id'], self.intention.id)
        self.assertEqual(result['status_field'], 'completed')
        self.assertTrue(result['value'])
        self.assertIn('marked as completed', result['message'])

        self.intention.refresh_from_db()
        self.assertTrue(self.intention.completed)

    def test_unmark_intention_completed(self):
        self.intention.completed = True
        self.intention.save()

        tool_input = {
            'intention_id': self.intention.id,
            'status_field': 'completed',
            'value': False
        }

        result = update_intention_status_executor(tool_input, user=self.user)

        self.assertFalse(result['value'])
        self.assertIn('unmarked as completed', result['message'])

        self.intention.refresh_from_db()
        self.assertFalse(self.intention.completed)

    def test_mark_intention_neverminded(self):
        tool_input = {
            'intention_id': self.intention.id,
            'status_field': 'neverminded',
            'value': True
        }

        result = update_intention_status_executor(tool_input, user=self.user)

        self.assertTrue(result['value'])
        self.assertIn('marked as neverminded', result['message'])

        self.intention.refresh_from_db()
        self.assertTrue(self.intention.neverminded)

    def test_mark_intention_sticky(self):
        tool_input = {
            'intention_id': self.intention.id,
            'status_field': 'sticky',
            'value': True
        }

        result = update_intention_status_executor(tool_input, user=self.user)

        self.assertTrue(result['value'])
        self.assertIn('marked as sticky', result['message'])

        self.intention.refresh_from_db()
        self.assertTrue(self.intention.sticky)

    def test_mark_intention_froggy(self):
        tool_input = {
            'intention_id': self.intention.id,
            'status_field': 'froggy',
            'value': True
        }

        result = update_intention_status_executor(tool_input, user=self.user)

        self.assertTrue(result['value'])
        self.assertIn('marked as frog', result['message'])

        self.intention.refresh_from_db()
        self.assertTrue(self.intention.froggy)

    def test_mark_intention_anxiety_inducing(self):
        tool_input = {
            'intention_id': self.intention.id,
            'status_field': 'anxiety_inducing',
            'value': True
        }

        result = update_intention_status_executor(tool_input, user=self.user)

        self.assertTrue(result['value'])
        self.assertIn('marked as anxiety-inducing', result['message'])

        self.intention.refresh_from_db()
        self.assertTrue(self.intention.anxiety_inducing)

    def test_missing_intention_id(self):
        tool_input = {
            'status_field': 'completed',
            'value': True
        }

        with self.assertRaisesMessage(ValueError, 'intention_id is required'):
            update_intention_status_executor(tool_input, user=self.user)

    def test_invalid_intention_id_type(self):
        tool_input = {
            'intention_id': 'not an integer',
            'status_field': 'completed',
            'value': True
        }

        with self.assertRaisesMessage(ValueError, 'intention_id must be an integer'):
            update_intention_status_executor(tool_input, user=self.user)

    def test_missing_status_field(self):
        tool_input = {
            'intention_id': self.intention.id,
            'value': True
        }

        with self.assertRaisesMessage(ValueError, 'status_field is required'):
            update_intention_status_executor(tool_input, user=self.user)

    def test_invalid_status_field(self):
        tool_input = {
            'intention_id': self.intention.id,
            'status_field': 'invalid_field',
            'value': True
        }

        with self.assertRaisesMessage(ValueError, 'Invalid status_field'):
            update_intention_status_executor(tool_input, user=self.user)

    def test_missing_value(self):
        tool_input = {
            'intention_id': self.intention.id,
            'status_field': 'completed'
        }

        with self.assertRaisesMessage(ValueError, 'value is required'):
            update_intention_status_executor(tool_input, user=self.user)

    def test_invalid_value_type(self):
        tool_input = {
            'intention_id': self.intention.id,
            'status_field': 'completed',
            'value': 'yes'
        }

        with self.assertRaisesMessage(ValueError, 'value must be a boolean'):
            update_intention_status_executor(tool_input, user=self.user)

    def test_nonexistent_intention(self):
        tool_input = {
            'intention_id': 99999,
            'status_field': 'completed',
            'value': True
        }

        with self.assertRaisesMessage(ValueError, 'not found or doesn\'t belong to you'):
            update_intention_status_executor(tool_input, user=self.user)

    def test_other_user_intention(self):
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )

        other_intention = Intention.objects.create(
            title='Other user task',
            date=self.today,
            creator=other_user
        )

        tool_input = {
            'intention_id': other_intention.id,
            'status_field': 'completed',
            'value': True
        }

        with self.assertRaisesMessage(ValueError, 'not found or doesn\'t belong to you'):
            update_intention_status_executor(tool_input, user=self.user)

    def test_froggy_validation_only_one_per_day(self):
        # Create existing frog
        existing_frog = Intention.objects.create(
            title='Existing frog',
            date=self.today,
            creator=self.user,
            froggy=True
        )

        tool_input = {
            'intention_id': self.intention.id,
            'status_field': 'froggy',
            'value': True
        }

        with self.assertRaisesMessage(ValueError, 'A frog already exists'):
            update_intention_status_executor(tool_input, user=self.user)

    def test_unmark_existing_frog(self):
        self.intention.froggy = True
        self.intention.save()

        tool_input = {
            'intention_id': self.intention.id,
            'status_field': 'froggy',
            'value': False
        }

        result = update_intention_status_executor(tool_input, user=self.user)

        self.assertFalse(result['value'])
        self.intention.refresh_from_db()
        self.assertFalse(self.intention.froggy)

    def test_concurrent_frog_update_prevented(self):
        from django.db import connection
        from threading import Thread
        from django.db.utils import OperationalError
        import time

        # Create a second intention to try to make a frog concurrently
        intention2 = Intention.objects.create(
            title='Second task',
            date=self.today,
            creator=self.user,
            froggy=False
        )

        results = {'thread1': None, 'thread2': None}

        def set_frog(thread_name, intention_id):
            try:
                time.sleep(0.01)  # Small delay to increase chance of collision
                result = update_intention_status_executor(
                    {
                        'intention_id': intention_id,
                        'status_field': 'froggy',
                        'value': True
                    },
                    user=self.user
                )
                results[thread_name] = {'success': True, 'result': result}
            except ValueError as e:
                results[thread_name] = {'success': False, 'error': str(e), 'error_type': 'ValueError'}
            except OperationalError as e:
                # SQLite database locking is expected in concurrent scenarios
                results[thread_name] = {'success': False, 'error': str(e), 'error_type': 'OperationalError'}

        connection.close()

        thread1 = Thread(target=set_frog, args=('thread1', self.intention.id))
        thread2 = Thread(target=set_frog, args=('thread2', intention2.id))

        thread1.start()
        thread2.start()

        thread1.join(timeout=5)
        thread2.join(timeout=5)

        # Count successful updates
        success_count = sum(1 for r in results.values() if r and r.get('success'))

        # In SQLite, concurrent transactions may both fail with OperationalError
        # The important thing is that at most one frog exists in the database
        frogs = Intention.objects.filter(creator=self.user, date=self.today, froggy=True)
        self.assertLessEqual(frogs.count(), 1, "At most one frog should exist in database")

        # If any thread succeeded, exactly one should have succeeded
        if success_count > 0:
            self.assertEqual(success_count, 1, "If any thread succeeded, only one should have")
            self.assertEqual(frogs.count(), 1, "Database should have exactly one frog if update succeeded")

    def test_tool_executor_integration(self):
        executor = ToolExecutor(user=self.user)

        result = executor.execute('update_intention_status', {
            'intention_id': self.intention.id,
            'status_field': 'completed',
            'value': True
        })

        self.assertTrue(result['success'])
        self.assertEqual(len(executor.execution_log), 1)
        self.assertEqual(executor.execution_log[0]['tool_name'], 'update_intention_status')


class ReorderIntentionsExecutorTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.today = get_working_day_date()

        # Create test intentions
        self.intention1 = Intention.objects.create(
            title='First task',
            date=self.today,
            creator=self.user,
            order=0
        )
        self.intention2 = Intention.objects.create(
            title='Second task',
            date=self.today,
            creator=self.user,
            order=1
        )
        self.intention3 = Intention.objects.create(
            title='Third task',
            date=self.today,
            creator=self.user,
            order=2
        )

    def test_successful_reorder(self):
        # Reorder to: 3, 1, 2 (reverse except swap first two)
        tool_input = {
            'intention_ids': [self.intention3.id, self.intention1.id, self.intention2.id]
        }

        result = reorder_intentions_executor(tool_input, user=self.user)

        self.assertEqual(result['count'], 3)
        self.assertEqual(result['date'], self.today.isoformat())
        self.assertIn('Successfully reordered', result['message'])

        # Verify database order
        self.intention1.refresh_from_db()
        self.intention2.refresh_from_db()
        self.intention3.refresh_from_db()

        self.assertEqual(self.intention3.order, 0)  # Now first
        self.assertEqual(self.intention1.order, 1)  # Now second
        self.assertEqual(self.intention2.order, 2)  # Now third

    def test_empty_intention_ids(self):
        tool_input = {'intention_ids': []}

        with self.assertRaisesMessage(ValueError, 'intention_ids list is required and cannot be empty'):
            reorder_intentions_executor(tool_input, user=self.user)

    def test_invalid_intention_ids_type(self):
        tool_input = {'intention_ids': 'not a list'}

        with self.assertRaisesMessage(ValueError, 'intention_ids must be a list'):
            reorder_intentions_executor(tool_input, user=self.user)

    def test_duplicate_intention_ids(self):
        tool_input = {
            'intention_ids': [self.intention1.id, self.intention2.id, self.intention1.id]
        }

        with self.assertRaisesMessage(ValueError, 'intention_ids contains duplicate IDs'):
            reorder_intentions_executor(tool_input, user=self.user)

    def test_nonexistent_intention(self):
        tool_input = {
            'intention_ids': [self.intention1.id, 99999, self.intention3.id]
        }

        with self.assertRaisesMessage(ValueError, 'Some intentions not found'):
            reorder_intentions_executor(tool_input, user=self.user)

    def test_other_user_intention(self):
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )

        other_intention = Intention.objects.create(
            title='Other user task',
            date=self.today,
            creator=other_user
        )

        tool_input = {
            'intention_ids': [self.intention1.id, other_intention.id]
        }

        with self.assertRaisesMessage(ValueError, 'Some intentions not found'):
            reorder_intentions_executor(tool_input, user=self.user)

    def test_specific_date(self):
        tomorrow = self.today + timedelta(days=1)
        future_intention = Intention.objects.create(
            title='Future task',
            date=tomorrow,
            creator=self.user,
            order=0
        )

        tool_input = {
            'intention_ids': [future_intention.id],
            'date': tomorrow.isoformat()
        }

        result = reorder_intentions_executor(tool_input, user=self.user)

        self.assertEqual(result['date'], tomorrow.isoformat())

    def test_invalid_date_format(self):
        tool_input = {
            'intention_ids': [self.intention1.id],
            'date': 'not-a-date'
        }

        with self.assertRaisesMessage(ValueError, 'Invalid date format'):
            reorder_intentions_executor(tool_input, user=self.user)

    def test_wrong_date_intentions(self):
        tomorrow = self.today + timedelta(days=1)

        tool_input = {
            'intention_ids': [self.intention1.id],  # Today's intention
            'date': tomorrow.isoformat()  # But asking for tomorrow
        }

        with self.assertRaisesMessage(ValueError, 'Some intentions not found'):
            reorder_intentions_executor(tool_input, user=self.user)

    def test_tool_executor_integration(self):
        executor = ToolExecutor(user=self.user)

        result = executor.execute('reorder_intentions', {
            'intention_ids': [self.intention2.id, self.intention3.id, self.intention1.id]
        })

        self.assertTrue(result['success'])
        self.assertEqual(len(executor.execution_log), 1)
        self.assertEqual(executor.execution_log[0]['tool_name'], 'reorder_intentions')


class ListIntentionsExecutorTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.today = get_working_day_date()

        # Create test intentions with different statuses
        self.intention1 = Intention.objects.create(
            title='Active task',
            date=self.today,
            creator=self.user,
            completed=False,
            neverminded=False
        )
        self.intention2 = Intention.objects.create(
            title='Completed task',
            date=self.today,
            creator=self.user,
            completed=True
        )
        self.intention3 = Intention.objects.create(
            title='Neverminded task',
            date=self.today,
            creator=self.user,
            neverminded=True
        )
        self.intention4 = Intention.objects.create(
            title='Frog task',
            date=self.today,
            creator=self.user,
            froggy=True,
            sticky=True
        )

    def test_list_all_intentions_default_date(self):
        tool_input = {}
        result = list_intentions_executor(tool_input, user=self.user)

        self.assertEqual(result['date'], self.today.isoformat())
        self.assertEqual(result['status_filter'], 'all')
        self.assertEqual(result['count'], 4)
        self.assertEqual(len(result['intentions']), 4)

        # Check structure of returned intentions
        first_intention = result['intentions'][0]
        self.assertIn('id', first_intention)
        self.assertIn('title', first_intention)
        self.assertIn('date', first_intention)
        self.assertIn('completed', first_intention)
        self.assertIn('status', first_intention)

    def test_list_active_intentions(self):
        tool_input = {'status_filter': 'active'}
        result = list_intentions_executor(tool_input, user=self.user)

        self.assertEqual(result['status_filter'], 'active')
        self.assertEqual(result['count'], 2)  # intention1 and intention4

        titles = [i['title'] for i in result['intentions']]
        self.assertIn('Active task', titles)
        self.assertIn('Frog task', titles)
        self.assertNotIn('Completed task', titles)
        self.assertNotIn('Neverminded task', titles)

    def test_list_completed_intentions(self):
        tool_input = {'status_filter': 'completed'}
        result = list_intentions_executor(tool_input, user=self.user)

        self.assertEqual(result['status_filter'], 'completed')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['intentions'][0]['title'], 'Completed task')

    def test_list_neverminded_intentions(self):
        tool_input = {'status_filter': 'neverminded'}
        result = list_intentions_executor(tool_input, user=self.user)

        self.assertEqual(result['status_filter'], 'neverminded')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['intentions'][0]['title'], 'Neverminded task')

    def test_list_specific_date(self):
        tomorrow = self.today + timedelta(days=1)

        # Create intention for tomorrow
        Intention.objects.create(
            title='Tomorrow task',
            date=tomorrow,
            creator=self.user
        )

        tool_input = {'date': tomorrow.isoformat()}
        result = list_intentions_executor(tool_input, user=self.user)

        self.assertEqual(result['date'], tomorrow.isoformat())
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['intentions'][0]['title'], 'Tomorrow task')

    def test_list_empty_date(self):
        tomorrow = self.today + timedelta(days=1)
        tool_input = {'date': tomorrow.isoformat()}
        result = list_intentions_executor(tool_input, user=self.user)

        self.assertEqual(result['count'], 0)
        self.assertEqual(len(result['intentions']), 0)

    def test_invalid_status_filter(self):
        tool_input = {'status_filter': 'invalid'}

        with self.assertRaisesMessage(ValueError, 'Invalid status_filter'):
            list_intentions_executor(tool_input, user=self.user)

    def test_invalid_date_format(self):
        tool_input = {'date': 'not-a-date'}

        with self.assertRaisesMessage(ValueError, 'Invalid date format'):
            list_intentions_executor(tool_input, user=self.user)

    def test_user_isolation(self):
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )

        # Create intention for other user
        Intention.objects.create(
            title='Other user task',
            date=self.today,
            creator=other_user
        )

        tool_input = {}
        result = list_intentions_executor(tool_input, user=self.user)

        # Should only see own intentions
        self.assertEqual(result['count'], 4)
        titles = [i['title'] for i in result['intentions']]
        self.assertNotIn('Other user task', titles)

    def test_tool_executor_integration(self):
        executor = ToolExecutor(user=self.user)

        result = executor.execute('list_intentions', {
            'status_filter': 'active'
        })

        self.assertTrue(result['success'])
        self.assertEqual(len(executor.execution_log), 1)
        self.assertEqual(executor.execution_log[0]['tool_name'], 'list_intentions')


class GetIntentionDetailsExecutorTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.today = get_working_day_date()

        self.intention = Intention.objects.create(
            title='Test task',
            date=self.today,
            creator=self.user,
            completed=False,
            sticky=True,
            froggy=True,
            anxiety_inducing=True
        )

    def test_get_intention_details_success(self):
        tool_input = {'intention_id': self.intention.id}
        result = get_intention_details_executor(tool_input, user=self.user)

        self.assertEqual(result['id'], self.intention.id)
        self.assertEqual(result['title'], 'Test task')
        self.assertEqual(result['date'], self.today.isoformat())
        self.assertTrue(result['sticky'])
        self.assertTrue(result['froggy'])
        self.assertTrue(result['anxiety_inducing'])
        self.assertFalse(result['completed'])
        self.assertEqual(result['status'], 'active')
        self.assertIn('created_datetime', result)
        self.assertIn('order', result)

    def test_missing_intention_id(self):
        tool_input = {}

        with self.assertRaisesMessage(ValueError, 'intention_id is required'):
            get_intention_details_executor(tool_input, user=self.user)

    def test_invalid_intention_id_type(self):
        tool_input = {'intention_id': 'not-an-int'}

        with self.assertRaisesMessage(ValueError, 'intention_id must be an integer'):
            get_intention_details_executor(tool_input, user=self.user)

    def test_nonexistent_intention(self):
        tool_input = {'intention_id': 99999}

        with self.assertRaisesMessage(ValueError, 'not found or doesn\'t belong to you'):
            get_intention_details_executor(tool_input, user=self.user)

    def test_other_user_intention(self):
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )

        other_intention = Intention.objects.create(
            title='Other user task',
            date=self.today,
            creator=other_user
        )

        tool_input = {'intention_id': other_intention.id}

        with self.assertRaisesMessage(ValueError, 'not found or doesn\'t belong to you'):
            get_intention_details_executor(tool_input, user=self.user)

    def test_completed_intention_status(self):
        self.intention.completed = True
        self.intention.save()

        tool_input = {'intention_id': self.intention.id}
        result = get_intention_details_executor(tool_input, user=self.user)

        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['completed'])

    def test_neverminded_intention_status(self):
        self.intention.neverminded = True
        self.intention.save()

        tool_input = {'intention_id': self.intention.id}
        result = get_intention_details_executor(tool_input, user=self.user)

        self.assertEqual(result['status'], 'neverminded')
        self.assertTrue(result['neverminded'])

    def test_tool_executor_integration(self):
        executor = ToolExecutor(user=self.user)

        result = executor.execute('get_intention_details', {
            'intention_id': self.intention.id
        })

        self.assertTrue(result['success'])
        self.assertEqual(result['result']['title'], 'Test task')
        self.assertEqual(len(executor.execution_log), 1)
        self.assertEqual(executor.execution_log[0]['tool_name'], 'get_intention_details')
