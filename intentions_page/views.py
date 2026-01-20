from django.db import transaction

from intentions_page.forms import IntentionEditForm, NoteEditForm, IntentionsDraftEditForm
from intentions_page.models import Intention, Note, IntentionsDraft, ChatMessage
import django.utils.timezone as timezone
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.views.decorators.csrf import ensure_csrf_cookie
from intentions_page.models import get_working_day_date
import json
import logging

logger = logging.getLogger(__name__)


@ensure_csrf_cookie
def home(request):
    if request.user.is_authenticated:
        working_day_date = get_working_day_date()

        # Copy sticky intentions from previous day(s)
        # Handle multi-day gaps by iterating day by day
        from django.db import models
        last_intention_date = Intention.objects.filter(creator=request.user).aggregate(
            models.Max('date')
        )['date__max']

        if last_intention_date and last_intention_date < working_day_date:
            current_date = last_intention_date
            while current_date < working_day_date:
                next_date = current_date + timezone.timedelta(days=1)
                Intention.copy_sticky_intentions_forward(request.user, current_date, next_date)
                current_date = next_date

        tomorrow_date = working_day_date + timezone.timedelta(days=1)

        tomorrow_draft_field = get_or_init_intentions_draft_field(request.user, tomorrow_date)
        today_draft_field = get_or_init_intentions_draft_field(request.user, working_day_date)

        content_by_date = create_day_range(working_day_date, working_day_date, request.user)
        content_by_date[working_day_date]['note'].collapse = True

        context = {
            'content_by_date': content_by_date,
            'tomorrow_draft_field':tomorrow_draft_field,
            'today_draft_field':today_draft_field,
        }

        return render(request, 'pages/home.html', context)
    else:
        return render(request, 'pages/welcome.html')

def get_or_init_intentions_draft_field(user, date):
    draft = IntentionsDraft.objects.filter(creator=user, date=date).first()
    if not draft:
        draft = IntentionsDraft(creator=user, date=date)
        draft.save()
    return IntentionsDraftEditForm(instance=draft)

@login_required
def history(request):
    intentions = Intention.objects.filter(creator=request.user)
    notes = Note.objects.filter(creator=request.user)

    end_date = get_working_day_date()

    start_date_candidates = [end_date]
    if intentions:
        start_date_candidates.append(intentions.last().date)
    if notes:
        start_date_candidates.append(notes.last().date)

    start_date = min(start_date_candidates)

    day_range = create_day_range(start_date, end_date, request.user)

    context = {
        'content_by_date': day_range
    }

    return render(request, 'pages/history.html', context)

def create_day(date, user):

    intentions = Intention.objects.filter(creator=user, date=date)

    for i in intentions:
        i.edit_form = IntentionEditForm(instance=i)

    note = Note.objects.filter(creator=user, date=date).first()
    if not note:
        note = Note(creator=user, date=date)
        note.save()

    note.edit_form = NoteEditForm(instance=note)
    note.collapse = False

    return {'intentions': intentions, 'note': note}

def create_day_range(start,end,user):
    day_range = {}

    num_days = (end - start).days + 1

    date_range = (end - timezone.timedelta(days=x) for x in range(num_days))

    for date in date_range:
        day_range[date] = create_day(date, user)

    return day_range

@login_required
def promote_draft_to_intentions(request):
    intentions = request.POST['content'].splitlines()
    for i in intentions:
        if not i.isspace() and not i == "":
            Intention.objects.create(title=i, creator=request.user)

    IntentionsDraft.objects.filter(creator=request.user, date=get_working_day_date()).delete()

    return redirect('home')


@login_required
@transaction.atomic
def edit(request, primary_key):
    intention = Intention.objects.select_for_update().get(id=primary_key)

    if intention.creator != get_user(request):
        raise PermissionDenied

    if request.method == 'POST':
        # Handle recurring toggle separately
        if 'toggle_recurring' in request.POST:
            if intention.recurring_intention and intention.recurring_intention.is_active:
                # Turn off recurring: deactivate the pattern
                logger.info(f"Deactivating recurring for intention {intention.id}: {intention.title}")
                intention.recurring_intention.is_active = False
                intention.recurring_intention.save()
            elif intention.recurring_intention and not intention.recurring_intention.is_active:
                # Reactivate an existing inactive pattern
                logger.info(f"Reactivating recurring for intention {intention.id}: {intention.title}")
                intention.recurring_intention.is_active = True
                intention.recurring_intention.save()
            else:
                # Turn on recurring: create a new daily pattern
                logger.info(f"Creating new recurring pattern for intention {intention.id}: {intention.title}")
                pattern, created = intention.get_or_create_recurring_pattern()
                logger.info(f"RecurringIntention {pattern.id} created={created}")

            # Refresh the intention to get updated recurring status
            intention.refresh_from_db()
            # Initialize form for template rendering
            intention.edit_form = IntentionEditForm(instance=intention)
        else:
            # Handle normal form fields
            intention.edit_form = IntentionEditForm(request.POST, instance=intention)

            if intention.edit_form.is_valid():
                # Enforce single froggy per day: if marking this as froggy, un-frog others
                if intention.edit_form.cleaned_data.get('froggy', False):
                    Intention.objects.filter(
                        creator=request.user,
                        date=intention.date,
                        froggy=True
                    ).exclude(id=intention.id).update(froggy=False)

                intention.edit_form.save()

    return render(request, "components/single_intention.html", context={'intention': intention})

