from __future__ import annotations

import argparse
import csv
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait


HOME_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"
DEFAULT_INPUT_CSV = Path(__file__).resolve().parents[1] / "data" / "missing_files.csv"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "all_verdicts"
VERDICTS_FOLDER_ID = "21"
DECISIONS_FOLDER_ID = "18"
DATE_COLUMN_CANDIDATES = (
    "Date",
    "date",
    "DecisionDate",
    "decision_date",
    "Judgment Date",
    "judgment_date",
    "תאריך",
    "תאריך החלטה",
    "תאריך גזר דין",
)


@dataclass
class VerdictTask:
    row_index: int
    case_number: str
    expected_date: str | None
    document_link: str | None

    @property
    def target_stem(self) -> str:
        if self.document_link:
            parsed = urlparse(self.document_link)
            name = Path(unquote(parsed.path)).name
            if name:
                return sanitize_filename(Path(name).stem)
        return sanitize_filename(self.case_number)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download verdict DOCX files from the public NGCS court site by case number "
            "and decision date, then extract ZIP downloads and rename files by Document Link."
        )
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_INPUT_CSV, help="Input CSV path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Where extracted files are saved.")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode.")
    parser.add_argument("--start-row", type=int, default=0, help="0-based row index to start from.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of rows to process.")
    parser.add_argument("--pause", type=float, default=1.5, help="Base pause between actions.")
    parser.add_argument("--page-timeout", type=int, default=30, help="Timeout for page waits.")
    parser.add_argument("--download-timeout", type=int, default=120, help="Timeout for ZIP/DOCX download completion.")
    return parser.parse_args()


def log(message: str) -> None:
    print(message, flush=True)


def sanitize_filename(value: str | None) -> str:
    if not value:
        return "document"
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value)).strip()
    cleaned = cleaned.rstrip(". ")
    return cleaned or "document"


