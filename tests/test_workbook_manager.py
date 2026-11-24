import os
import tempfile
from pathlib import Path
import openpyxl
import pytest

from scraper_app.models.product_models import ProductRecord, PricePair, OptionPriceEntry, VariantCombination
from scraper_app.excel.workbook_manager import WorkbookManager


def test_workbook_initialization_and_immediate_save():
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_output.xlsx"
        manager = WorkbookManager(str(output_path))
        manager.initialize_from_input_names(["iPhone 16 Pro", "Samsung S24 Ultra", "AirPods 4"])

        assert len(manager.records) == 3
        assert manager.records["iPhone 16 Pro"].status == "Pending"

        # Immediate save before scraping starts
        success = manager.save_workbook()
        assert success is True
        assert output_path.exists()

        # Check sheets in output workbook
        wb = openpyxl.load_workbook(str(output_path))
        assert WorkbookManager.SHEET_PRODUCTS in wb.sheetnames
        assert WorkbookManager.SHEET_VARIANTS in wb.sheetnames

        ws1 = wb[WorkbookManager.SHEET_PRODUCTS]
        headers = [c.value for c in ws1[1]]
        assert "Product name" in headers
        assert "Regular Price" in headers
        assert "specification" in headers
        assert "description" in headers
        assert "Status" in headers

        rows = list(ws1.iter_rows(values_only=True))
        assert len(rows) == 4  # 1 header + 3 products
        assert rows[1][0] == "iPhone 16 Pro"
        assert rows[1][-1] == "Pending"


def test_dynamic_columns_and_discounted_price_placement():
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_dynamic.xlsx"
        manager = WorkbookManager(str(output_path))

        # Record with discount and multiple options
        rec = ProductRecord(
            product_name="iPhone 16 Pro",
            image_folder=tmpdir,
            default_price=PricePair(regular=135000, discounted=129000),
            attribute_options={
                "colour": [
                    OptionPriceEntry("Black Titanium", PricePair(135000, 129000)),
                    OptionPriceEntry("Desert Titanium", PricePair(138000, 132000)),
                ],
                "official/unofficial": [
                    OptionPriceEntry("Unofficial", PricePair(135000, 129000)),
                    OptionPriceEntry("Official", PricePair(180000, None)),
                ],
                "region": [
                    OptionPriceEntry("USA", PricePair(135000, 129000)),
                ],
            },
            extra_fields={"Warranty": "1 Year Official Warranty"},
            specifications="Chip: A18 Pro\nRAM: 8GB",
            description_html="<p>Authentic iPhone 16 Pro.</p>",
            status="Done",
        )
        rec.variant_combinations.append(
            VariantCombination(
                product_name="iPhone 16 Pro",
                source_website="https://applegadgetsbd.com",
                official_type="Unofficial",
                region="USA",
                storage="128GB",
                color="Black Titanium",
                prices=PricePair(135000, 129000),
                stock_status="In Stock",
            )
        )
        manager.update_record(rec)
        assert manager.save_workbook() is True

        wb = openpyxl.load_workbook(str(output_path))
        ws1 = wb[WorkbookManager.SHEET_PRODUCTS]
        headers = [c.value for c in ws1[1]]

        # Verify Discounted Price is immediately right of Regular Price
        reg_idx = headers.index("Regular Price")
        assert headers[reg_idx + 1] == "Discounted Price"

        # Verify dynamic option columns are added with Regular and Discounted headers
        assert "colour 1" in headers
        assert "colour 1 Regular Price" in headers
        assert "colour 1 Discounted Price" in headers
        assert "colour 2" in headers
        assert "official/unofficial 1" in headers
        assert "Warranty" in headers

        # Verify local folder hyperlink on Image Folder
        img_col_idx = headers.index("Image Folder") + 1
        img_cell = ws1.cell(row=2, column=img_col_idx)
        assert img_cell.hyperlink is not None
        assert "file:///" in img_cell.hyperlink.target

        # Verify Sheet 2 contains variant combination
        ws2 = wb[WorkbookManager.SHEET_VARIANTS]
        v_rows = list(ws2.iter_rows(values_only=True))
        assert len(v_rows) == 2  # header + 1 combo
        assert v_rows[1][0] == "iPhone 16 Pro"
        assert v_rows[1][3] == "Unofficial"
        assert v_rows[1][4] == "USA"
        assert v_rows[1][6] == "Black Titanium"
        assert v_rows[1][8] == "135000"
        assert v_rows[1][9] == "129000"


def test_resume_from_existing_xlsx():
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_resume.xlsx"
        manager = WorkbookManager(str(output_path))

        rec1 = ProductRecord(
            product_name="iPhone 16 Pro",
            status="Done",
            default_price=PricePair(135000, 129000),
            specifications="A18 Pro",
            description_html="<p>Done product</p>",
        )
        rec2 = ProductRecord(
            product_name="Samsung S24 Ultra",
            status="Pending",
        )
        manager.update_record(rec1)
        manager.update_record(rec2)
        manager.save_workbook()

        # Load for resume
        resumed_manager = WorkbookManager.load_for_resume(str(output_path))
        assert len(resumed_manager.records) == 2
        assert resumed_manager.records["iPhone 16 Pro"].status == "Done"
        assert resumed_manager.records["iPhone 16 Pro"].default_price.regular == 135000
        assert resumed_manager.records["Samsung S24 Ultra"].status == "Pending"
