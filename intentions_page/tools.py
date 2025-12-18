import logging

logger = logging.getLogger(__name__)

# Human-readable status names for messaging
STATUS_NAMES = {
    'completed': 'completed',
    'neverminded': 'neverminded',
    'sticky': 'sticky',
    'froggy': 'frog (most important)',
    'anxiety_inducing': 'anxiety-inducing'
}

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


def update_intention_status_executor(tool_input, user=None):
    """
    Execute the update_intention_status tool.

    Args:
        tool_input: Dict with keys: intention_id (int), status_field (str), value (bool)
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import Intention

    intention_id = tool_input.get('intention_id')
    if not intention_id:
        raise ValueError("intention_id is required")

    if not isinstance(intention_id, int):
        raise ValueError("intention_id must be an integer")

    status_field = tool_input.get('status_field')
    valid_status_fields = ['completed', 'neverminded', 'sticky', 'froggy', 'anxiety_inducing']

    if not status_field:
        raise ValueError("status_field is required")

    if status_field not in valid_status_fields:
        raise ValueError(
            f"Invalid status_field '{status_field}'. "
            f"Must be one of: {', '.join(valid_status_fields)}"
        )

    value = tool_input.get('value')
    if value is None:
        raise ValueError("value is required")

    if not isinstance(value, bool):
        raise ValueError("value must be a boolean (true or false)")

    # Get the intention and verify ownership
    try:
        intention = Intention.objects.get(id=intention_id, creator=user)
    except Intention.DoesNotExist:
        raise ValueError(
            f"Intention with ID {intention_id} not found or doesn't belong to you"
        )

    # Special validation for froggy - wrap ALL froggy updates in transaction
    if status_field == 'froggy':
        from django.db import transaction

        with transaction.atomic():
            if value is True:
                # Check for existing frog only when setting froggy=True
                existing_frog = Intention.objects.select_for_update().filter(
                    creator=user,
                    date=intention.date,
                    froggy=True
                ).exclude(id=intention_id).first()

                if existing_frog:
                    raise ValueError(
                        f"A frog already exists for {intention.date}: '{existing_frog.title}'. "
                        f"Only one frog per day allowed. Remove the existing frog first."
                    )

            # Update within transaction for both True and False
            setattr(intention, status_field, value)
            intention.save()
    else:
        # Non-froggy updates don't need transaction
        setattr(intention, status_field, value)
        intention.save()

    # Get the human-readable status name
    status_name = STATUS_NAMES[status_field]
    action = "marked as" if value else "unmarked as"

    logger.info(
        f"Updated intention #{intention.id} for user {user.id}: "
        f"{status_field}={value}"
    )

    return {
        'intention_id': intention.id,
        'title': intention.title,
        'status_field': status_field,
        'value': value,
        'date': intention.date.isoformat(),
        'message': f"Successfully {action} {status_name}: {intention.title}"
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


def list_intentions_executor(tool_input, user=None):
    """
    Execute the list_intentions tool.

    Args:
        tool_input: Dict with keys: date (optional), status_filter (optional)
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import Intention, get_working_day_date
    from django.utils.dateparse import parse_date

    date_str = tool_input.get('date')
    if date_str:
        target_date = parse_date(date_str)
        if not target_date:
            raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")
    else:
        target_date = get_working_day_date()

    status_filter = tool_input.get('status_filter')
    valid_status_filters = ['active', 'completed', 'neverminded', 'all']

    if status_filter and status_filter not in valid_status_filters:
        raise ValueError(
            f"Invalid status_filter '{status_filter}'. "
            f"Must be one of: {', '.join(valid_status_filters)}"
        )

    # Query intentions for the user and date
    intentions = Intention.objects.filter(
        creator=user,
        date=target_date
    ).order_by('order', 'created_datetime')

    # Apply status filter
    if status_filter == 'active':
        intentions = intentions.filter(completed=False, neverminded=False)
    elif status_filter == 'completed':
        intentions = intentions.filter(completed=True)
    elif status_filter == 'neverminded':
        intentions = intentions.filter(neverminded=True)
    # 'all' or None = no filtering

    # Build result list
    intention_list = []
    for intention in intentions:
        intention_list.append({
            'id': intention.id,
            'title': intention.title,
            'date': intention.date.isoformat(),
            'order': intention.order,
            'completed': intention.completed,
            'neverminded': intention.neverminded,
            'sticky': intention.sticky,
            'froggy': intention.froggy,
            'anxiety_inducing': intention.anxiety_inducing,
            'status': intention.get_status()
        })

    logger.info(
        f"Listed {len(intention_list)} intentions for user {user.id} on {target_date} "
        f"with filter: {status_filter or 'all'}"
    )

    return {
        'date': target_date.isoformat(),
        'status_filter': status_filter or 'all',
        'count': len(intention_list),
        'intentions': intention_list,
        'message': f"Found {len(intention_list)} intention(s) for {target_date}"
    }