@login_required
def append(request, primary_key):
    if request.method == 'POST':
        intention = Intention.objects.get(id=primary_key)

        if intention.creator != get_user(request):
            raise PermissionDenied

        intention.title += ' ' + request.POST['append']
        intention.save()

    return redirect(request.headers.get('Referer', 'home'))

@login_required
def note(request, primary_key):
    if request.method == 'POST':
        note = Note.objects.get(id=primary_key)
        return autosave_field(request, note)

@login_required
def intentions_draft(request, primary_key):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                draft = IntentionsDraft.objects.select_for_update().get(id=primary_key)
                return autosave_field(request, draft)
        except IntentionsDraft.DoesNotExist:  # It would be cleaner not to send these requests in the first place
            return HttpResponse(status=200)

def autosave_field(request, object):
    if object.creator != get_user(request):
        raise PermissionDenied
    if object.version < int(request.POST['version']):
        object.content = request.POST['content']
        object.version = request.POST['version']
        object.save()
    return HttpResponse(status=200)

def feedback(request):
    email = request.POST.get("email")
    message = request.POST.get("message")
    message = message.replace('\n', '<br>')
    path = request.path

    html = f"<html>" \
           f"<br><b>path: </b>{path}" \
           f"<br><b>email: </b>{email}" \
           f"<br><b>message: </b>{message}" \
           f"</html>"

    result = send_mail("Feedback on intentions.page", message, recipient_list=['tmkadamcz@gmail.com'], html_message=html, from_email=email)

    if result == 1:
        return HttpResponse(status=200)
    else:
        return HttpResponse(status=500)

def privacy_policy(request):
    return render(request, "privacy-policy.html")

def build_intentions_context(user, include_history_days=7):
    """Build text summary of user's intentions for LLM context."""
    from datetime import timedelta

    working_day = get_working_day_date()
    start_date = working_day - timedelta(days=include_history_days)

    intentions = Intention.objects.filter(
        creator=user,
        date__gte=start_date,
        date__lte=working_day
    ).order_by('-date', 'created_datetime')

    if not intentions:
        return "No current intentions."

    # Group by date and format with status markers
    intentions_by_date = {}
    for intention in intentions:
        date_str = intention.date.strftime('%Y-%m-%d (%A)')
        if date_str not in intentions_by_date:
            intentions_by_date[date_str] = []

        status = ""
        if intention.completed:
            status = "[COMPLETED] "
        elif intention.neverminded:
            status = "[NEVERMINDED] "
        elif intention.sticky:
            status = "[STICKY] "
        elif intention.froggy:
            status = "[FROG - Most Important] "
        elif intention.anxiety_inducing:
            status = "[CHARGED] "

        # Include intention ID for tool use
        intentions_by_date[date_str].append(f"{status}{intention.title} (ID: {intention.id})")

    # Format as text
    context_lines = []
    for date_str, items in intentions_by_date.items():
        context_lines.append(f"\n{date_str}:")
        for item in items:
            context_lines.append(f"  - {item}")

    return "\n".join(context_lines)

def prepare_messages_for_llm(chat_messages):
    """
    Convert ChatMessage objects to format expected by LLM API.
    Handles both plain text and JSON-structured messages.
    """
    llm_messages = []

    for msg in chat_messages:
        if msg.role == 'system':
            continue  # System messages handled separately

        # Try to parse content as JSON
        try:
            content_data = json.loads(msg.content)

            if isinstance(content_data, dict) and 'content_blocks' in content_data:
                # Message with tool use
                llm_messages.append({
                    'role': msg.role,
                    'content': content_data['content_blocks']
                })
            elif isinstance(content_data, dict) and content_data.get('type') == 'tool_result':
                # Tool result message
                llm_messages.append({
                    'role': 'user',
                    'content': [{
                        'type': 'tool_result',
                        'tool_use_id': content_data['tool_use_id'],
                        'content': json.dumps(content_data['content']),
                        'is_error': content_data.get('is_error', False)
                    }]
                })
            else:
                # Unknown JSON, treat as text
                llm_messages.append({
                    'role': msg.role,
                    'content': msg.content
                })
        except (json.JSONDecodeError, ValueError, TypeError):
            # Plain text message (backward compatible)
            llm_messages.append({
                'role': msg.role,
                'content': msg.content
            })

    return llm_messages

