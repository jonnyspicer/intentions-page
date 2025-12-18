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


def create_intentions_batch_executor(tool_input, user=None):
    """
    Execute the create_intentions_batch tool to create multiple intentions at once.

    Args:
        tool_input: Dict with keys: intentions (list of dicts), date (optional)
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import Intention, get_working_day_date
    from django.utils.dateparse import parse_date
    from django.db import transaction

    intentions_list = tool_input.get('intentions', [])
    if not intentions_list:
        raise ValueError("intentions list is required and cannot be empty")

    if not isinstance(intentions_list, list):
        raise ValueError("intentions must be a list")

    if len(intentions_list) > 20:
        raise ValueError("Cannot create more than 20 intentions at once")

    # Parse common date if provided
    date_str = tool_input.get('date')
    if date_str:
        common_date = parse_date(date_str)
        if not common_date:
            raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")
    else:
        common_date = None  # Will use working day per intention

    # Validate all intentions before creating any
    validated_intentions = []
    frog_count = 0

    for idx, intention_spec in enumerate(intentions_list):
        if not isinstance(intention_spec, dict):
            raise ValueError(f"Intention #{idx + 1} must be a dictionary/object")

        # Validate title
        title = intention_spec.get('title', '').strip()
        if not title:
            raise ValueError(f"Intention #{idx + 1}: title is required and cannot be empty")
        if len(title) > 500:
            raise ValueError(f"Intention #{idx + 1}: title cannot exceed 500 characters")

        # Parse date for this intention (use common_date if no specific date)
        intention_date_str = intention_spec.get('date')
        if intention_date_str:
            intention_date = parse_date(intention_date_str)
            if not intention_date:
                raise ValueError(
                    f"Intention #{idx + 1}: invalid date format '{intention_date_str}'. Use YYYY-MM-DD."
                )
        elif common_date:
            intention_date = common_date
        else:
            intention_date = get_working_day_date()

        # Extract flags
        froggy = intention_spec.get('froggy', False)
        sticky = intention_spec.get('sticky', False)
        anxiety_inducing = intention_spec.get('anxiety_inducing', False)

        # Check frog constraint
        if froggy:
            frog_count += 1
            if frog_count > 1:
                raise ValueError(
                    "Cannot create multiple frogs in the same batch. Only one frog per day allowed."
                )

        validated_intentions.append({
            'title': title,
            'date': intention_date,
            'froggy': froggy,
            'sticky': sticky,
            'anxiety_inducing': anxiety_inducing
        })

    # Create all intentions atomically
    created_intentions = []

    with transaction.atomic():
        # If there's a frog in the batch, check for existing frogs
        if frog_count > 0:
            frog_intention = next(i for i in validated_intentions if i['froggy'])
            existing_frog = Intention.objects.select_for_update().filter(
                creator=user,
                date=frog_intention['date'],
                froggy=True
            ).first()

            if existing_frog:
                raise ValueError(
                    f"A frog already exists for {frog_intention['date']}: '{existing_frog.title}'. "
                    f"Only one frog per day allowed."
                )

        # Create all intentions
        for intention_data in validated_intentions:
            intention = Intention.objects.create(
                title=intention_data['title'],
                date=intention_data['date'],
                creator=user,
                froggy=intention_data['froggy'],
                sticky=intention_data['sticky'],
                anxiety_inducing=intention_data['anxiety_inducing'],
                completed=False,
                neverminded=False
            )
            created_intentions.append(intention)

    logger.info(
        f"Batch created {len(created_intentions)} intentions for user {user.id}"
    )

    # Build result list
    results = []
    for intention in created_intentions:
        results.append({
            'intention_id': intention.id,
            'title': intention.title,
            'date': intention.date.isoformat(),
            'froggy': intention.froggy,
            'sticky': intention.sticky,
            'anxiety_inducing': intention.anxiety_inducing
        })

    return {
        'count': len(created_intentions),
        'intentions': results,
        'message': f"Successfully created {len(created_intentions)} intention(s)"
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


def create_recurring_intention_executor(tool_input, user=None):
    """
    Execute the create_recurring_intention tool.

    Args:
        tool_input: Dict with keys: title, frequency, interval, start_date, and pattern-specific fields
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import RecurringIntention
    from django.utils.dateparse import parse_date

    # Validate title
    title = tool_input.get('title', '').strip()
    if not title:
        raise ValueError("Title is required and cannot be empty")
    if len(title) > 500:
        raise ValueError("Title cannot exceed 500 characters")

    # Validate frequency
    frequency = tool_input.get('frequency')
    valid_frequencies = ['daily', 'weekly', 'monthly', 'yearly']
    if not frequency:
        raise ValueError("frequency is required")
    if frequency not in valid_frequencies:
        raise ValueError(
            f"Invalid frequency '{frequency}'. Must be one of: {', '.join(valid_frequencies)}"
        )

    # Validate interval
    interval = tool_input.get('interval', 1)
    if not isinstance(interval, int) or interval < 1:
        raise ValueError("interval must be a positive integer (1 or greater)")

    # Validate start_date
    start_date_str = tool_input.get('start_date')
    if not start_date_str:
        raise ValueError("start_date is required")
    start_date = parse_date(start_date_str)
    if not start_date:
        raise ValueError(f"Invalid start_date format: {start_date_str}. Use YYYY-MM-DD.")

    # Validate end_date (optional)
    end_date = None
    end_date_str = tool_input.get('end_date')
    if end_date_str:
        end_date = parse_date(end_date_str)
        if not end_date:
            raise ValueError(f"Invalid end_date format: {end_date_str}. Use YYYY-MM-DD.")
        if end_date < start_date:
            raise ValueError("end_date cannot be before start_date")

    # Frequency-specific validation
    days_of_week = None
    day_of_month = None
    month = None

    if frequency == 'weekly':
        days_of_week = tool_input.get('days_of_week')
        if not days_of_week:
            raise ValueError("days_of_week is required for weekly frequency (list of 0-6, where 0=Monday)")
        if not isinstance(days_of_week, list):
            raise ValueError("days_of_week must be a list of integers (0-6)")
        if not days_of_week:
            raise ValueError("days_of_week cannot be empty")
        for day in days_of_week:
            if not isinstance(day, int) or day < 0 or day > 6:
                raise ValueError("days_of_week must contain integers between 0 (Monday) and 6 (Sunday)")

    elif frequency == 'monthly':
        day_of_month = tool_input.get('day_of_month')
        if not day_of_month:
            raise ValueError("day_of_month is required for monthly frequency (1-31)")
        if not isinstance(day_of_month, int) or day_of_month < 1 or day_of_month > 31:
            raise ValueError("day_of_month must be an integer between 1 and 31")

    elif frequency == 'yearly':
        month = tool_input.get('month')
        day_of_month = tool_input.get('day_of_month')
        if not month:
            raise ValueError("month is required for yearly frequency (1-12)")
        if not day_of_month:
            raise ValueError("day_of_month is required for yearly frequency (1-31)")
        if not isinstance(month, int) or month < 1 or month > 12:
            raise ValueError("month must be an integer between 1 and 12")
        if not isinstance(day_of_month, int) or day_of_month < 1 or day_of_month > 31:
            raise ValueError("day_of_month must be an integer between 1 and 31")

    # Get default flags
    default_sticky = tool_input.get('default_sticky', False)
    default_froggy = tool_input.get('default_froggy', False)
    default_anxiety_inducing = tool_input.get('default_anxiety_inducing', False)

    # Create recurring intention
    recurring_intention = RecurringIntention.objects.create(
        title=title,
        creator=user,
        frequency=frequency,
        interval=interval,
        days_of_week=days_of_week,
        day_of_month=day_of_month,
        month=month,
        start_date=start_date,
        end_date=end_date,
        is_active=True,
        default_sticky=default_sticky,
        default_froggy=default_froggy,
        default_anxiety_inducing=default_anxiety_inducing
    )

    logger.info(
        f"Created recurring intention #{recurring_intention.id} for user {user.id}: "
        f"{title} ({frequency})"
    )

    # Build pattern description
    if frequency == 'daily':
        pattern = f"every {interval} day(s)" if interval > 1 else "daily"
    elif frequency == 'weekly':
        days_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        day_names = [days_names[d] for d in sorted(days_of_week)]
        pattern = f"every {interval} week(s) on {', '.join(day_names)}" if interval > 1 else f"weekly on {', '.join(day_names)}"
    elif frequency == 'monthly':
        pattern = f"every {interval} month(s) on day {day_of_month}" if interval > 1 else f"monthly on day {day_of_month}"
    elif frequency == 'yearly':
        pattern = f"every {interval} year(s) on {month}/{day_of_month}" if interval > 1 else f"yearly on {month}/{day_of_month}"

    return {
        'recurring_intention_id': recurring_intention.id,
        'title': recurring_intention.title,
        'frequency': recurring_intention.frequency,
        'pattern': pattern,
        'start_date': recurring_intention.start_date.isoformat(),
        'end_date': recurring_intention.end_date.isoformat() if recurring_intention.end_date else None,
        'is_active': recurring_intention.is_active,
        'message': f"Successfully created recurring intention: {title} ({pattern})"
    }


