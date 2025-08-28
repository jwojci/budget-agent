# /budget-1.0/data_processing/parsers/mbank_parser.py

import os
import re
from loguru import logger
from bs4 import BeautifulSoup
from typing import List, Tuple, Dict, Set
from .base_parser import BaseParser


class MBankParser(BaseParser):
    """Parses mBank HTML email statements for transactions."""

    @staticmethod
    def get_sender_name() -> str:
        """Returns the bank name."""
        return "mBank"

    def parse_html(self, file_path: str) -> List[Dict[str, str]]:
        """Parses transaction data (time and description) from HTML file."""
        if not file_path or not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return []

        try:
            with open(file_path, "r", encoding="iso-8859-2") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
            tables = soup.find_all("table", border="1")
            if not tables:
                return []

            data_rows = []
            for row in tables[0].find_all("tr")[1:]:
                cols = row.find_all("td")
                if len(cols) == 2:
                    data_rows.append(
                        {
                            "time": cols[0].get_text(strip=True),
                            "description": cols[1].get_text(strip=True),
                        }
                    )
            return data_rows
        except Exception as e:
            logger.error(f"Error parsing mBank HTML file '{file_path}': {e}")
            return []

    def process_transactions(
        self,
        raw_transactions: List[Dict[str, str]],
        file_date_str: str,
        existing_dates: Set[str],
        category_map_records: List[Dict[str, str]],
    ) -> Tuple[List[List], List[str]]:
        """Processes transactions into spreadsheet rows and identifies new keywords."""
        if not raw_transactions:
            return [], []

        date_header = os.path.basename(file_date_str).replace(".htm", "")
        if date_header in existing_dates:
            logger.info(f"Data for {date_header} already processed.")
            return [], []

        rows, new_keywords = [], set()
        keyword_to_details = {
            rec.get("Keyword", "").lower(): (
                rec.get("Category", "Other"),
                rec.get("Type", "Unclassified"),
            )
            for rec in category_map_records
            if rec.get("Keyword")
        }

        for tx in raw_transactions:
            time_str, desc = tx["time"], tx["description"]
            if "Obciazenie rach." in desc:
                continue

            # Extract keyword
            keyword = ""
            if match := re.search(r"Autoryzacja karty.*?:(.*?)\.\s*Kwota:", desc):
                keyword = match.group(1).strip()
            elif match := re.search(r"tytulem:(.*?);", desc):
                keyword = match.group(1).strip()
            else:
                keyword = desc

            keyword = re.sub(
                r"\s*(?:/.*|K\.\d.*|-\s*)", "", keyword.replace("...", "")
            ).strip()

            # Extract amounts
            expense, income, balance = 0.0, 0.0, 0.0
            display_desc = desc

            if match := re.search(r"Przelew przych.*?kwota ([\d,.]+) PLN", desc):
                income = float(match.group(1).replace(",", "."))
                display_desc = "Income: " + (
                    re.search(r"od (.*?);", desc).group(1).strip()
                    if re.search(r"od (.*?);", desc)
                    else "Unknown"
                )
            elif match := re.search(
                r"Kwota: ([\d,.]+) PLN|Przelew wych.*?kwota ([\d,.]+) PLN|na kwote ([\d,.]+) PLN",
                desc,
            ):
                expense = float(next(g for g in match.groups() if g).replace(",", "."))
                display_desc = desc.split("Kwota:")[0].split(":", 1)[-1].strip()
            else:
                continue

            if match := re.search(r"Dostepne: ([\d,.]+) PLN|Dost. ([\d,.]+)", desc):
                balance = float(next(g for g in match.groups() if g).replace(",", "."))

            # Categorize
            category, type_ = keyword_to_details.get(
                keyword.lower(), ("Other", "Unclassified")
            )
            if category == "Other":
                for kw, (cat, typ) in keyword_to_details.items():
                    if kw in keyword.lower() or kw in desc.lower():
                        category, type_ = cat, typ
                        break
                if keyword and keyword.lower() not in keyword_to_details:
                    new_keywords.add(keyword)

            if expense or income:
                rows.append(
                    [
                        time_str,
                        display_desc,
                        expense,
                        income,
                        balance,
                        date_header,
                        category,
                        type_,
                    ]
                )

        if rows:
            logger.info(f"Processed {len(rows)} transactions for {date_header}.")
        return rows, list(new_keywords)
