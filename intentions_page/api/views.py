from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from intentions_page.models import (
    Intention,
    IntentionsDraft,
    Note,
    RecurringIntention,
    get_working_day_date,
)

from .serializers import (
    IntentionListSerializer,
    IntentionSerializer,
    IntentionsDraftSerializer,
    NoteSerializer,
    RecurringIntentionSerializer,
)


class IntentionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing intentions.

    Provides CRUD operations plus custom actions:
    - today: Get today's intentions
    - bulk_update_order: Update order of multiple intentions
    - mark_completed: Mark intention as completed
    - mark_neverminded: Mark intention as neverminded
    """

    permission_classes = [IsAuthenticated]
    serializer_class = IntentionSerializer
    filterset_fields = ["date", "completed", "neverminded", "sticky", "froggy"]
    ordering_fields = ["order", "created_datetime", "date"]
    ordering = ["order", "created_datetime"]

    def get_queryset(self):
        """Filter intentions to only show the current user's intentions."""
        return Intention.objects.filter(creator=self.request.user)

    def get_serializer_class(self):
        """Use lighter serializer for list actions."""
        if self.action == "list":
            return IntentionListSerializer
        return IntentionSerializer

    def perform_create(self, serializer):
        """Set the creator to the current user when creating."""
        serializer.save(creator=self.request.user)

    @action(detail=False, methods=["get"])
    def today(self, request):
        """Get all intentions for today's working day."""
        today = get_working_day_date()
        intentions = self.get_queryset().filter(date=today)
        serializer = IntentionListSerializer(intentions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def bulk_update_order(self, request):
        """
        Update the order of multiple intentions at once.

        Expected payload:
        {
            "intentions": [
                {"id": 1, "order": 0},
                {"id": 2, "order": 1},
                ...
            ]
        }
        """
        intentions_data = request.data.get("intentions", [])

        if not intentions_data:
            return Response(
                {"error": "No intentions provided"}, status=status.HTTP_400_BAD_REQUEST
            )

        updated_count = 0
        for item in intentions_data:
            intention_id = item.get("id")
            new_order = item.get("order")

            if intention_id is None or new_order is None:
                continue

            try:
                intention = self.get_queryset().get(id=intention_id)
                intention.order = new_order
                intention.save(update_fields=["order"])
                updated_count += 1
            except Intention.DoesNotExist:
                pass

        return Response(
            {
                "updated": updated_count,
                "message": f"Updated order for {updated_count} intention(s)",
            }
        )

    @action(detail=True, methods=["post"])
    def mark_completed(self, request, pk=None):
        """Mark an intention as completed."""
        intention = self.get_object()
        intention.completed = True
        intention.neverminded = False
        intention.save(update_fields=["completed", "neverminded"])
        serializer = self.get_serializer(intention)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def mark_neverminded(self, request, pk=None):
        """Mark an intention as neverminded (dismissed)."""
        intention = self.get_object()
        intention.neverminded = True
        intention.completed = False
        intention.save(update_fields=["completed", "neverminded"])
        serializer = self.get_serializer(intention)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def toggle_completed(self, request, pk=None):
        """Toggle the completed status of an intention."""
        intention = self.get_object()
        intention.completed = not intention.completed
        if intention.completed:
            intention.neverminded = False
        intention.save(update_fields=["completed", "neverminded"])
        serializer = self.get_serializer(intention)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def make_recurring(self, request, pk=None):
        """
        Convert an intention to a recurring pattern.

        Creates a daily recurring intention and links it to this intention.
        """
        intention = self.get_object()
        recurring, created = intention.get_or_create_recurring_pattern()

        return Response(
            {
                "message": "Recurring pattern created"
                if created
                else "Already has recurring pattern",
                "recurring_intention_id": recurring.id,
                "created": created,
            }
        )


class NoteViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing notes.

    Notes are daily journal entries, one per user per day.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = NoteSerializer
    filterset_fields = ["date"]
    ordering_fields = ["date", "created_datetime"]
    ordering = ["-date"]

    def get_queryset(self):
        """Filter notes to only show the current user's notes."""
        return Note.objects.filter(creator=self.request.user)

    def perform_create(self, serializer):
        """Set the creator to the current user when creating."""
        serializer.save(creator=self.request.user)

    @action(detail=False, methods=["get"])
    def today(self, request):
        """Get today's note if it exists."""
        today = get_working_day_date()
        try:
            note = self.get_queryset().get(date=today)
            serializer = self.get_serializer(note)
            return Response(serializer.data)
        except Note.DoesNotExist:
            return Response(
                {"detail": "No note for today"}, status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=["post", "put"])
    def update_today(self, request):
        """Create or update today's note."""
        today = get_working_day_date()
        note, created = Note.objects.get_or_create(
            creator=request.user, date=today, defaults={"content": ""}
        )

        serializer = self.get_serializer(note, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class IntentionsDraftViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing intentions drafts.

    Drafts are temporary text content for planning intentions,
    one per user per day.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = IntentionsDraftSerializer
    filterset_fields = ["date"]
    ordering_fields = ["date", "created_datetime"]
    ordering = ["-date"]

    def get_queryset(self):
        """Filter drafts to only show the current user's drafts."""
        return IntentionsDraft.objects.filter(creator=self.request.user)

    def perform_create(self, serializer):
        """Set the creator to the current user when creating."""
        serializer.save(creator=self.request.user)

    @action(detail=False, methods=["get"])
    def today(self, request):
        """Get today's draft if it exists."""
        today = get_working_day_date()
        try:
            draft = self.get_queryset().get(date=today)
            serializer = self.get_serializer(draft)
            return Response(serializer.data)
        except IntentionsDraft.DoesNotExist:
            return Response(
                {"detail": "No draft for today"}, status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=["post", "put"])
    def update_today(self, request):
        """Create or update today's draft."""
        today = get_working_day_date()
        draft, created = IntentionsDraft.objects.get_or_create(
            creator=request.user, date=today, defaults={"content": ""}
        )

        serializer = self.get_serializer(draft, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class RecurringIntentionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing recurring intention patterns.

    Recurring intentions automatically generate intentions based on
    frequency patterns (daily, weekly, monthly, yearly).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = RecurringIntentionSerializer
    filterset_fields = ["is_active", "frequency"]
    ordering_fields = ["created_datetime", "title"]
    ordering = ["-created_datetime"]

    def get_queryset(self):
        """Filter recurring intentions to only show the current user's patterns."""
        return RecurringIntention.objects.filter(creator=self.request.user)

    def perform_create(self, serializer):
        """Set the creator to the current user when creating."""
        serializer.save(creator=self.request.user)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Deactivate a recurring intention pattern."""
        recurring = self.get_object()
        recurring.is_active = False
        recurring.save(update_fields=["is_active"])
        serializer = self.get_serializer(recurring)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a recurring intention pattern."""
        recurring = self.get_object()
        recurring.is_active = True
        recurring.save(update_fields=["is_active"])
        serializer = self.get_serializer(recurring)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def generate_for_date(self, request, pk=None):
        """
        Manually generate an intention for a specific date.

        Expected payload: {"date": "2026-01-24"}
        """
        recurring = self.get_object()
        date_str = request.data.get("date")

        if not date_str:
            return Response(
                {"error": "Date is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from datetime import datetime

            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        intention = recurring.generate_intention_for_date(target_date)

        if intention:
            return Response(
                {
                    "message": "Intention generated successfully",
                    "intention_id": intention.id,
                }
            )
        else:
            should_generate, reason = recurring.should_generate_for_date(target_date)
            return Response(
                {
                    "message": "No intention generated",
                    "reason": reason,
                    "should_generate": should_generate,
                },
                status=status.HTTP_200_OK,
            )