def get_intention_details_executor(tool_input, user=None):
    """
    Execute the get_intention_details tool.

    Args:
        tool_input: Dict with keys: intention_id (int)
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import Intention

    intention_id = tool_input.get('intention_id')
    if not intention_id:
        raise ValueError("intention_id is required")

    if not isinstance(intention_id, int):
        raise ValueError("intention_id must be an integer")

    # Get the intention and verify ownership
    try:
        intention = Intention.objects.get(id=intention_id, creator=user)
    except Intention.DoesNotExist:
        raise ValueError(
            f"Intention with ID {intention_id} not found or doesn't belong to you"
        )

    logger.info(f"Retrieved intention #{intention.id} for user {user.id}")

    return {
        'id': intention.id,
        'title': intention.title,
        'date': intention.date.isoformat(),
        'created_datetime': intention.created_datetime.isoformat(),
        'order': intention.order,
        'completed': intention.completed,
        'neverminded': intention.neverminded,
        'sticky': intention.sticky,
        'froggy': intention.froggy,
        'anxiety_inducing': intention.anxiety_inducing,
        'status': intention.get_status(),
        'message': f"Retrieved details for intention: {intention.title}"
    }


def update_intention_executor(tool_input, user=None):
    """
    Execute the update_intention tool.

    Args:
        tool_input: Dict with keys: intention_id (int), title (optional), date (optional)
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import Intention
    from django.utils.dateparse import parse_date

    intention_id = tool_input.get('intention_id')
    if not intention_id:
        raise ValueError("intention_id is required")

    if not isinstance(intention_id, int):
        raise ValueError("intention_id must be an integer")

    # Get the intention and verify ownership
    try:
        intention = Intention.objects.get(id=intention_id, creator=user)
    except Intention.DoesNotExist:
        raise ValueError(
            f"Intention with ID {intention_id} not found or doesn't belong to you"
        )

    # Track what changed
    changes = []

    # Update title if provided
    new_title = tool_input.get('title')
    if new_title is not None:
        new_title = new_title.strip()
        if not new_title:
            raise ValueError("Title cannot be empty")
        if len(new_title) > 500:
            raise ValueError("Title cannot exceed 500 characters")

        if new_title != intention.title:
            old_title = intention.title
            intention.title = new_title
            changes.append(f"title: '{old_title}' → '{new_title}'")

    # Update date if provided
    new_date_str = tool_input.get('date')
    if new_date_str is not None:
        new_date = parse_date(new_date_str)
        if not new_date:
            raise ValueError(f"Invalid date format: {new_date_str}. Use YYYY-MM-DD.")

        if new_date != intention.date:
            # Check if moving a frog to a date that already has one
            if intention.froggy:
                existing_frog = Intention.objects.filter(
                    creator=user,
                    date=new_date,
                    froggy=True
                ).exclude(id=intention.id).first()

                if existing_frog:
                    raise ValueError(
                        f"A frog already exists for {new_date}: '{existing_frog.title}'. "
                        f"Cannot move this frog there. Remove the existing frog first."
                    )

            old_date = intention.date
            intention.date = new_date
            changes.append(f"date: {old_date.isoformat()} → {new_date.isoformat()}")

    # Check if any changes were made
    if not changes:
        return {
            'intention_id': intention.id,
            'title': intention.title,
            'date': intention.date.isoformat(),
            'changes': [],
            'message': "No changes made - intention already has the specified values"
        }

    # Save the changes
    intention.save()

    logger.info(
        f"Updated intention #{intention.id} for user {user.id}: {', '.join(changes)}"
    )

    return {
        'intention_id': intention.id,
        'title': intention.title,
        'date': intention.date.isoformat(),
        'changes': changes,
        'message': f"Successfully updated intention: {', '.join(changes)}"
    }