def normalize_date_str(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    text = text.replace(".", "/").replace("-", "/")
    text = re.sub(r"\s+", " ", text)
    text = text.split(" ")[0]

    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.year < 100:
                dt = dt.replace(year=2000 + dt.year if dt.year < 40 else 1900 + dt.year)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return None


def parse_case_components(case_number: str) -> tuple[str, str]:
    parts = [part.strip() for part in str(case_number).split("-") if part.strip()]
    if len(parts) != 3:
        raise ValueError(
            f"Expected Case Number in format 'number-month-year', got: {case_number!r}"
        )
    case_num, month, year = parts
    if not case_num.isdigit() or not month.isdigit() or not year.isdigit():
        raise ValueError(f"Case Number contains non-digits: {case_number!r}")
    return case_num, f"{month.zfill(2)}-{year.zfill(2)}"


def build_driver(download_dir: Path, headless: bool) -> webdriver.Chrome:
    download_dir.mkdir(parents=True, exist_ok=True)

    options = ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=he-IL")
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")

    prefs = {
        "download.default_directory": str(download_dir.resolve()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "safebrowsing.disable_download_protection": True,
        "download_restrictions": 0,
        "profile.default_content_setting_values.automatic_downloads": 1,
        "plugins.always_open_pdf_externally": True,
        "download.open_pdf_in_system_reader": False,
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    try:
        driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": str(download_dir.resolve())},
        )
    except Exception:
        pass
    return driver


def wait_for_document_ready(driver: webdriver.Chrome, timeout: int) -> None:
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def dismiss_terms_overlay(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    for by, value in (
        (By.ID, "btUploadDocumentsConfirm"),
        (By.CSS_SELECTOR, "a.modal_ReturnMessageClose"),
    ):
        try:
            element = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((by, value)))
            element.click()
            time.sleep(0.4)
            return
        except Exception:
            continue


def ensure_site_is_available(driver: webdriver.Chrome) -> None:
    page = driver.page_source or ""
    if "האתר אינו פעיל בעקבות עבודות שדרוג" in page:
        raise RuntimeError(
            "The NGCS site currently shows a maintenance page. Retry later when the public site is back."
        )


def go_home(driver: webdriver.Chrome, wait: WebDriverWait, timeout: int) -> None:
    try:
        home_link = driver.find_element(By.CSS_SELECTOR, "a[id$='_Header_webbtnGoHome']")
        home_link.click()
    except Exception:
        driver.get(HOME_URL)
    wait_for_document_ready(driver, timeout)
    dismiss_terms_overlay(driver, wait)
    ensure_site_is_available(driver)


def read_tasks(csv_path: Path, start_row: int, limit: int | None) -> list[VerdictTask]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    subset = rows[start_row:] if start_row else rows
    if limit is not None:
        subset = subset[:limit]

    tasks: list[VerdictTask] = []
    for relative_index, row in enumerate(subset, start=start_row):
        case_number = (row.get("Case Number") or "").strip()
        if not case_number:
            continue
        expected_date = None
        for column in DATE_COLUMN_CANDIDATES:
            expected_date = normalize_date_str(row.get(column))
            if expected_date:
                break
        tasks.append(
            VerdictTask(
                row_index=relative_index,
                case_number=case_number,
                expected_date=expected_date,
                document_link=(row.get("Document Link") or "").strip() or None,
            )
        )
    return tasks


def target_already_exists(output_dir: Path, stem: str) -> bool:
    return any(output_dir.glob(f"{stem}.*"))


def clear_and_type(element: WebElement, value: str) -> None:
    element.click()
    element.send_keys(Keys.CONTROL, "a")
    element.send_keys(Keys.DELETE)
    element.send_keys(value)


def search_header_case(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    timeout: int,
    case_number: str,
) -> None:
    case_num, month_year = parse_case_components(case_number)

    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[id$='_BamaMonthYearTextBoxHT']")))
    except TimeoutException:
        driver.get(HOME_URL)
        wait_for_document_ready(driver, timeout)
        dismiss_terms_overlay(driver, wait)

    ensure_site_is_available(driver)

    try:
        radio = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id$='_BamaCaseIdentifierOptionBoxHT']"))
        )
        if not radio.is_selected():
            radio.click()
            time.sleep(0.3)
    except Exception:
        pass

    month_year_box = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id$='_BamaMonthYearTextBoxHT']"))
    )
    case_num_box = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id$='_BamaCaseNumberTextBoxHT']"))
    )
    clear_and_type(month_year_box, month_year)
    clear_and_type(case_num_box, case_num)

    try:
        search_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id$='_SearchHeaderCaseButton']"))
        )
        search_button.click()
    except Exception:
        driver.execute_script("__doPostBack('Header1:CaseLocatorHeaderUC2:SearchHeaderCaseButton','')")

    wait_for_document_ready(driver, timeout)
    time.sleep(2.0)


def open_folder(driver: webdriver.Chrome, wait: WebDriverWait, folder_id: str, timeout: int) -> None:
    try:
        folder_link = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    f"//a[contains(@class,'FolderLink')][contains(@href,'NavigateToFolder') and contains(@href,'{folder_id}')]",
                )
            )
        )
        folder_link.click()
    except Exception:
        driver.execute_script(
            f"__doPostBack('_ctl0$ElectronicCaseFolderTreeView1$NavigateToFolder','{folder_id}')"
        )

    wait_for_document_ready(driver, timeout)
    time.sleep(1.5)


def read_grid_items(driver: webdriver.Chrome) -> list[dict]:
    try:
        store = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "DecisionListGridArrayStore"))
        )
        raw = store.get_attribute("value") or "[]"
        import json

        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def decision_item_matches_date(item: dict, expected_date: str) -> bool:
    for key in ("DecisionSignatureDate", "DecisionDate", "DecisionDisplayDate", "DecisionSignatureDateDisplay"):
        if normalize_date_str(item.get(key)) == expected_date:
            return True
    return False


