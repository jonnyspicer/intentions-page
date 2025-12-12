#!/usr/bin/env python3
import os
import sys
import json
from anthropic import Anthropic

def main():
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    with open('pr_diff.txt', 'r') as f:
        diff_content = f.read()

    if not diff_content.strip():
        print("No diff content to review")
        sys.exit(0)

    prompt = f"""You are a senior software engineer reviewing a pull request for a Django application.

Context:
- Django 3.1.8 application
- LLM-powered chat interface using Claude API
- Tool calling framework for agent capabilities
- Bootstrap 4 frontend with dark mode
- PostgreSQL/SQLite database

Focus areas:
1. Code quality and best practices
2. Security vulnerabilities (CSRF, SQL injection, XSS, prompt injection)
3. Performance issues
4. Django-specific patterns and ORM usage
5. Python style (PEP 8)
6. Potential bugs and edge cases
7. Tool execution security
8. API rate limiting considerations

Please review the following diff and provide:
- Summary of changes
- Security concerns (if any)
- Code quality issues (if any)
- Suggestions for improvement
- Overall assessment (APPROVE/REQUEST_CHANGES/COMMENT)

Format your response as a GitHub PR review comment in Markdown.

Diff:
```diff
{diff_content}
```"""

    client = Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )

    review_text = message.content[0].text

    with open('review_output.txt', 'w') as f:
        f.write(review_text)

    print("Review generated successfully")

if __name__ == '__main__':
    main()
