from django.conf import settings
from anthropic import Anthropic
from openai import OpenAI
import logging
import json

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
                response = self._get_claude_completion(messages)
                # Extract text from structured response for backward compatibility
                text = response['content'][0].text if isinstance(response, dict) else response
                return text, 'claude'
            elif self.primary_provider == 'openai':
                return self._get_openai_completion(messages), 'openai'
        except Exception as e:
            logger.error(f"Primary provider ({self.primary_provider}) failed: {e}")

            # Try fallback if enabled
            if self.fallback_enabled:
                fallback_provider = 'openai' if self.primary_provider == 'claude' else 'claude'
                try:
                    if fallback_provider == 'claude':
                        response = self._get_claude_completion(messages)
                        text = response['content'][0].text if isinstance(response, dict) else response
                        return text, 'claude'
                    else:
                        return self._get_openai_completion(messages), 'openai'
                except Exception as fallback_error:
                    logger.error(f"Fallback provider ({fallback_provider}) also failed: {fallback_error}")
                    raise Exception("All LLM providers failed")
            else:
                raise

    def get_completion_with_tools(self, messages, intentions_context=None, user=None):
        """
        Get completion with tool calling support.
        Handles loop: LLM → tool use → execute → result → LLM → response

        Args:
            messages: Conversation history
            intentions_context: User's intentions context
            user: Django User object for tool execution

        Returns:
            Tuple of (final_response_dict, provider_used)
        """
        from intentions_page.tools import get_available_tools, ToolExecutor

        # Build system message
        system_msg = self._build_system_message(intentions_context, tools_available=True)
        conversation = [system_msg] + messages

        # Get available tools
        tools = get_available_tools()

        # Initialize tool executor
        tool_executor = ToolExecutor(user=user)

        # Tool calling loop (max 5 iterations)
        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            try:
                # Call Claude with tools
                response = self._get_claude_completion(conversation, tools=tools)

                # Check stop reason
                if response['stop_reason'] == 'end_turn':
                    # No tool use, extract text and return
                    text_content = ""
                    for block in response['content']:
                        if hasattr(block, 'text'):
                            text_content += block.text

                    return {
                        'content': text_content,
                        'content_blocks': [{'type': 'text', 'text': text_content}],
                        'tool_executions': tool_executor.execution_log
                    }, 'claude'

                elif response['stop_reason'] == 'tool_use':
                    # Extract text and tool use blocks
                    assistant_content = []
                    tool_uses = []

                    for block in response['content']:
                        if hasattr(block, 'text'):
                            assistant_content.append({'type': 'text', 'text': block.text})
                        elif hasattr(block, 'name'):  # Tool use block
                            tool_uses.append({
                                'type': 'tool_use',
                                'id': block.id,
                                'name': block.name,
                                'input': block.input
                            })
                            assistant_content.append({
                                'type': 'tool_use',
                                'id': block.id,
                                'name': block.name,
                                'input': block.input
                            })

                    # Add assistant message to conversation
                    conversation.append({
                        'role': 'assistant',
                        'content': assistant_content
                    })

                    # Execute tools and build results
                    tool_results = []
                    for tool_use in tool_uses:
                        result = tool_executor.execute(tool_use['name'], tool_use['input'])

                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': tool_use['id'],
                            'content': json.dumps(result['result']) if result['success'] else result['error'],
                            'is_error': not result['success']
                        })

                    # Add tool results to conversation
                    conversation.append({
                        'role': 'user',
                        'content': tool_results
                    })

                    # Continue loop to get final response
                    continue

                else:
                    # Unexpected stop reason
                    logger.warning(f"Unexpected stop_reason: {response['stop_reason']}")
                    break

            except Exception as e:
                logger.error(f"Error in tool calling loop: {e}", exc_info=True)
                return {
                    'content': f"I encountered an error: {str(e)}",
                    'content_blocks': [{'type': 'text', 'text': f"I encountered an error: {str(e)}"}],
                    'tool_executions': tool_executor.execution_log
                }, 'claude'

        # Max iterations reached
        logger.warning(f"Tool calling loop exceeded max iterations ({max_iterations})")
        return {
            'content': "I apologize, but I reached the maximum number of tool executions for this request.",
            'content_blocks': [{'type': 'text', 'text': "I apologize, but I reached the maximum number of tool executions."}],
            'tool_executions': tool_executor.execution_log
        }, 'claude'

    def _build_system_message(self, intentions_context, tools_available=False):
        """Build system message with user's intentions context and tool instructions."""
        base_message = f"""You are a helpful assistant for an intentions tracking application.

The user's current intentions are:
{intentions_context}

Help them prioritize tasks, break down complex intentions, suggest time management strategies, and identify dependencies between tasks. Be concise and actionable."""

        if tools_available:
            base_message += """

You have access to these tools:
1. 'create_intention' - Create a new intention/task
2. 'update_intention_status' - Update status of an intention (mark completed, sticky, froggy, anxiety-inducing, neverminded)
3. 'reorder_intentions' - Reorder intentions by priority
4. 'list_intentions' - List all intentions for a date with optional status filtering
5. 'get_intention_details' - Get detailed information about a specific intention by ID

Guidelines:
- Only use tools when explicitly or implicitly requested
- For general questions, respond normally without tools
- When creating a "frog" (most important task), remember only one per day is allowed
- When updating status or reordering, use the intention IDs shown in parentheses (e.g., "ID: 123")
- Use 'list_intentions' to see what intentions exist before updating or reordering them
- After using a tool, briefly confirm what was done
- IMPORTANT: When creating a new intention, do NOT provide a date parameter unless the user explicitly specifies a different date. Let it default to today's date automatically.
- Status fields: 'completed' (task done), 'neverminded' (gave up on task), 'sticky' (carry forward), 'froggy' (most important), 'anxiety_inducing' (causes stress)"""

        return {
            'role': 'system',
            'content': base_message
        }

    def _get_claude_completion(self, messages, tools=None):
        """Get completion from Claude API with optional tool support."""
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

        # Build API call parameters
        api_params = {
            'model': "claude-sonnet-4-5-20250929",
            'max_tokens': settings.LLM_MAX_TOKENS_PER_REQUEST,
            'messages': api_messages
        }

        if system_content:
            api_params['system'] = system_content

        if tools:
            api_params['tools'] = tools

        response = self.anthropic_client.messages.create(**api_params)

        # Return structured response instead of just text
        return {
            'content': response.content,
            'stop_reason': response.stop_reason,
            'usage': response.usage
        }

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