@login_required
def chat_history(request):
    """Return chat history as JSON."""
    messages = ChatMessage.objects.filter(creator=request.user)
    messages_data = []

    for msg in messages:
        # Try to parse structured content
        try:
            content_data = json.loads(msg.content)
            if isinstance(content_data, dict) and 'tool_executions' in content_data:
                # Extract display text from content blocks
                display_text = ""
                for block in content_data.get('content_blocks', []):
                    if block.get('type') == 'text':
                        display_text += block.get('text', '')

                messages_data.append({
                    'id': msg.id,
                    'role': msg.role,
                    'content': display_text,
                    'created_datetime': msg.created_datetime.isoformat(),
                    'llm_provider': msg.llm_provider,
                    'tool_executions': content_data.get('tool_executions', [])
                })
            else:
                # Regular message
                messages_data.append({
                    'id': msg.id,
                    'role': msg.role,
                    'content': msg.content,
                    'created_datetime': msg.created_datetime.isoformat(),
                    'llm_provider': msg.llm_provider
                })
        except (json.JSONDecodeError, ValueError, TypeError):
            # Plain text message
            messages_data.append({
                'id': msg.id,
                'role': msg.role,
                'content': msg.content,
                'created_datetime': msg.created_datetime.isoformat(),
                'llm_provider': msg.llm_provider
            })

    return JsonResponse({
        'messages': messages_data,
        # Include preference to keep client state in sync on page load
        'show_tool_confirmations': request.user.show_tool_confirmations
    })

@login_required
def chat_send_message(request):
    """Handle sending message to LLM and getting response."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        include_intentions = data.get('include_intentions', True)

        if not user_message:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)

        # Rate limiting
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        messages_today = ChatMessage.objects.filter(
            creator=request.user,
            role='user',
            created_datetime__gte=today_start
        ).count()

        if messages_today >= settings.LLM_MAX_MESSAGES_PER_DAY:
            return JsonResponse({
                'error': f'Daily message limit ({settings.LLM_MAX_MESSAGES_PER_DAY}) reached'
            }, status=429)

        # Save user message
        user_msg = ChatMessage.objects.create(
            creator=request.user,
            role='user',
            content=user_message
        )

        # Get recent conversation history (last 20 messages)
        recent_messages = ChatMessage.objects.filter(
            creator=request.user
        ).order_by('-created_datetime')[:20]

        llm_messages = prepare_messages_for_llm(reversed(recent_messages))

        # Get intentions context if requested
        intentions_context = None
        if include_intentions:
            intentions_context = build_intentions_context(request.user, include_history_days=0)

        # Get LLM response with tool support
        from intentions_page.llm_service import LLMService
        llm_service = LLMService()
        response_dict, provider_used = llm_service.get_completion_with_tools(
            llm_messages,
            intentions_context,
            user=request.user
        )

        # Save assistant response
        if response_dict.get('tool_executions'):
            # Store structured response with tool executions
            assistant_content = json.dumps({
                'type': 'assistant',
                'content_blocks': response_dict.get('content_blocks', []),
                'tool_executions': response_dict['tool_executions']
            })
        else:
            # Store plain text (backward compatible)
            assistant_content = response_dict['content']

        assistant_msg = ChatMessage.objects.create(
            creator=request.user,
            role='assistant',
            content=assistant_content,
            llm_provider=provider_used
        )

        return JsonResponse({
            'user_message': {
                'id': user_msg.id,
                'role': user_msg.role,
                'content': user_msg.content,
                'created_datetime': user_msg.created_datetime.isoformat()
            },
            'assistant_message': {
                'id': assistant_msg.id,
                'role': assistant_msg.role,
                'content': response_dict['content'],
                'created_datetime': assistant_msg.created_datetime.isoformat(),
                'llm_provider': assistant_msg.llm_provider,
                'tool_executions': response_dict.get('tool_executions', [])
            },
            # Include preference in every response to keep client state in sync
            'show_tool_confirmations': request.user.show_tool_confirmations
        })

    except Exception as e:
        logger.error(f"Chat error: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def chat_clear_history(request):
    """Clear all chat history for current user."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    deleted_count, _ = ChatMessage.objects.filter(creator=request.user).delete()
    return JsonResponse({'deleted_count': deleted_count})
