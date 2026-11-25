"""
Feedback service for collecting user bug reports and feature requests.

Optionally creates GitHub issues when configured, with graceful
degradation to logging-only mode when GitHub is unavailable.
"""

import logging
from datetime import datetime, timezone

import httpx

from backend.core.config import GitHubSettings, get_github_settings
from backend.schemas.requests import FeedbackCategory, FeedbackContext

logger = logging.getLogger(__name__)


class FeedbackService:
    """Service for handling user feedback submissions."""

    def __init__(self, github_settings: GitHubSettings | None = None):
        self._github = github_settings or get_github_settings()

    def submit_feedback(
        self,
        category: FeedbackCategory,
        title: str,
        description: str,
        user_email: str,
        user_id: str,
        context: FeedbackContext | None = None,
    ) -> dict:
        """
        Submit user feedback, optionally creating a GitHub issue.

        Returns a dict compatible with FeedbackResponse.
        """
        prefix = "Bug Report" if category == FeedbackCategory.BUG else "Feature Request"
        issue_title = f"[{prefix}] {title}"
        issue_body = self._format_issue_body(
            category=category,
            description=description,
            user_email=user_email,
            context=context,
        )
        labels = ["bug"] if category == FeedbackCategory.BUG else ["enhancement"]

        if not self._github.is_configured:
            logger.info(
                "GitHub not configured — logging feedback locally.\nTitle: %s\nBody:\n%s",
                issue_title,
                issue_body,
            )
            return {
                "success": True,
                "issue_url": None,
                "issue_number": None,
                "message": "Feedback recorded. Thank you!",
            }

        try:
            result = self._create_github_issue(issue_title, issue_body, labels)
            return {
                "success": True,
                "issue_url": result["html_url"],
                "issue_number": result["number"],
                "message": "A ticket has been created. Thank you!",
            }
        except Exception:
            logger.exception(
                "Failed to create GitHub issue — logging feedback locally.\nTitle: %s\nBody:\n%s",
                issue_title,
                issue_body,
            )
            return {
                "success": True,
                "issue_url": None,
                "issue_number": None,
                "message": "Feedback recorded. Thank you!",
            }

    def _create_github_issue(self, title: str, body: str, labels: list[str]) -> dict:
        """Create a GitHub issue via the REST API."""
        url = (
            f"https://api.github.com/repos/"
            f"{self._github.repo_owner}/{self._github.repo_name}/issues"
        )
        headers = {
            "Authorization": f"Bearer {self._github.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        payload = {"title": title, "body": body, "labels": labels}

        with httpx.Client(timeout=15) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _format_issue_body(
        category: FeedbackCategory,
        description: str,
        user_email: str,
        context: FeedbackContext | None,
    ) -> str:
        """Build a markdown issue body with context tables."""
        heading = "Bug Report" if category == FeedbackCategory.BUG else "Feature Request"
        now = datetime.now(timezone.utc).isoformat()

        lines = [
            f"## {heading}",
            "",
            f"**Submitted by:** {user_email}",
            f"**Date:** {now}",
            "",
            "### Description",
            description,
        ]

        if context:
            app_rows = []
            if context.current_view:
                app_rows.append(("View", context.current_view))
            if context.workflow_step is not None:
                app_rows.append(("Workflow Step", str(context.workflow_step)))
            if context.current_run_id:
                app_rows.append(("Run ID", f"`{context.current_run_id}`"))
            if context.csv_filename:
                app_rows.append(("CSV Filename", context.csv_filename))
            if context.app_url:
                app_rows.append(("App URL", context.app_url))

            if app_rows:
                lines.extend(
                    [
                        "",
                        "### Application Context",
                        "| Field | Value |",
                        "|-------|-------|",
                    ]
                )
                for field, value in app_rows:
                    lines.append(f"| {field} | {value} |")

            env_rows = []
            if context.browser_user_agent:
                env_rows.append(("User Agent", context.browser_user_agent))
            if context.screen_resolution:
                env_rows.append(("Screen Resolution", context.screen_resolution))

            if env_rows:
                lines.extend(
                    [
                        "",
                        "### Environment",
                        "| Field | Value |",
                        "|-------|-------|",
                    ]
                )
                for field, value in env_rows:
                    lines.append(f"| {field} | {value} |")

        lines.extend(["", "*Automatically created via Syxplain feedback system.*"])
        return "\n".join(lines)
