"""
Authentication views for mobile OAuth.
"""
import os

from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from intentions_page.users.models import User


class GoogleAuthView(APIView):
    """
    Exchange a Google ID token for a Django REST Framework auth token.

    This endpoint is used by mobile apps that implement Google Sign-In.
    The mobile app obtains an ID token from Google, then sends it here
    to get a Django auth token for subsequent API requests.
    """

    permission_classes = [AllowAny]

    def get_valid_client_ids(self):
        """Get all valid Google OAuth client IDs (web + iOS)."""
        client_ids = []

        # Web client ID from allauth settings
        web_client_id = getattr(settings, "SOCIALACCOUNT_PROVIDERS", {}).get(
            "google", {}
        ).get("APP", {}).get("client_id")
        if web_client_id:
            client_ids.append(web_client_id)

        # iOS client ID from environment
        ios_client_id = os.environ.get("GOOGLE_OAUTH_IOS_CLIENT_ID")
        if ios_client_id:
            client_ids.append(ios_client_id)

        return client_ids

    def verify_token_with_clients(self, id_token_str, client_ids):
        """Try to verify token against each client ID until one succeeds."""
        last_error = None

        for client_id in client_ids:
            try:
                return id_token.verify_oauth2_token(
                    id_token_str,
                    google_requests.Request(),
                    client_id,
                )
            except ValueError as e:
                last_error = e
                continue

        # If we get here, none of the client IDs worked
        raise last_error or ValueError("No valid client IDs configured")

    def post(self, request):
        """
        Exchange Google ID token for DRF auth token.

        Expected payload:
        {
            "id_token": "eyJhbGciOiJSUzI1NiIs..."
        }

        Returns:
        {
            "token": "abc123...",
            "user": {
                "id": 1,
                "email": "user@example.com",
                "name": "User Name"
            }
        }
        """
        id_token_str = request.data.get("id_token")

        if not id_token_str:
            return Response(
                {"error": "id_token is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get all valid Google OAuth client IDs
        client_ids = self.get_valid_client_ids()

        if not client_ids:
            return Response(
                {"error": "Google OAuth is not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            # Verify the ID token with Google (tries each client ID)
            idinfo = self.verify_token_with_clients(id_token_str, client_ids)

            # Get user info from the verified token
            email = idinfo.get("email")
            email_verified = idinfo.get("email_verified", False)
            name = idinfo.get("name", "")
            given_name = idinfo.get("given_name", "")
            family_name = idinfo.get("family_name", "")

            if not email:
                return Response(
                    {"error": "Email not provided by Google"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not email_verified:
                return Response(
                    {"error": "Email not verified by Google"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Find or create the user
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "name": name or f"{given_name} {family_name}".strip(),
                },
            )

            # Update name if it was empty and we now have one
            if not user.name and name:
                user.name = name
                user.save(update_fields=["name"])

            # Get or create an auth token for this user
            token, _ = Token.objects.get_or_create(user=user)

            return Response({
                "token": token.key,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                },
            })

        except ValueError as e:
            # Token verification failed
            return Response(
                {"error": f"Invalid token: {str(e)}"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
