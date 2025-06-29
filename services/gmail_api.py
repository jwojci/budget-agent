import os
import base64
import datetime
import re

from loguru import logger
from googleapiclient.errors import HttpError

import config


class GmailService:
    """
    Provides an interface for interacting with the Gmail API.
    Handles fetching email IDs and saving attachments.
    """

    def __init__(self, gmail_api_client):
        self.gmail_api_client = gmail_api_client
        if not os.path.exists(config.ATTACHMENTS_DIR):
            os.makedirs(config.ATTACHMENTS_DIR)

    def get_email_ids_for_current_month(self) -> list[str]:
        """Fetches all email IDs from the specified sender for the current month."""
        try:
            today = datetime.datetime.now()
            first_day_of_month = today.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            after_date = first_day_of_month.strftime("%Y/%m/%d")

            query = f"from:{config.EMAIL_SENDER} after:{after_date}"
            logger.info(f"Searching for emails with query: '{query}'")

            messages = []
            response = (
                self.gmail_api_client.users()
                .messages()
                .list(userId="me", q=query)
                .execute()
            )
            messages.extend(response.get("messages", []))

            while "nextPageToken" in response:
                page_token = response["nextPageToken"]
                response = (
                    self.gmail_api_client.users()
                    .messages()
                    .list(userId="me", q=query, pageToken=page_token)
                    .execute()
                )
                messages.extend(response.get("messages", []))

            if not messages:
                logger.info(
                    f"No new emails from '{config.EMAIL_SENDER}' found for the current month."
                )
                return []
            return [msg["id"] for msg in messages]
        except HttpError as error:
            logger.error(f"An HTTP error occurred searching for emails: {error}")
            return []
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching email IDs: {e}")
            return []

    def save_attachments_from_message(self, msg_id: str) -> str | None:
        """
        Finds the specific HTML attachment from an email, saves it, and returns the path.
        """
        if not msg_id:
            return None
        try:
            msg = (
                self.gmail_api_client.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            def find_html_attachments_parts(parts):
                attachments = []
                for part in parts:
                    if part.get("parts"):
                        attachments.extend(find_html_attachments_parts(part["parts"]))
                    elif (
                        part.get("filename")
                        and "Powiadomienie e-mail z " in part.get("filename")
                        and part.get("filename").endswith(".htm")
                    ):
                        attachments.append(part)
                return attachments

            payload_parts = msg["payload"].get("parts", [])
            html_attachments = find_html_attachments_parts(payload_parts)

            if not html_attachments:
                logger.warning(
                    f"No suitable '.htm' attachment found in email ID: {msg_id}."
                )
                return None

            # There's only one and should be only one html attachment
            part = html_attachments[0]
            filename = part.get("filename")
            attachment_id = part.get("body", {}).get("attachmentId")

            if attachment_id:
                attachment = (
                    self.gmail_api_client.users()
                    .messages()
                    .attachments()
                    .get(userId="me", messageId=msg_id, id=attachment_id)
                    .execute()
                )
                file_data = base64.urlsafe_b64decode(attachment["data"].encode("UTF-8"))
                cleaned_filename = filename.replace("Powiadomienie e-mail z ", "")
                filepath = os.path.join(config.ATTACHMENTS_DIR, cleaned_filename)
                if os.path.exists(filepath):
                    logger.info(f"Skipping attachment {filepath} File exists")
                else:
                    with open(filepath, "wb") as f:
                        f.write(file_data)
                    logger.info(f"Saved attachment: {cleaned_filename}")
                return filepath
            return None
        except HttpError as error:
            logger.error(
                f"An HTTP error occurred fetching message or attachment for ID {msg_id}: {error}",
                exc_info=True,
            )
            return None
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while saving attachment for ID {msg_id}: {e}",
                exc_info=True,
            )
            return None