def decision_item_looks_like_verdict(item: dict) -> bool:
    haystack = " ".join(str(item.get(key, "")) for key in item.keys()).lower()
    return "פסק" in haystack or "גזר" in haystack or "verdict" in haystack


def pick_decision_item(items: list[dict], expected_date: str) -> dict | None:
    dated_matches = [item for item in items if decision_item_matches_date(item, expected_date)]
    if not dated_matches:
        return None
    preferred = [item for item in dated_matches if decision_item_looks_like_verdict(item)]
    return preferred[0] if preferred else dated_matches[0]


def click_row_checkbox_by_date(
    driver: webdriver.Chrome,
    expected_date: str,
) -> bool:
    xpath = f"//div[@id='DecisionListGrid']//tr[.//*[contains(normalize-space(), '{expected_date}')]]"
    try:
        row = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath)))
    except Exception:
        return False

    checkbox_xpaths = (
        ".//input[@type='checkbox']",
        ".//span[contains(@class,'checkbox')]",
        ".//*[contains(@class,'x-grid3-row-checker')]",
    )
    for checkbox_xpath in checkbox_xpaths:
        try:
            checkbox = row.find_element(By.XPATH, checkbox_xpath)
            driver.execute_script("arguments[0].click();", checkbox)
            time.sleep(0.5)
            return True
        except Exception:
            continue
    return False


def click_download_docx_controls(driver: webdriver.Chrome, wait: WebDriverWait) -> bool:
    download_candidates = (
        (By.ID, "btnDownload"),
        (By.XPATH, "//input[contains(@value,'הורד') or contains(@value,'הורדה')]"),
        (By.XPATH, "//button[contains(.,'הורד') or contains(.,'הורדה')]"),
        (By.XPATH, "//a[contains(.,'הורד') or contains(.,'הורדה')]"),
    )
    for locator in download_candidates:
        try:
            button = WebDriverWait(driver, 4).until(EC.element_to_be_clickable(locator))
            driver.execute_script("arguments[0].click();", button)
            time.sleep(0.8)
            break
        except Exception:
            continue

    docx_candidates = (
        (By.XPATH, "//option[contains(., 'DOCX') or contains(., 'Word')]"),
        (By.XPATH, "//a[contains(., 'DOCX') or contains(., 'Word')]"),
        (By.XPATH, "//button[contains(., 'DOCX') or contains(., 'Word')]"),
        (By.XPATH, "//label[contains(., 'DOCX') or contains(., 'Word')]"),
        (By.XPATH, "//input[@type='radio' and (contains(@value,'DOCX') or contains(@value,'Word'))]"),
    )
    for locator in docx_candidates:
        try:
            element = WebDriverWait(driver, 4).until(EC.element_to_be_clickable(locator))
            driver.execute_script("arguments[0].click();", element)
            time.sleep(0.8)
            return True
        except Exception:
            continue
    return False


def ensure_docx_selected_if_possible(driver: webdriver.Chrome) -> None:
    selectors = (
        (By.CSS_SELECTOR, "select"),
        (By.XPATH, "//input[@type='radio']"),
        (By.XPATH, "//label"),
        (By.XPATH, "//a"),
        (By.XPATH, "//button"),
    )
    for by, value in selectors:
        try:
            elements = driver.find_elements(by, value)
        except Exception:
            continue

        for element in elements:
            text = ((element.text or "") + " " + (element.get_attribute("value") or "")).strip()
            if "DOCX" not in text.upper() and "WORD" not in text.upper():
                continue

            try:
                tag = element.tag_name.lower()
                if tag == "select":
                    Select(element).select_by_visible_text(next(
                        option.text for option in element.find_elements(By.TAG_NAME, "option")
                        if "DOCX" in option.text.upper() or "WORD" in option.text.upper()
                    ))
                else:
                    driver.execute_script("arguments[0].click();", element)
                time.sleep(0.5)
                return
            except Exception:
                continue