def delete_intention_executor(tool_input, user=None):
    """
    Execute the delete_intention tool.

    Args:
        tool_input: Dict with keys: intention_id (int)
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import Intention

    intention_id = tool_input.get('intention_id')
    if not intention_id:
        raise ValueError("intention_id is required")

    if not isinstance(intention_id, int):
        raise ValueError("intention_id must be an integer")

    # Get the intention and verify ownership
    try:
        intention = Intention.objects.get(id=intention_id, creator=user)
    except Intention.DoesNotExist:
        raise ValueError(
            f"Intention with ID {intention_id} not found or doesn't belong to you"
        )

    # Store intention details before deletion for logging and response
    intention_title = intention.title
    intention_date = intention.date.isoformat()
    intention_id_str = intention.id

    # Delete the intention
    intention.delete()

    logger.info(f"Deleted intention #{intention_id_str} for user {user.id}: {intention_title}")

    return {
        'intention_id': intention_id_str,
        'title': intention_title,
        'date': intention_date,
        'message': f"Successfully deleted intention: {intention_title}"
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
    'update_intention_status': {
        'schema': {
            'name': 'update_intention_status',
            'description': 'Update the status of an intention. Use when user indicates they completed/neverminded a task, or wants to change sticky/froggy/anxiety-inducing flags. Examples: "I finished X", "Mark Y as my frog", "Make Z sticky", "I\'m not doing X anymore".',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'intention_id': {
                        'type': 'integer',
                        'description': 'ID of the intention to update (shown in parentheses like "ID: 123")'
                    },
                    'status_field': {
                        'type': 'string',
                        'description': 'Which status to update',
                        'enum': ['completed', 'neverminded', 'sticky', 'froggy', 'anxiety_inducing']
                    },
                    'value': {
                        'type': 'boolean',
                        'description': 'New value for the status (true to set, false to unset)'
                    }
                },
                'required': ['intention_id', 'status_field', 'value']
            }
        },
        'executor': update_intention_status_executor,
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
    },
    'list_intentions': {
        'schema': {
            'name': 'list_intentions',
            'description': 'List all intentions for a specific date with optional status filtering. Use when user asks to see their tasks, view intentions, or check what they have planned. Returns full details for each intention.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'date': {
                        'type': 'string',
                        'description': 'Date in YYYY-MM-DD format. ONLY provide this if the user explicitly requests a specific date. Otherwise, omit this parameter to use today\'s date.'
                    },
                    'status_filter': {
                        'type': 'string',
                        'description': 'Filter by status: "active" (not completed/neverminded), "completed", "neverminded", or "all"',
                        'enum': ['active', 'completed', 'neverminded', 'all']
                    }
                },
                'required': []
            }
        },
        'executor': list_intentions_executor,
        'requires_user': True
    },
    'get_intention_details': {
        'schema': {
            'name': 'get_intention_details',
            'description': 'Get detailed information about a specific intention by ID. Use when user asks for details about a specific task or when you need to verify intention properties before updating.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'intention_id': {
                        'type': 'integer',
                        'description': 'ID of the intention to retrieve (shown in parentheses like "ID: 123")'
                    }
                },
                'required': ['intention_id']
            }
        },
        'executor': get_intention_details_executor,
        'requires_user': True
    },
    'update_intention': {
        'schema': {
            'name': 'update_intention',
            'description': 'Update an intention\'s title and/or date. Use when user wants to modify, rename, change, or reschedule an existing task. At least one of title or date must be provided.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'intention_id': {
                        'type': 'integer',
                        'description': 'ID of the intention to update (shown in parentheses like "ID: 123")'
                    },
                    'title': {
                        'type': 'string',
                        'description': 'New title for the intention (optional, max 500 characters)'
                    },
                    'date': {
                        'type': 'string',
                        'description': 'New date in YYYY-MM-DD format (optional)'
                    }
                },
                'required': ['intention_id']
            }
        },
        'executor': update_intention_executor,
        'requires_user': True
    },
    'delete_intention': {
        'schema': {
            'name': 'delete_intention',
            'description': 'Delete an intention permanently. Use when user wants to remove, delete, or get rid of a task entirely. This is permanent and cannot be undone.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'intention_id': {
                        'type': 'integer',
                        'description': 'ID of the intention to delete (shown in parentheses like "ID: 123")'
                    }
                },
                'required': ['intention_id']
            }
        },
        'executor': delete_intention_executor,
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

            # Save to AgentAction model for audit trail
            if self.user:
                from intentions_page.models import AgentAction
                AgentAction.objects.create(
                    user=self.user,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_output=result,
                    success=True,
                    error=None
                )

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

            # Save failed execution to AgentAction model
            if self.user:
                from intentions_page.models import AgentAction
                AgentAction.objects.create(
                    user=self.user,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_output=None,
                    success=False,
                    error=str(e)
                )

            return {
                'success': False,
                'result': None,
                'error': str(e)
            }
