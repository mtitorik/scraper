import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from ..models.product_models import ProductRecord, VariantCombination, PricePair, OptionPriceEntry


class WorkbookManager:
    """Manages creation, incremental saving, dynamic columns, and resume loading
    for the 2-sheet output Excel file.
    """

    SHEET_PRODUCTS = "Products"
    SHEET_VARIANTS = "All Variant Combinations"

    def __init__(self, output_path: str):
        self.output_path = Path(output_path).resolve()
        self.records: Dict[str, ProductRecord] = {}  # product_name -> ProductRecord
        self.pending_save_lock_error = False

    def initialize_from_input_names(self, product_names: List[str]):
        """Pre-populates ProductRecord list with 'Pending' status."""
        self.records = {}
        for name in product_names:
            clean = name.strip()
            if clean and clean not in self.records:
                self.records[clean] = ProductRecord(product_name=clean, status="Pending")

    def update_record(self, record: ProductRecord):
        """Updates or adds a ProductRecord in memory."""
        self.records[record.product_name] = record

    def get_record(self, product_name: str) -> Optional[ProductRecord]:
        return self.records.get(product_name)

    def get_all_records(self) -> List[ProductRecord]:
        return list(self.records.values())

    def _determine_columns(self) -> Tuple[List[str], bool]:
        """Dynamically computes all Sheet 1 column headers across all current records.
        Returns (columns_list, has_any_discount).
        """
        # 1. Check if base price has discount anywhere
        has_base_discount = any(
            rec.default_price.has_discount() for rec in self.records.values()
        )

        # 2. Collect max count and discount flags for each option category
        # Category order preference: colour, official/unofficial, region, storage, others
        known_order = ["colour", "official/unofficial", "region", "storage"]
        category_max_counts: Dict[str, int] = {}
        category_has_discount: Dict[str, bool] = {}
        discovered_extra_fields: Set[str] = set()

        for rec in self.records.values():
            for cat, entries in rec.attribute_options.items():
                norm_cat = cat.lower().strip()
                count = len(entries)
                if count > category_max_counts.get(norm_cat, 0):
                    category_max_counts[norm_cat] = count
                if any(e.prices.has_discount() for e in entries):
                    category_has_discount[norm_cat] = True

            for field_name in rec.extra_fields.keys():
                discovered_extra_fields.add(field_name.strip())

        # Sort categories: known_order first, then any other dynamically discovered categories alphabetically
        sorted_cats = [c for c in known_order if c in category_max_counts]
        for c in sorted(category_max_counts.keys()):
            if c not in sorted_cats:
                sorted_cats.append(c)

        # Build column list
        cols = ["Product name", "page link", "Image Folder", "Regular Price"]
        if has_base_discount:
            cols.append("Discounted Price")

        # Add dynamic option columns
        for cat in sorted_cats:
            max_n = category_max_counts[cat]
            has_disc = category_has_discount.get(cat, False)
            for i in range(1, max_n + 1):
                # Header labels: e.g. "colour 1", "colour 1 Regular Price", "colour 1 Discounted Price"
                cols.append(f"{cat} {i}")
                cols.append(f"{cat} {i} Regular Price")
                if has_disc:
                    cols.append(f"{cat} {i} Discounted Price")

        # Single-value extra fields (e.g. Warranty)
        for extra in sorted(discovered_extra_fields):
            cols.append(extra)

        # Final fields
        cols.extend(["specification", "description", "Status"])
        return cols, has_base_discount

    def save_workbook(self) -> bool:
        """Atomically saves current records to the 2-sheet .xlsx file with lock protection."""
        cols, has_base_discount = self._determine_columns()

        wb = openpyxl.Workbook()
        
        # Setup Sheet 1: Products
        ws1 = wb.active
        ws1.title = self.SHEET_PRODUCTS

        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        border_thin = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0"),
        )
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=False)
        align_center = Alignment(horizontal="center", vertical="center")

        ws1.append(cols)
        for col_idx in range(1, len(cols) + 1):
            cell = ws1.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = align_center

        # Write each product record into Sheet 1
        for row_idx, rec in enumerate(self.records.values(), start=2):
            row_data: Dict[str, Any] = {
                "Product name": rec.product_name,
                "page link": rec.get_combined_page_links(),
                "Image Folder": rec.image_folder or "-",
                "Regular Price": rec.default_price.regular_display(),
                "specification": rec.specifications,
                "description": rec.description_html,
                "Status": rec.status,
            }
            if has_base_discount:
                row_data["Discounted Price"] = rec.default_price.discounted_display() or "-"

            # Fill attribute options
            for cat, entries in rec.attribute_options.items():
                norm_cat = cat.lower().strip()
                for i, entry in enumerate(entries, start=1):
                    row_data[f"{norm_cat} {i}"] = entry.label
                    row_data[f"{norm_cat} {i} Regular Price"] = entry.prices.regular_display()
                    row_data[f"{norm_cat} {i} Discounted Price"] = entry.prices.discounted_display() or "-"

            # Fill extra fields
            for k, v in rec.extra_fields.items():
                row_data[k] = v

            # Assemble row cells based on cols
            row_values = []
            for col_name in cols:
                val = row_data.get(col_name)
                if val is None or val == "":
                    # If product is found and field missing -> "not found"
                    val = "not found" if rec.status in ("Done", "Partial") else "-"
                row_values.append(val)

            ws1.append(row_values)

            # Apply styling and local folder hyperlink
            for c_idx, col_name in enumerate(cols, start=1):
                cell = ws1.cell(row=row_idx, column=c_idx)
                cell.border = border_thin
                cell.alignment = align_left

                if col_name == "Image Folder" and rec.image_folder and os.path.exists(rec.image_folder):
                    folder_path = Path(rec.image_folder).as_posix()
                    cell.hyperlink = f"file:///{folder_path}"
                    cell.font = Font(name="Calibri", size=11, color="2563EB", underline="single")

                if col_name == "Status":
                    cell.alignment = align_center
                    if rec.status == "Done":
                        cell.font = Font(name="Calibri", size=11, bold=True, color="16A34A")
                    elif rec.status == "Not Found":
                        cell.font = Font(name="Calibri", size=11, bold=True, color="DC2626")
                    elif rec.status == "In Progress":
                        cell.font = Font(name="Calibri", size=11, bold=True, color="D97706")

        # Adjust column widths automatically
        for col in ws1.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            header_name = str(col[0].value or "")
            if header_name in ("specification", "description"):
                ws1.column_dimensions[col_letter].width = 30
                continue
            for cell in col[:50]:
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws1.column_dimensions[col_letter].width = max(max_len + 3, 14)

        # Atomic write with lock guard
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".xlsx", dir=str(self.output_path.parent))
        os.close(tmp_fd)

        try:
            wb.save(tmp_path)
            # Try atomic replace
            if os.name == "nt":
                # On Windows, replace can fail if target is open in Excel
                if self.output_path.exists():
                    try:
                        os.remove(str(self.output_path))
                    except PermissionError:
                        self.pending_save_lock_error = True
                        print(f"[WorkbookManager] Warning: {self.output_path.name} is locked by another process (e.g. Excel). Changes cached.")
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                        return False
                shutil.move(tmp_path, str(self.output_path))
            else:
                os.replace(tmp_path, str(self.output_path))

            self.pending_save_lock_error = False
            return True
        except PermissionError:
            self.pending_save_lock_error = True
            print(f"[WorkbookManager] File locked: {self.output_path.name}. Changes queued.")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return False
        except Exception as e:
            print(f"[WorkbookManager] Error saving workbook: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return False

    @classmethod
    def load_for_resume(cls, file_path: str) -> "WorkbookManager":
        """Loads an existing output .xlsx file to resume scraping."""
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        manager = cls(str(path))
        wb = openpyxl.load_workbook(str(path), data_only=True)

        # Parse Sheet 1: Products
        if cls.SHEET_PRODUCTS in wb.sheetnames:
            ws1 = wb[cls.SHEET_PRODUCTS]
            headers = [str(cell.value or "").strip() for cell in ws1[1]]
            
            for row in ws1.iter_rows(min_row=2, values_only=True):
                if not row or not any(row):
                    continue
                row_dict = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}
                p_name = str(row_dict.get("Product name") or "").strip()
                if not p_name:
                    continue

                status = str(row_dict.get("Status") or "Pending").strip()
                page_link_raw = str(row_dict.get("page link") or "").strip()
                page_links = [l.strip() for l in page_link_raw.split("|") if l.strip() and l.strip() != "not found"]
                img_folder = str(row_dict.get("Image Folder") or "").strip()
                if img_folder == "-":
                    img_folder = ""

                # Regular & Discounted price
                reg_raw = row_dict.get("Regular Price")
                disc_raw = row_dict.get("Discounted Price")
                reg_val = None
                disc_val = None
                if reg_raw and str(reg_raw).strip() not in ("-", "not found"):
                    try:
                        digits = re.sub(r"[^\d]", "", str(reg_raw))
                        if digits:
                            reg_val = int(digits)
                    except Exception:
                        pass
                if disc_raw and str(disc_raw).strip() not in ("-", "not found"):
                    try:
                        digits = re.sub(r"[^\d]", "", str(disc_raw))
                        if digits:
                            disc_val = int(digits)
                    except Exception:
                        pass

                specs = str(row_dict.get("specification") or "not found").strip()
                desc = str(row_dict.get("description") or "not found").strip()

                record = ProductRecord(
                    product_name=p_name,
                    page_links=page_links,
                    image_folder=img_folder,
                    default_price=PricePair(regular=reg_val, discounted=disc_val),
                    specifications=specs,
                    description_html=desc,
                    status=status,
                )
                manager.records[p_name] = record

        # Parse Sheet 2: All Variant Combinations
        if cls.SHEET_VARIANTS in wb.sheetnames:
            ws2 = wb[cls.SHEET_VARIANTS]
            v_headers = [str(cell.value or "").strip() for cell in ws2[1]]
            for row in ws2.iter_rows(min_row=2, values_only=True):
                if not row or not any(row):
                    continue
                v_dict = {v_headers[i]: (row[i] if i < len(row) else None) for i in range(len(v_headers))}
                p_name = str(v_dict.get("Product name") or "").strip()
                if p_name in manager.records:
                    reg_p = v_dict.get("Regular Price")
                    disc_p = v_dict.get("Discounted Price")
                    combo = VariantCombination(
                        product_name=p_name,
                        source_website=str(v_dict.get("Source Website") or "").strip(),
                        page_link=str(v_dict.get("Page Link") or "").strip(),
                        official_type=str(v_dict.get("Official/Unofficial") or "not found").strip(),
                        region=str(v_dict.get("Region") or "not found").strip(),
                        storage=str(v_dict.get("Storage") or "not found").strip(),
                        color=str(v_dict.get("Colour") or "not found").strip(),
                        prices=PricePair(
                            regular=int(reg_p) if isinstance(reg_p, (int, float)) else None,
                            discounted=int(disc_p) if isinstance(disc_p, (int, float)) else None,
                        ),
                        stock_status=str(v_dict.get("Stock Status") or "In Stock").strip(),
                    )
                    manager.records[p_name].variant_combinations.append(combo)

        return manager

    @classmethod
    def read_input_product_names(cls, input_file_path: str) -> List[str]:
        """Reads product names from Column A of the input .xlsx file."""
        path = Path(input_file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")

        wb = openpyxl.load_workbook(str(path), data_only=True)
        ws = wb.active
        names: List[str] = []
        for idx, row in enumerate(ws.iter_rows(values_only=True)):
            if not row or row[0] is None:
                continue
            val = str(row[0]).strip()
            # If row 0 looks like header 'Product Name', skip it
            if idx == 0 and val.lower().replace(" ", "").replace("_", "") in ("productname", "product", "name", "item"):
                continue
            if val and val not in names:
                names.append(val)
        return names
