from django.conf import settings
from anthropic import Anthropic
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

class LLMService:
    """
    Service for interacting with LLM providers (Claude & OpenAI).
    Supports primary provider with fallback.
    """

    def __init__(self):
        self.primary_provider = settings.LLM_PRIMARY_PROVIDER
        self.fallback_enabled = settings.LLM_FALLBACK_ENABLED

        # Initialize clients
        try:
            if settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY != 'your_claude_api_key_here':
                self.anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            else:
                self.anthropic_client = None
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            self.anthropic_client = None

        try:
            if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != 'your_openai_api_key_here':
                self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
            else:
                self.openai_client = None
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            self.openai_client = None

    def get_completion(self, messages, intentions_context=None):
        """
        Get completion from LLM with fallback support.

        Args:
            messages: List of dicts with 'role' and 'content' keys
            intentions_context: Optional string with user's intentions

        Returns:
            Tuple of (response_text, provider_used)
        """
        # Check if any clients are available
        if not self.anthropic_client and not self.openai_client:
            raise ValueError(
                "No LLM clients available. Please configure ANTHROPIC_API_KEY or OPENAI_API_KEY in your .env file."
            )

        # Add system message with intentions context if provided
        if intentions_context:
            system_message = self._build_system_message(intentions_context)
            messages = [system_message] + messages

        # Try primary provider
        try:
            if self.primary_provider == 'claude':
                return self._get_claude_completion(messages), 'claude'
            elif self.primary_provider == 'openai':
                return self._get_openai_completion(messages), 'openai'
        except Exception as e:
            logger.error(f"Primary provider ({self.primary_provider}) failed: {e}")

            # Try fallback if enabled
            if self.fallback_enabled:
                fallback_provider = 'openai' if self.primary_provider == 'claude' else 'claude'
                try:
                    if fallback_provider == 'claude':
                        return self._get_claude_completion(messages), 'claude'
                    else:
                        return self._get_openai_completion(messages), 'openai'
                except Exception as fallback_error:
                    logger.error(f"Fallback provider ({fallback_provider}) also failed: {fallback_error}")
                    raise Exception("All LLM providers failed")
            else:
                raise

    def _build_system_message(self, intentions_context):
        """Build system message with user's intentions context."""
        return {
            'role': 'system',
            'content': f"""You are a helpful assistant for an intentions tracking application.

The user's current intentions are:
{intentions_context}

Help them prioritize tasks, break down complex intentions, suggest time management strategies, and identify dependencies between tasks. Be concise and actionable."""
        }

    def _get_claude_completion(self, messages):
        """Get completion from Claude API."""
        if not self.anthropic_client:
            raise Exception("Claude API key not configured")

        # Claude API requires system message to be separate
        system_content = None
        api_messages = []

        for msg in messages:
            if msg['role'] == 'system':
                system_content = msg['content']
            else:
                api_messages.append(msg)

        response = self.anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=settings.LLM_MAX_TOKENS_PER_REQUEST,
            system=system_content,
            messages=api_messages
        )

        return response.content[0].text

    def _get_openai_completion(self, messages):
        """Get completion from OpenAI API."""
        if not self.openai_client:
            raise Exception("OpenAI API key not configured")

        response = self.openai_client.chat.completions.create(
            model="gpt-4",
            max_tokens=settings.LLM_MAX_TOKENS_PER_REQUEST,
            messages=messages
        )

        return response.choices[0].message.content