def wait_for_new_download(download_dir: Path, since_ts: float, timeout: int) -> Path:
    deadline = time.time() + timeout
    latest_candidate: Path | None = None

    while time.time() < deadline:
        partials = list(download_dir.glob("*.crdownload"))
        finished = [path for path in download_dir.iterdir() if path.is_file() and path.stat().st_mtime >= since_ts]
        if finished:
            latest_candidate = max(finished, key=lambda path: path.stat().st_mtime)
            if not partials:
                size1 = latest_candidate.stat().st_size
                time.sleep(1.0)
                size2 = latest_candidate.stat().st_size
                if size1 == size2:
                    return latest_candidate
        time.sleep(0.7)

    if latest_candidate:
        return latest_candidate
    raise TimeoutError(f"No downloaded file appeared in {download_dir} within {timeout} seconds.")


def move_file_with_unique_name(source: Path, target_base: Path) -> Path:
    candidate = target_base.with_suffix(source.suffix)
    counter = 1
    while candidate.exists():
        candidate = target_base.with_name(f"{target_base.name}_{counter}").with_suffix(source.suffix)
        counter += 1
    shutil.move(str(source), str(candidate))
    return candidate


def extract_zip_and_rename(zip_path: Path, target_base: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        if not members:
            raise RuntimeError(f"ZIP file is empty: {zip_path}")

        preferred = [
            member for member in members if member.filename.lower().endswith((".docx", ".doc"))
        ]
        chosen = preferred[0] if preferred else members[0]

        temp_path = zip_path.with_name(f"__tmp__{sanitize_filename(Path(chosen.filename).name)}")
        with archive.open(chosen) as source, temp_path.open("wb") as target:
            shutil.copyfileobj(source, target)

    final_path = move_file_with_unique_name(temp_path, target_base)
    try:
        zip_path.unlink()
    except Exception:
        pass
    return final_path


def finalize_download(downloaded_path: Path, output_dir: Path, target_stem: str) -> Path:
    target_base = output_dir / sanitize_filename(target_stem)
    if downloaded_path.suffix.lower() == ".zip":
        return extract_zip_and_rename(downloaded_path, target_base)
    return move_file_with_unique_name(downloaded_path, target_base)


def save_document_from_popup(
    driver: webdriver.Chrome,
    download_dir: Path,
    output_dir: Path,
    target_stem: str,
    download_timeout: int,
) -> Path:
    original_handle = driver.current_window_handle
    current_handles = set(driver.window_handles)
    popup_candidates = [handle for handle in current_handles if handle != original_handle]
    if popup_candidates:
        popup_handle = popup_candidates[-1]
    else:
        WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
        popup_handle = [handle for handle in driver.window_handles if handle != original_handle][-1]

    driver.switch_to.window(popup_handle)

    try:
        try:
            wait_for_document_ready(driver, 20)
        except Exception:
            pass

        ensure_docx_selected_if_possible(driver)
        download_started_at = time.time()

        save_candidates = (
            (By.ID, "btnSave"),
            (By.XPATH, "//input[contains(@value,'שמור') or contains(@value,'הורד')]"),
            (By.XPATH, "//button[contains(.,'שמור') or contains(.,'הורד')]"),
            (By.XPATH, "//a[contains(.,'שמור') or contains(.,'הורד')]"),
        )
        last_error: Exception | None = None
        for locator in save_candidates:
            try:
                button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable(locator))
                driver.execute_script("arguments[0].click();", button)
                downloaded = wait_for_new_download(download_dir, download_started_at, download_timeout)
                return finalize_download(downloaded, output_dir, target_stem)
            except Exception as exc:
                last_error = exc
                continue

        raise RuntimeError(f"Could not trigger document save/download. Last error: {last_error}")
    finally:
        try:
            driver.close()
        except Exception:
            pass
        try:
            driver.switch_to.window(original_handle)
        except Exception:
            pass


