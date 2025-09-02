from loguru import logger

from .parsers.mbank_parser import MBankParser
from .parsers.base_parser import BaseParser


ALL_PARSERS = [
    MBankParser,
]


def get_parser(email_sender: str) -> BaseParser | None:
    """
    Factory function that returns an instance of the correct parser
    based on the email sender's name.
    """
    for parser_class in ALL_PARSERS:
        if parser_class.get_sender_name().lower() in email_sender.lower():
            logger.info(
                f"Selected '{parser_class.get_sender_name()}' parser for sender '{email_sender}'."
            )
            return parser_class()  # Return an instance of the class

    logger.warning(f"No suitable parser found for sender: '{email_sender}'.")
    return None
