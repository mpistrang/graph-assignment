"""LLM prompts for classification and analysis."""

CLASSIFY_ISSUE_PROMPT = """You are a support ticket classifier. Analyze the following support ticket and classify it.

TICKET:
Subject: {subject}
Body: {body}

Classify this ticket into ONE of these categories:
- "frontend": UI issues, display problems, client-side errors, browser issues, CSS/styling, React/JS errors
- "backend": API errors, server issues, database problems, authentication, data not saving, 500 errors
- "infra": Deployment issues, downtime, performance/latency, infrastructure, DevOps
- "unclear": Cannot determine from the description, could be multiple areas

Respond with ONLY a JSON object in this exact format:
{{"issue_type": "<category>", "reasoning": "<brief explanation>"}}
"""

ANALYZE_CORRELATION_PROMPT = """You are analyzing whether a support ticket is related to recent code changes or deployed features.

SUPPORT TICKET:
Subject: {ticket_subject}
Body: {ticket_body}

RECENT GITHUB PRs (merged to main):
{prs_summary}

RECENT LINEAR TICKETS (deployed to production):
{linear_summary}

RECENT INTERCOM TICKETS (for pattern detection):
{intercom_summary}

Analyze:
1. Is this ticket likely related to any of the recent PRs or Linear tickets?
2. Is this a recurring issue (similar to other recent Intercom tickets)?

Consider:
- Timing: Did the issue start around when changes were deployed?
- Keywords: Do ticket keywords match PR/Linear ticket titles or descriptions?
- Scope: Does the affected area match the changed components?

Respond with ONLY a JSON object in this exact format:
{{
    "correlated": true/false,
    "confidence": 0.0-1.0,
    "correlation_type": "github_pr" | "linear_ticket" | "none",
    "matched_item": {{"type": "pr|linear|none", "title": "<title if matched>", "id": "<id if matched>"}} | null,
    "reason": "<explanation>",
    "is_recurring": true/false,
    "related_tickets": ["<ticket_id>", ...] | [],
    "pattern_summary": "<description of recurring pattern if any>" | null
}}
"""

GENERATE_RECOMMENDATION_PROMPT = """You are a support ticket triage assistant. Based on the analysis below, recommend a next action.

TICKET:
Subject: {ticket_subject}
Body: {ticket_body}

ANALYSIS:
- Issue type: {issue_type}
- Correlated to recent change: {correlated} (confidence: {confidence})
- Matched item: {matched_item}
- Correlation reason: {reason}
- Is recurring pattern: {is_recurring}
- Related tickets: {related_tickets}

Choose ONE next_action:
- "escalate": Bug correlates to recent code change or is a recurring pattern
- "get_more_info": Need more details from customer to diagnose
- "reproduce": Support should try to reproduce before escalating

Respond with ONLY valid JSON (no other text):
{{
    "next_action": "escalate",
    "next_action_reason": "Brief explanation of why this action was chosen",
    "suggested_tags": ["tag1", "tag2"],
    "correlation_summary": "Summary of correlation findings",
    "questions_for_customer": ["Question 1?", "Question 2?"],
    "engineering_context": "Relevant context for engineering team if escalating"
}}

Notes:
- questions_for_customer: Include if next_action is "get_more_info", otherwise use null or empty list
- engineering_context: Include if next_action is "escalate", otherwise use null
"""