def open_document_by_item(driver: webdriver.Chrome, item: dict) -> bool:
    document_id = (
        item.get("DocumentID")
        or item.get("documentid")
        or item.get("DocID")
        or item.get("DecisionID")
        or item.get("DecisionId")
    )
    if not document_id:
        return False
    driver.execute_script(f"__doPostBack('_ctl0:btnDocument','{document_id}&1')")
    return True


def open_document_by_selection_flow(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    expected_date: str,
) -> bool:
    if not click_row_checkbox_by_date(driver, expected_date):
        return False
    return click_download_docx_controls(driver, wait)


def download_for_task(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    download_dir: Path,
    output_dir: Path,
    task: VerdictTask,
    timeout: int,
    download_timeout: int,
) -> Path:
    search_header_case(driver, wait, timeout, task.case_number)
    ensure_site_is_available(driver)

    if not task.expected_date:
        raise RuntimeError("No date found in CSV row, so it is impossible to choose the correct verdict.")

    folder_ids = [VERDICTS_FOLDER_ID, DECISIONS_FOLDER_ID]

    for folder_id in folder_ids:
        open_folder(driver, wait, folder_id, timeout)
        items = read_grid_items(driver)
        chosen = pick_decision_item(items, task.expected_date)

        if chosen:
            if open_document_by_item(driver, chosen):
                return save_document_from_popup(
                    driver=driver,
                    download_dir=download_dir,
                    output_dir=output_dir,
                    target_stem=task.target_stem,
                    download_timeout=download_timeout,
                )

        if open_document_by_selection_flow(driver, wait, task.expected_date):
            return save_document_from_popup(
                driver=driver,
                download_dir=download_dir,
                output_dir=output_dir,
                target_stem=task.target_stem,
                download_timeout=download_timeout,
            )

    raise RuntimeError(
        f"No document matching date {task.expected_date} was found in 'פסקי דין' or 'החלטות בתיק' for case {task.case_number}."
    )


def main() -> None:
    args = parse_args()
    output_dir: Path = args.output_dir.resolve()
    download_dir = output_dir / "_court_gov_tmp"
    output_dir.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)

    tasks = read_tasks(args.csv.resolve(), args.start_row, args.limit)
    if not tasks:
        log("No rows to process.")
        return

    driver = build_driver(download_dir=download_dir, headless=args.headless)
    wait = WebDriverWait(driver, args.page_timeout)
    successes = 0
    failures: list[tuple[int, str, str]] = []

    try:
        driver.get(HOME_URL)
        wait_for_document_ready(driver, args.page_timeout)
        dismiss_terms_overlay(driver, wait)
        ensure_site_is_available(driver)

        total = len(tasks)
        for index, task in enumerate(tasks, start=1):
            if target_already_exists(output_dir, task.target_stem):
                log(f"[{index}/{total}] Skipping existing file for {task.case_number}: {task.target_stem}")
                continue

            log(
                f"[{index}/{total}] Case {task.case_number} | date={task.expected_date or 'missing'} | target={task.target_stem}"
            )
            try:
                saved_path = download_for_task(
                    driver=driver,
                    wait=wait,
                    download_dir=download_dir,
                    output_dir=output_dir,
                    task=task,
                    timeout=args.page_timeout,
                    download_timeout=args.download_timeout,
                )
                successes += 1
                log(f"    Saved: {saved_path}")
            except Exception as exc:
                failures.append((task.row_index, task.case_number, str(exc)))
                log(f"    Failed: {exc}")
            finally:
                try:
                    go_home(driver, wait, args.page_timeout)
                except Exception:
                    try:
                        driver.get(HOME_URL)
                        wait_for_document_ready(driver, args.page_timeout)
                    except Exception:
                        pass
                time.sleep(args.pause)
    finally:
        driver.quit()

    log("")
    log(f"Done. Successes: {successes} | Failures: {len(failures)}")
    if failures:
        log("Failures:")
        for row_index, case_number, reason in failures:
            log(f"  row={row_index} case={case_number} reason={reason}")


if __name__ == "__main__":
    main()
