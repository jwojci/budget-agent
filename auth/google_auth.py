import os.path
from loguru import logger

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import gspread

import config


class GoogleAuthenticator:
    """Manages Google API authentication for Gmail and Google Sheets."""

    def __init__(
        self,
        token_file=config.TOKEN_FILE,
        credentials_file=config.CREDENTIALS_FILE,
        scopes=config.SCOPES,
    ):
        self.token_file = token_file
        self.credentials_file = credentials_file
        self.scopes = scopes
        self._creds = None

    def get_creds(self):
        """Handles user authentication for all Google services."""
        if self._creds and self._creds.valid:
            return self._creds

        if os.path.exists(self.token_file):
            self._creds = Credentials.from_authorized_user_file(
                self.token_file, self.scopes
            )

        if self._creds and self._creds.expired and self._creds.refresh_token:
            try:
                self._creds.refresh(Request())
                logger.info("Google credentials refreshed successfully.")
            except Exception as e:
                logger.error(f"Error refreshing token: {e}. Forcing re-authentication.")
                self._creds = None  # Force full re-auth if refresh fails

        if not self._creds or not self._creds.valid:
            try:
                logger.info(
                    "No valid Google credentials found. Starting new authentication flow."
                )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.scopes
                )
                self._creds = flow.run_local_server(port=0)
                logger.info("New Google credentials obtained successfully.")
            except FileNotFoundError:
                logger.error(
                    f"Credentials file not found at {self.credentials_file}. Please download it from the Google Cloud Console."
                )
                self._creds = None
            except Exception as e:
                logger.error(
                    f"An unexpected error occurred during authentication flow: {e}",
                    exc_info=True,
                )

        if self._creds:
            with open(self.token_file, "w") as token:
                token.write(self._creds.to_json())
        return self._creds

    def get_gmail_service(self):
        """Builds and returns the Gmail service client."""
        creds = self.get_creds()
        if not creds:
            return None
        try:
            service = build("gmail", "v1", credentials=creds)
            logger.info("Gmail service client built successfully.")
            return service
        except HttpError as error:
            logger.error(f"An HTTP error occurred building the Gmail service: {error}")
            return None
        except Exception as e:
            logger.error(
                f"An unexpected error occurred building the Gmail service: {e}"
            )
            return None

    def get_gspread_client(self):
        """Returns an authenticated gspread client for Google Sheets."""
        try:
            # gspread.oauth() manages its own authentication flow
            # needs credentials.json file from Google Cloud in %APPDATA%/gspread
            gc = gspread.oauth(scopes=self.scopes)
            logger.info("gspread client authenticated via OAuth.")
            return gc
        except Exception as e:
            logger.error(f"Failed to authenticate with gspread: {e}", exc_info=True)
            return None
