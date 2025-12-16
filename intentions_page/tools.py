import logging

logger = logging.getLogger(__name__)

def create_intention_executor(tool_input, user=None):
    """
    Execute the create_intention tool.

    Args:
        tool_input: Dict with keys: title, date (optional), froggy, sticky, anxiety_inducing
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import Intention, get_working_day_date
    from django.utils.dateparse import parse_date

    title = tool_input.get('title', '').strip()
    if not title:
        raise ValueError("Title is required and cannot be empty")
    if len(title) > 500:
        raise ValueError("Title cannot exceed 500 characters")

    date_str = tool_input.get('date')
    if date_str:
        intention_date = parse_date(date_str)
        if not intention_date:
            raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")
    else:
        intention_date = get_working_day_date()

    froggy = tool_input.get('froggy', False)
    sticky = tool_input.get('sticky', False)
    anxiety_inducing = tool_input.get('anxiety_inducing', False)

    if froggy:
        from django.db import transaction

        with transaction.atomic():
            existing_frog = Intention.objects.select_for_update().filter(
                creator=user,
                date=intention_date,
                froggy=True
            ).first()

            if existing_frog:
                raise ValueError(
                    f"A frog already exists for {intention_date}: '{existing_frog.title}'. "
                    f"Only one frog per day allowed."
                )

            intention = Intention.objects.create(
                title=title,
                date=intention_date,
                creator=user,
                froggy=froggy,
                sticky=sticky,
                anxiety_inducing=anxiety_inducing,
                completed=False,
                neverminded=False
            )
    else:
        intention = Intention.objects.create(
            title=title,
            date=intention_date,
            creator=user,
            froggy=froggy,
            sticky=sticky,
            anxiety_inducing=anxiety_inducing,
            completed=False,
            neverminded=False
        )

    logger.info(f"Created intention #{intention.id} for user {user.id}: {title}")

    return {
        'intention_id': intention.id,
        'title': intention.title,
        'date': intention.date.isoformat(),
        'froggy': intention.froggy,
        'sticky': intention.sticky,
        'anxiety_inducing': intention.anxiety_inducing,
        'message': f"Successfully created intention: {title}"
    }


def reorder_intentions_executor(tool_input, user=None):
    """
    Execute the reorder_intentions tool.

    Args:
        tool_input: Dict with keys: intention_ids (list of int), date (optional)
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import Intention, get_working_day_date
    from django.utils.dateparse import parse_date
    from django.db import transaction

    intention_ids = tool_input.get('intention_ids', [])
    if not intention_ids:
        raise ValueError("intention_ids list is required and cannot be empty")

    if not isinstance(intention_ids, list):
        raise ValueError("intention_ids must be a list of intention IDs")

    # Check for duplicate IDs
    if len(intention_ids) != len(set(intention_ids)):
        raise ValueError("intention_ids contains duplicate IDs")

    date_str = tool_input.get('date')
    if date_str:
        target_date = parse_date(date_str)
        if not target_date:
            raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")
    else:
        target_date = get_working_day_date()

    # Verify all intentions exist and belong to the user
    intentions = Intention.objects.filter(
        id__in=intention_ids,
        creator=user,
        date=target_date
    )

    if intentions.count() != len(intention_ids):
        raise ValueError(
            f"Some intentions not found or don't belong to you for {target_date}. "
            f"Found {intentions.count()} out of {len(intention_ids)} intentions."
        )

    # Update order for each intention atomically
    with transaction.atomic():
        for order_index, intention_id in enumerate(intention_ids):
            Intention.objects.filter(id=intention_id).update(order=order_index)

    logger.info(f"Reordered {len(intention_ids)} intentions for user {user.id} on {target_date}")

    # Return updated intentions in new order
    reordered_intentions = Intention.objects.filter(id__in=intention_ids).order_by('order')

    return {
        'count': len(intention_ids),
        'date': target_date.isoformat(),
        'intentions': [
            {
                'id': intention.id,
                'title': intention.title,
                'order': intention.order
            }
            for intention in reordered_intentions
        ],
        'message': f"Successfully reordered {len(intention_ids)} intentions for {target_date}"
    }


TOOL_REGISTRY = {
    'create_intention': {
        'schema': {
            'name': 'create_intention',
            'description': 'Create a new intention for a specific date. Use when user asks to add, create, or track a new task.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'title': {
                        'type': 'string',
                        'description': 'Title of the intention'
                    },
                    'date': {
                        'type': 'string',
                        'description': 'Date in YYYY-MM-DD format. ONLY provide this if the user explicitly requests a specific date. Otherwise, omit this parameter to use today\'s date.'
                    },
                    'froggy': {
                        'type': 'boolean',
                        'description': 'Most important task (frog) for the day. Only one frog per day allowed.',
                        'default': False
                    },
                    'sticky': {
                        'type': 'boolean',
                        'description': 'Should carry forward to future days if incomplete',
                        'default': False
                    },
                    'anxiety_inducing': {
                        'type': 'boolean',
                        'description': 'Whether task causes anxiety/stress',
                        'default': False
                    }
                },
                'required': ['title']
            }
        },
        'executor': create_intention_executor,
        'requires_user': True
    },
    'reorder_intentions': {
        'schema': {
            'name': 'reorder_intentions',
            'description': 'Reorder intentions for a specific date by priority. Use when user asks to prioritize, sort, or reorder their tasks. Provide the intention IDs in the desired order (first ID will be shown first).',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'intention_ids': {
                        'type': 'array',
                        'items': {
                            'type': 'integer'
                        },
                        'description': 'List of intention IDs in the desired order (first ID = highest priority/first in list)'
                    },
                    'date': {
                        'type': 'string',
                        'description': 'Date in YYYY-MM-DD format. ONLY provide this if the user explicitly requests a specific date. Otherwise, omit this parameter to use today\'s date.'
                    }
                },
                'required': ['intention_ids']
            }
        },
        'executor': reorder_intentions_executor,
        'requires_user': True
    }
}


def get_available_tools():
    """Return list of tool schemas for Claude API."""
    return [tool_def['schema'] for tool_def in TOOL_REGISTRY.values()]


class ToolExecutor:
    """Executes tools and manages validation."""

    def __init__(self, user=None):
        self.user = user
        self.execution_log = []

    def execute(self, tool_name, tool_input):
        """
        Execute a tool by name with given input.

        Args:
            tool_name: Name of tool to execute
            tool_input: Dict of input parameters

        Returns:
            dict with structure:
            {
                'success': bool,
                'result': dict or None,
                'error': str or None
            }
        """
        if tool_name not in TOOL_REGISTRY:
            return {
                'success': False,
                'result': None,
                'error': f"Unknown tool: {tool_name}"
            }

        tool_def = TOOL_REGISTRY[tool_name]

        if tool_def.get('requires_user') and not self.user:
            return {
                'success': False,
                'result': None,
                'error': "User authentication required for this tool"
            }

        try:
            executor_func = tool_def['executor']
            result = executor_func(tool_input, user=self.user)

            self.execution_log.append({
                'tool_name': tool_name,
                'input': tool_input,
                'result': result,
                'success': True,
                'error': None
            })

            return {
                'success': True,
                'result': result,
                'error': None
            }

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}, error: {e}", exc_info=True)

            self.execution_log.append({
                'tool_name': tool_name,
                'input': tool_input,
                'result': None,
                'success': False,
                'error': str(e)
            })

            return {
                'success': False,
                'result': None,
                'error': str(e)
            }
