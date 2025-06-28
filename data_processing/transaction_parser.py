import os
import re

from loguru import logger
from bs4 import BeautifulSoup


class TransactionParser:
    """
    Parses transaction details from HTML email attachments.
    """

    def parse_expenses_from_html(self, file_path: str) -> list[tuple[str, str]]:
        """Parses expense data (time and description) from the HTML attachment."""
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Attachment file not found at {file_path}")
            return []
        try:
            with open(file_path, "r", encoding="iso-8859-2") as f:
                html = f.read()
            soup = BeautifulSoup(html, "html.parser")
            tables = soup.find_all("table", border="1")
            if not tables:
                logger.warning(f"No data table found in the HTML file: {file_path}.")
                return []
            data_rows = []
            for row in tables[0].find_all("tr")[1:]:  # Skip header row
                cols = row.find_all("td")
                if len(cols) == 2:  # Expecting Time and Description columns
                    time = cols[0].get_text(strip=True)
                    description = cols[1].get_text(strip=True)
                    data_rows.append((time, description))
            logger.info(
                f"Parsed {len(data_rows)} transactions from HTML file: {file_path}"
            )
            return data_rows
        except Exception as e:
            logger.error(
                f"An error occurred while parsing the HTML file '{file_path}': {e}",
                exc_info=True,
            )
            return []

    def extract_and_categorize_transaction_details(
        self,
        expenses_raw: list[tuple[str, str]],
        file_date_str: str,
        existing_dates: set[str],
        category_map_records: list[dict],
    ) -> tuple[list[list], list[str]]:
        """
        Processes raw expenses, assigns Category AND Type, and returns new rows for sheet
        and new keywords found.
        """
        if not expenses_raw:
            return [], []

        # Extract date from filename
        date_header = os.path.basename(file_date_str).replace(".htm", "")
        if date_header in existing_dates:
            logger.info(
                f"Data for {date_header} already exists in sheet. Skipping processing."
            )
            return [], []

        processed_rows = []
        new_keywords_found = set()

        keyword_to_details_map = {
            rec.get("Keyword", "").lower(): (
                rec.get("Category", "Other"),
                rec.get("Type", "Unclassified"),
            )
            for rec in category_map_records
            if rec.get("Keyword")
        }

        for time_str, description in expenses_raw:
            # Skip redundant settlement transactions (specific to mBank)
            if "Obciazenie rach." in description:
                logger.info(
                    f"Skipping redundant settlement transaction: {description[:70]}..."
                )
                continue

            expense, income, balance = 0.0, 0.0, 0.0
            display_desc = description  # Description to be saved to sheet

            # --- Keyword Extraction ---
            potential_keyword = ""
            # Pattern 1: For "Autoryzacja karty" (card authorization)
            match1 = re.search(r"Autoryzacja karty.*?:(.*?)\.\s*Kwota:", description)
            if match1:
                potential_keyword = match1.group(1).strip()
            else:
                # Pattern 2: For "tytulem:" (transaction title)
                match2 = re.search(r"tytulem:(.*?);", description)
                if match2:
                    potential_keyword = match2.group(1).strip()
            if not potential_keyword:
                # Fallback: if no specific keyword pattern, use the entire description for matching
                potential_keyword = description

            # Clean up the extracted keyword
            if potential_keyword:
                potential_keyword = potential_keyword.replace("...", "").strip()
                potential_keyword = re.sub(r"\s*/.*", "", potential_keyword).strip()
                potential_keyword = re.sub(r"\sK\.\d.*", "", potential_keyword).strip()
                potential_keyword = re.sub(
                    r"^\s*-\s*", "", potential_keyword
                ).strip()  # Remove leading dash if present

            # --- Amount and Balance Extraction ---
            income_match = re.search(
                r"Przelew przych.*?kwota ([\d,.]+) PLN", description
            )
            amount_match = re.search(
                r"Kwota: ([\d,.]+) PLN|Przelew wych.*?kwota ([\d,.]+) PLN|na kwote ([\d,.]+) PLN",
                description,
            )

            if income_match:
                income = float(income_match.group(1).replace(",", "."))
                desc_match = re.search(r"od (.*?);", description)
                display_desc = "Income: " + (
                    desc_match.group(1).strip() if desc_match else "Unknown"
                )
            elif amount_match:
                amount_str = next(g for g in amount_match.groups() if g)
                expense = float(amount_str.replace(",", "."))
                display_desc = description.split("Kwota:")[
                    0
                ].strip()  # Take part before "Kwota:"
                if display_desc.startswith("mBank:"):
                    display_desc = display_desc.split(":", 1)[1].strip()
                if "Autoryzacja karty" in display_desc:
                    display_desc = display_desc.split(":", 1)[
                        -1
                    ].strip()  # Take part after last colon
            else:
                # If no income or expense amount, skip this transaction
                logger.debug(
                    f"Skipping transaction with no recognizable amount: {description[:100]}..."
                )
                continue

            balance_match = re.search(
                r"Dostepne: ([\d,.]+) PLN|Dost. ([\d,.]+)", description
            )
            if balance_match:
                balance_str = next(g for g in balance_match.groups() if g)
                balance = float(balance_str.replace(",", "."))

            # --- Categorization Logic ---
            assigned_category = "Other"
            assigned_type = "Unclassified"

            # Try to match cleaned potential_keyword first
            matched_details = keyword_to_details_map.get(potential_keyword.lower())
            if matched_details:
                assigned_category, assigned_type = matched_details
            else:
                # Fallback: check if any keyword from category_map is IN the potential keyword or description
                # This is less precise but catches variations
                for kw_in_map, (cat, typ) in keyword_to_details_map.items():
                    if (
                        kw_in_map in potential_keyword.lower()
                        or kw_in_map in description.lower()
                    ):
                        assigned_category = cat
                        assigned_type = typ
                        break

            # If still "Other" and we extracted a solid potential_keyword, add it for user review
            if (
                assigned_category == "Other"
                and potential_keyword
                and potential_keyword.lower() not in keyword_to_details_map
            ):
                new_keywords_found.add(potential_keyword)

            if expense > 0 or income > 0:  # Only add if it's an actual transaction
                processed_rows.append(
                    [
                        time_str,
                        display_desc,  # Use the cleaned description for the sheet
                        expense,
                        income,
                        balance,
                        date_header,  # YYYY-MM-DD from filename
                        assigned_category,
                        assigned_type,
                    ]
                )

        if processed_rows:
            logger.info(
                f"Processed {len(processed_rows)} new transactions for date: {date_header}."
            )
        return processed_rows, list(new_keywords_found)
