from rest_framework import serializers

from intentions_page.models import (
    Intention,
    IntentionsDraft,
    Note,
    RecurringIntention,
)


class IntentionSerializer(serializers.ModelSerializer):
    """Serializer for Intention model with read/write support."""

    status = serializers.SerializerMethodField()
    is_recurring = serializers.ReadOnlyField()

    class Meta:
        model = Intention
        fields = [
            "id",
            "title",
            "date",
            "created_datetime",
            "order",
            "completed",
            "neverminded",
            "sticky",
            "froggy",
            "anxiety_inducing",
            "status",
            "is_recurring",
            "recurring_intention",
        ]
        read_only_fields = ["id", "created_datetime", "creator"]

    def get_status(self, obj):
        """Get the status of the intention (completed, neverminded, or active)."""
        return obj.get_status()

    def validate(self, data):
        """
        Validate intention data:
        - Only one froggy intention per day per user
        """
        request = self.context.get("request")
        if not request:
            return data

        # Check froggy constraint
        if data.get("froggy", False):
            date = data.get("date") or (self.instance.date if self.instance else None)
            if date:
                existing_frog = Intention.objects.filter(
                    creator=request.user, date=date, froggy=True
                )
                # Exclude current instance if updating
                if self.instance:
                    existing_frog = existing_frog.exclude(id=self.instance.id)

                if existing_frog.exists():
                    raise serializers.ValidationError(
                        {"froggy": "Only one froggy intention allowed per day"}
                    )

        return data


class IntentionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing intentions."""

    status = serializers.SerializerMethodField()

    class Meta:
        model = Intention
        fields = [
            "id",
            "title",
            "date",
            "order",
            "completed",
            "neverminded",
            "sticky",
            "froggy",
            "anxiety_inducing",
            "status",
        ]

    def get_status(self, obj):
        return obj.get_status()


class NoteSerializer(serializers.ModelSerializer):
    """Serializer for Note model."""

    class Meta:
        model = Note
        fields = [
            "id",
            "content",
            "date",
            "created_datetime",
            "version",
        ]
        read_only_fields = ["id", "created_datetime", "creator"]


class IntentionsDraftSerializer(serializers.ModelSerializer):
    """Serializer for IntentionsDraft model."""

    class Meta:
        model = IntentionsDraft
        fields = [
            "id",
            "content",
            "date",
            "created_datetime",
            "version",
        ]
        read_only_fields = ["id", "created_datetime", "creator"]


class RecurringIntentionSerializer(serializers.ModelSerializer):
    """Serializer for RecurringIntention model."""

    generated_intentions_count = serializers.SerializerMethodField()

    class Meta:
        model = RecurringIntention
        fields = [
            "id",
            "title",
            "frequency",
            "interval",
            "days_of_week",
            "day_of_month",
            "month",
            "start_date",
            "end_date",
            "is_active",
            "default_sticky",
            "default_froggy",
            "default_anxiety_inducing",
            "created_datetime",
            "last_generated_date",
            "generated_intentions_count",
        ]
        read_only_fields = ["id", "created_datetime", "creator", "last_generated_date"]

    def get_generated_intentions_count(self, obj):
        """Count of intentions generated from this recurring pattern."""
        return obj.generated_intentions.count()

    def validate(self, data):
        """
        Validate recurring intention data based on frequency type.
        """
        frequency = data.get("frequency") or (
            self.instance.frequency if self.instance else None
        )

        if frequency == "weekly":
            if not data.get("days_of_week"):
                raise serializers.ValidationError(
                    {"days_of_week": "Required for weekly frequency"}
                )
            # Validate days_of_week is a list of integers 0-6
            days = data.get("days_of_week", [])
            if not isinstance(days, list) or not all(
                isinstance(d, int) and 0 <= d <= 6 for d in days
            ):
                raise serializers.ValidationError(
                    {
                        "days_of_week": "Must be a list of integers from 0 (Monday) to 6 (Sunday)"
                    }
                )

        elif frequency == "monthly":
            if not data.get("day_of_month"):
                raise serializers.ValidationError(
                    {"day_of_month": "Required for monthly frequency"}
                )
            day = data.get("day_of_month")
            if not (1 <= day <= 31):
                raise serializers.ValidationError(
                    {"day_of_month": "Must be between 1 and 31"}
                )

        elif frequency == "yearly":
            if not data.get("month") or not data.get("day_of_month"):
                raise serializers.ValidationError(
                    {
                        "month": "Required for yearly frequency",
                        "day_of_month": "Required for yearly frequency",
                    }
                )
            month = data.get("month")
            day = data.get("day_of_month")
            if not (1 <= month <= 12):
                raise serializers.ValidationError({"month": "Must be between 1 and 12"})
            if not (1 <= day <= 31):
                raise serializers.ValidationError(
                    {"day_of_month": "Must be between 1 and 31"}
                )

        return data
