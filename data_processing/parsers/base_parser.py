from abc import ABC, abstractmethod


class BaseParser(ABC):
    """
    Abstract method for defining the interface for bank statement parsers
    """

    @staticmethod
    @abstractmethod
    def get_sender_name() -> str:
        """Returns the name of the bank or sender this parser handles."""
        pass

    @abstractmethod
    def parse_html(self, file_path: str) -> list[dict[str, str]]:
        """Parses the transaction data from an HTML file"""
        pass

    @abstractmethod
    def process_transactions(
        self,
        raw_transactions: list[dict[str, str]],
        file_data_str: str,
        existing_dates: set[str],
        category_map_records: list[dict[str, str]],
    ) -> tuple[list[list], list[str]]:
        """
        Processes raw transactions into structured rows for the spreadsheet
        and identifies new keywords.
        """
        pass