def list_recurring_intentions_executor(tool_input, user=None):
    """
    Execute the list_recurring_intentions tool.

    Args:
        tool_input: Dict with keys: active_only (optional, default True)
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import RecurringIntention

    active_only = tool_input.get('active_only', True)
    if not isinstance(active_only, bool):
        raise ValueError("active_only must be a boolean (true or false)")

    # Query recurring intentions
    recurring_intentions = RecurringIntention.objects.filter(creator=user)

    if active_only:
        recurring_intentions = recurring_intentions.filter(is_active=True)

    recurring_intentions = recurring_intentions.order_by('created_datetime')

    # Build result list
    intentions_list = []
    for ri in recurring_intentions:
        # Build pattern description
        if ri.frequency == 'daily':
            pattern = f"every {ri.interval} day(s)" if ri.interval > 1 else "daily"
        elif ri.frequency == 'weekly':
            if ri.days_of_week:
                days_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                day_names = [days_names[d] for d in sorted(ri.days_of_week)]
                pattern = f"every {ri.interval} week(s) on {', '.join(day_names)}" if ri.interval > 1 else f"weekly on {', '.join(day_names)}"
            else:
                pattern = "weekly (no days configured)"
        elif ri.frequency == 'monthly':
            pattern = f"every {ri.interval} month(s) on day {ri.day_of_month}" if ri.interval > 1 else f"monthly on day {ri.day_of_month}"
        elif ri.frequency == 'yearly':
            pattern = f"every {ri.interval} year(s) on {ri.month}/{ri.day_of_month}" if ri.interval > 1 else f"yearly on {ri.month}/{ri.day_of_month}"

        intentions_list.append({
            'id': ri.id,
            'title': ri.title,
            'frequency': ri.frequency,
            'pattern': pattern,
            'start_date': ri.start_date.isoformat(),
            'end_date': ri.end_date.isoformat() if ri.end_date else None,
            'is_active': ri.is_active,
            'default_sticky': ri.default_sticky,
            'default_froggy': ri.default_froggy,
            'default_anxiety_inducing': ri.default_anxiety_inducing,
            'last_generated_date': ri.last_generated_date.isoformat() if ri.last_generated_date else None
        })

    logger.info(
        f"Listed {len(intentions_list)} recurring intentions for user {user.id} "
        f"(active_only={active_only})"
    )

    return {
        'count': len(intentions_list),
        'active_only': active_only,
        'recurring_intentions': intentions_list,
        'message': f"Found {len(intentions_list)} recurring intention(s)"
    }


def update_recurring_intention_executor(tool_input, user=None):
    """
    Execute the update_recurring_intention tool.

    Args:
        tool_input: Dict with keys: recurring_intention_id, and any fields to update
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import RecurringIntention
    from django.utils.dateparse import parse_date

    recurring_intention_id = tool_input.get('recurring_intention_id')
    if not recurring_intention_id:
        raise ValueError("recurring_intention_id is required")

    if not isinstance(recurring_intention_id, int):
        raise ValueError("recurring_intention_id must be an integer")

    # Get the recurring intention and verify ownership
    try:
        recurring_intention = RecurringIntention.objects.get(id=recurring_intention_id, creator=user)
    except RecurringIntention.DoesNotExist:
        raise ValueError(
            f"Recurring intention with ID {recurring_intention_id} not found or doesn't belong to you"
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

        if new_title != recurring_intention.title:
            old_title = recurring_intention.title
            recurring_intention.title = new_title
            changes.append(f"title: '{old_title}' -> '{new_title}'")

    # Update frequency if provided
    new_frequency = tool_input.get('frequency')
    if new_frequency is not None:
        valid_frequencies = ['daily', 'weekly', 'monthly', 'yearly']
        if new_frequency not in valid_frequencies:
            raise ValueError(
                f"Invalid frequency '{new_frequency}'. Must be one of: {', '.join(valid_frequencies)}"
            )
        if new_frequency != recurring_intention.frequency:
            old_frequency = recurring_intention.frequency
            recurring_intention.frequency = new_frequency
            changes.append(f"frequency: {old_frequency} -> {new_frequency}")

    # Update interval if provided
    new_interval = tool_input.get('interval')
    if new_interval is not None:
        if not isinstance(new_interval, int) or new_interval < 1:
            raise ValueError("interval must be a positive integer (1 or greater)")
        if new_interval != recurring_intention.interval:
            old_interval = recurring_intention.interval
            recurring_intention.interval = new_interval
            changes.append(f"interval: {old_interval} -> {new_interval}")

    # Update start_date if provided
    new_start_date_str = tool_input.get('start_date')
    if new_start_date_str is not None:
        new_start_date = parse_date(new_start_date_str)
        if not new_start_date:
            raise ValueError(f"Invalid start_date format: {new_start_date_str}. Use YYYY-MM-DD.")
        if new_start_date != recurring_intention.start_date:
            old_start_date = recurring_intention.start_date
            recurring_intention.start_date = new_start_date
            changes.append(f"start_date: {old_start_date.isoformat()} -> {new_start_date.isoformat()}")

    # Update end_date if provided
    new_end_date_str = tool_input.get('end_date')
    if new_end_date_str is not None:
        new_end_date = parse_date(new_end_date_str)
        if not new_end_date:
            raise ValueError(f"Invalid end_date format: {new_end_date_str}. Use YYYY-MM-DD.")
        if new_end_date < recurring_intention.start_date:
            raise ValueError("end_date cannot be before start_date")
        if new_end_date != recurring_intention.end_date:
            old_end_date = recurring_intention.end_date
            recurring_intention.end_date = new_end_date
            changes.append(f"end_date: {old_end_date.isoformat() if old_end_date else 'None'} -> {new_end_date.isoformat()}")

    # Update pattern-specific fields
    new_days_of_week = tool_input.get('days_of_week')
    if new_days_of_week is not None:
        if not isinstance(new_days_of_week, list):
            raise ValueError("days_of_week must be a list of integers (0-6)")
        if not new_days_of_week:
            raise ValueError("days_of_week cannot be empty")
        for day in new_days_of_week:
            if not isinstance(day, int) or day < 0 or day > 6:
                raise ValueError("days_of_week must contain integers between 0 (Monday) and 6 (Sunday)")
        if new_days_of_week != recurring_intention.days_of_week:
            recurring_intention.days_of_week = new_days_of_week
            changes.append(f"days_of_week: {recurring_intention.days_of_week} -> {new_days_of_week}")

    new_day_of_month = tool_input.get('day_of_month')
    if new_day_of_month is not None:
        if not isinstance(new_day_of_month, int) or new_day_of_month < 1 or new_day_of_month > 31:
            raise ValueError("day_of_month must be an integer between 1 and 31")
        if new_day_of_month != recurring_intention.day_of_month:
            old_day = recurring_intention.day_of_month
            recurring_intention.day_of_month = new_day_of_month
            changes.append(f"day_of_month: {old_day} -> {new_day_of_month}")

    new_month = tool_input.get('month')
    if new_month is not None:
        if not isinstance(new_month, int) or new_month < 1 or new_month > 12:
            raise ValueError("month must be an integer between 1 and 12")
        if new_month != recurring_intention.month:
            old_month = recurring_intention.month
            recurring_intention.month = new_month
            changes.append(f"month: {old_month} -> {new_month}")

    # Update default flags if provided
    new_default_sticky = tool_input.get('default_sticky')
    if new_default_sticky is not None:
        if not isinstance(new_default_sticky, bool):
            raise ValueError("default_sticky must be a boolean")
        if new_default_sticky != recurring_intention.default_sticky:
            recurring_intention.default_sticky = new_default_sticky
            changes.append(f"default_sticky: {not new_default_sticky} -> {new_default_sticky}")

    new_default_froggy = tool_input.get('default_froggy')
    if new_default_froggy is not None:
        if not isinstance(new_default_froggy, bool):
            raise ValueError("default_froggy must be a boolean")
        if new_default_froggy != recurring_intention.default_froggy:
            recurring_intention.default_froggy = new_default_froggy
            changes.append(f"default_froggy: {not new_default_froggy} -> {new_default_froggy}")

    new_default_anxiety_inducing = tool_input.get('default_anxiety_inducing')
    if new_default_anxiety_inducing is not None:
        if not isinstance(new_default_anxiety_inducing, bool):
            raise ValueError("default_anxiety_inducing must be a boolean")
        if new_default_anxiety_inducing != recurring_intention.default_anxiety_inducing:
            recurring_intention.default_anxiety_inducing = new_default_anxiety_inducing
            changes.append(f"default_anxiety_inducing: {not new_default_anxiety_inducing} -> {new_default_anxiety_inducing}")

    # Check if any changes were made
    if not changes:
        return {
            'recurring_intention_id': recurring_intention.id,
            'title': recurring_intention.title,
            'changes': [],
            'message': "No changes made - recurring intention already has the specified values"
        }

    # Save the changes
    recurring_intention.save()

    logger.info(
        f"Updated recurring intention #{recurring_intention.id} for user {user.id}: {', '.join(changes)}"
    )

    return {
        'recurring_intention_id': recurring_intention.id,
        'title': recurring_intention.title,
        'changes': changes,
        'message': f"Successfully updated recurring intention: {', '.join(changes)}"
    }


def pause_recurring_intention_executor(tool_input, user=None):
    """
    Execute the pause_recurring_intention tool.

    Args:
        tool_input: Dict with keys: recurring_intention_id (int)
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import RecurringIntention

    recurring_intention_id = tool_input.get('recurring_intention_id')
    if not recurring_intention_id:
        raise ValueError("recurring_intention_id is required")

    if not isinstance(recurring_intention_id, int):
        raise ValueError("recurring_intention_id must be an integer")

    # Get the recurring intention and verify ownership
    try:
        recurring_intention = RecurringIntention.objects.get(id=recurring_intention_id, creator=user)
    except RecurringIntention.DoesNotExist:
        raise ValueError(
            f"Recurring intention with ID {recurring_intention_id} not found or doesn't belong to you"
        )

    # Check if already paused
    if not recurring_intention.is_active:
        logger.info(
            f"Recurring intention #{recurring_intention.id} already paused for user {user.id}"
        )
        return {
            'recurring_intention_id': recurring_intention.id,
            'title': recurring_intention.title,
            'is_active': False,
            'message': f"Recurring intention was already paused: {recurring_intention.title}"
        }

    # Pause the recurring intention
    recurring_intention.is_active = False
    recurring_intention.save()

    logger.info(f"Paused recurring intention #{recurring_intention.id} for user {user.id}")

    return {
        'recurring_intention_id': recurring_intention.id,
        'title': recurring_intention.title,
        'is_active': False,
        'message': f"Successfully paused recurring intention: {recurring_intention.title}"
    }


def resume_recurring_intention_executor(tool_input, user=None):
    """
    Execute the resume_recurring_intention tool.

    Args:
        tool_input: Dict with keys: recurring_intention_id (int)
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import RecurringIntention

    recurring_intention_id = tool_input.get('recurring_intention_id')
    if not recurring_intention_id:
        raise ValueError("recurring_intention_id is required")

    if not isinstance(recurring_intention_id, int):
        raise ValueError("recurring_intention_id must be an integer")

    # Get the recurring intention and verify ownership
    try:
        recurring_intention = RecurringIntention.objects.get(id=recurring_intention_id, creator=user)
    except RecurringIntention.DoesNotExist:
        raise ValueError(
            f"Recurring intention with ID {recurring_intention_id} not found or doesn't belong to you"
        )

    # Check if already active
    if recurring_intention.is_active:
        logger.info(
            f"Recurring intention #{recurring_intention.id} already active for user {user.id}"
        )
        return {
            'recurring_intention_id': recurring_intention.id,
            'title': recurring_intention.title,
            'is_active': True,
            'message': f"Recurring intention was already active: {recurring_intention.title}"
        }

    # Resume the recurring intention
    recurring_intention.is_active = True
    recurring_intention.save()

    logger.info(f"Resumed recurring intention #{recurring_intention.id} for user {user.id}")

    return {
        'recurring_intention_id': recurring_intention.id,
        'title': recurring_intention.title,
        'is_active': True,
        'message': f"Successfully resumed recurring intention: {recurring_intention.title}"
    }


def delete_recurring_intention_executor(tool_input, user=None):
    """
    Execute the delete_recurring_intention tool.

    Args:
        tool_input: Dict with keys: recurring_intention_id (int)
        user: Django User object

    Returns:
        dict with result information

    Raises:
        ValueError: For validation errors
    """
    from intentions_page.models import RecurringIntention

    recurring_intention_id = tool_input.get('recurring_intention_id')
    if not recurring_intention_id:
        raise ValueError("recurring_intention_id is required")

    if not isinstance(recurring_intention_id, int):
        raise ValueError("recurring_intention_id must be an integer")

    # Get the recurring intention and verify ownership
    try:
        recurring_intention = RecurringIntention.objects.get(id=recurring_intention_id, creator=user)
    except RecurringIntention.DoesNotExist:
        raise ValueError(
            f"Recurring intention with ID {recurring_intention_id} not found or doesn't belong to you"
        )

    # Store details before deletion for logging and response
    recurring_intention_title = recurring_intention.title
    recurring_intention_id_str = recurring_intention.id

    # Delete the recurring intention
    # Generated intentions keep their data but lose the link (SET_NULL behavior)
    recurring_intention.delete()

    logger.info(
        f"Deleted recurring intention #{recurring_intention_id_str} for user {user.id}: "
        f"{recurring_intention_title}"
    )

    return {
        'recurring_intention_id': recurring_intention_id_str,
        'title': recurring_intention_title,
        'message': f"Successfully deleted recurring intention: {recurring_intention_title}"
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
    'create_intentions_batch': {
        'schema': {
            'name': 'create_intentions_batch',
            'description': 'Create multiple intentions at once (batch operation). Use when user asks to break down a complex task into subtasks, or wants to create several tasks simultaneously. Maximum 20 intentions per batch.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'intentions': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'title': {
                                    'type': 'string',
                                    'description': 'Title of the intention (max 500 characters)'
                                },
                                'date': {
                                    'type': 'string',
                                    'description': 'Date in YYYY-MM-DD format (optional, overrides batch-level date)'
                                },
                                'froggy': {
                                    'type': 'boolean',
                                    'description': 'Mark as frog/most important (optional, only one frog per day allowed)',
                                    'default': False
                                },
                                'sticky': {
                                    'type': 'boolean',
                                    'description': 'Should carry forward if incomplete (optional)',
                                    'default': False
                                },
                                'anxiety_inducing': {
                                    'type': 'boolean',
                                    'description': 'Causes anxiety/stress (optional)',
                                    'default': False
                                }
                            },
                            'required': ['title']
                        },
                        'description': 'List of intentions to create (max 20). Each must have at least a title.'
                    },
                    'date': {
                        'type': 'string',
                        'description': 'Default date for all intentions in YYYY-MM-DD format. Individual intentions can override this. ONLY provide if user explicitly requests a specific date, otherwise omit to use today\'s date.'
                    }
                },
                'required': ['intentions']
            }
        },
        'executor': create_intentions_batch_executor,
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
    },
    'create_recurring_intention': {
        'schema': {
            'name': 'create_recurring_intention',
            'description': 'Create a recurring intention pattern that automatically generates intentions on specified dates. Use when user wants to set up tasks that repeat daily, weekly, monthly, or yearly. Generated intentions are created by a background job.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'title': {
                        'type': 'string',
                        'description': 'Title of the recurring intention (max 500 characters)'
                    },
                    'frequency': {
                        'type': 'string',
                        'description': 'How often to repeat',
                        'enum': ['daily', 'weekly', 'monthly', 'yearly']
                    },
                    'interval': {
                        'type': 'integer',
                        'description': 'Repeat every N days/weeks/months/years (default: 1)',
                        'default': 1
                    },
                    'start_date': {
                        'type': 'string',
                        'description': 'When to start generating intentions (YYYY-MM-DD format)'
                    },
                    'end_date': {
                        'type': 'string',
                        'description': 'Optional end date (YYYY-MM-DD format). If not provided, pattern continues indefinitely.'
                    },
                    'days_of_week': {
                        'type': 'array',
                        'items': {
                            'type': 'integer'
                        },
                        'description': 'For weekly frequency: list of weekdays [0-6] where 0=Monday, 6=Sunday. Required for weekly.'
                    },
                    'day_of_month': {
                        'type': 'integer',
                        'description': 'For monthly/yearly frequency: day of month (1-31). Required for monthly and yearly. Handles month-end gracefully.'
                    },
                    'month': {
                        'type': 'integer',
                        'description': 'For yearly frequency: month (1-12). Required for yearly.'
                    },
                    'default_sticky': {
                        'type': 'boolean',
                        'description': 'Should generated intentions be sticky by default',
                        'default': False
                    },
                    'default_froggy': {
                        'type': 'boolean',
                        'description': 'Should generated intentions be frogs by default (only if no other frog exists)',
                        'default': False
                    },
                    'default_anxiety_inducing': {
                        'type': 'boolean',
                        'description': 'Should generated intentions be marked as anxiety-inducing by default',
                        'default': False
                    }
                },
                'required': ['title', 'frequency', 'start_date']
            }
        },
        'executor': create_recurring_intention_executor,
        'requires_user': True
    },
    'list_recurring_intentions': {
        'schema': {
            'name': 'list_recurring_intentions',
            'description': 'List all recurring intention patterns for the user. Use when user wants to see their recurring tasks or scheduled patterns.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'active_only': {
                        'type': 'boolean',
                        'description': 'If true, only show active patterns. If false, show all including paused patterns. Default: true',
                        'default': True
                    }
                },
                'required': []
            }
        },
        'executor': list_recurring_intentions_executor,
        'requires_user': True
    },
    'update_recurring_intention': {
        'schema': {
            'name': 'update_recurring_intention',
            'description': 'Update an existing recurring intention pattern. Use when user wants to modify any aspect of a recurring task. Can update title, frequency, dates, pattern settings, or default flags.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'recurring_intention_id': {
                        'type': 'integer',
                        'description': 'ID of the recurring intention to update'
                    },
                    'title': {
                        'type': 'string',
                        'description': 'New title (optional, max 500 characters)'
                    },
                    'frequency': {
                        'type': 'string',
                        'description': 'New frequency (optional)',
                        'enum': ['daily', 'weekly', 'monthly', 'yearly']
                    },
                    'interval': {
                        'type': 'integer',
                        'description': 'New interval (optional, must be positive integer)'
                    },
                    'start_date': {
                        'type': 'string',
                        'description': 'New start date (optional, YYYY-MM-DD format)'
                    },
                    'end_date': {
                        'type': 'string',
                        'description': 'New end date (optional, YYYY-MM-DD format)'
                    },
                    'days_of_week': {
                        'type': 'array',
                        'items': {
                            'type': 'integer'
                        },
                        'description': 'New days of week for weekly patterns (optional, 0-6)'
                    },
                    'day_of_month': {
                        'type': 'integer',
                        'description': 'New day of month for monthly/yearly (optional, 1-31)'
                    },
                    'month': {
                        'type': 'integer',
                        'description': 'New month for yearly patterns (optional, 1-12)'
                    },
                    'default_sticky': {
                        'type': 'boolean',
                        'description': 'New default sticky flag (optional)'
                    },
                    'default_froggy': {
                        'type': 'boolean',
                        'description': 'New default froggy flag (optional)'
                    },
                    'default_anxiety_inducing': {
                        'type': 'boolean',
                        'description': 'New default anxiety-inducing flag (optional)'
                    }
                },
                'required': ['recurring_intention_id']
            }
        },
        'executor': update_recurring_intention_executor,
        'requires_user': True
    },
    'pause_recurring_intention': {
        'schema': {
            'name': 'pause_recurring_intention',
            'description': 'Pause a recurring intention pattern to temporarily stop generating intentions. Use when user wants to temporarily disable a recurring task without deleting it. Paused patterns can be resumed later.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'recurring_intention_id': {
                        'type': 'integer',
                        'description': 'ID of the recurring intention to pause'
                    }
                },
                'required': ['recurring_intention_id']
            }
        },
        'executor': pause_recurring_intention_executor,
        'requires_user': True
    },
    'resume_recurring_intention': {
        'schema': {
            'name': 'resume_recurring_intention',
            'description': 'Resume a paused recurring intention pattern to restart generating intentions. Use when user wants to reactivate a previously paused recurring task.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'recurring_intention_id': {
                        'type': 'integer',
                        'description': 'ID of the recurring intention to resume'
                    }
                },
                'required': ['recurring_intention_id']
            }
        },
        'executor': resume_recurring_intention_executor,
        'requires_user': True
    },
    'delete_recurring_intention': {
        'schema': {
            'name': 'delete_recurring_intention',
            'description': 'Permanently delete a recurring intention pattern. Use when user wants to completely remove a recurring task. Generated intentions remain but lose their link to the pattern. This cannot be undone.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'recurring_intention_id': {
                        'type': 'integer',
                        'description': 'ID of the recurring intention to delete'
                    }
                },
                'required': ['recurring_intention_id']
            }
        },
        'executor': delete_recurring_intention_executor,
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
