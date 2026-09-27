import os
import re
import pandas as pd
from docx import Document as load_doc
from docx.document import Document as DocxDocument
import sys

current_dir = os.path.abspath(__file__)
pred_sentencing_path = os.path.abspath(os.path.join(current_dir, '..', '..'))
sys.path.insert(0, pred_sentencing_path)


from docx.text.paragraph import Paragraph
from docx.table import _Cell, Table
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl

# Modify property of Paragraph.text to include hyperlink text

Paragraph.text = property(lambda self: get_paragraph_text(self))

# Optional: Word COM automation for .doc -> .docx conversion on Windows
try:
    import win32com.client as win32  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    win32 = None

def get_paragraph_text(paragraph) -> str:
    # אוסף את כל הטקסטים w:t מכל מקום בפסקה (כולל hyperlinks וכו')
    texts = []
    for t in paragraph._p.xpath(".//w:t"):
        if t.text:
            texts.append(t.text)
    return "".join(texts)

def is_paragraph_visually_bold(paragraph):
    """
    Check if the ENTIRE paragraph is bold or underlined.
    Returns True only if all meaningful text in the paragraph has bold/underline formatting.
    Includes support for complex scripts (Hebrew, Arabic, etc.) via w:bCs.
    """
    if not paragraph.runs or not paragraph.text.strip():
        return False
    
    total_text_length = 0
    formatted_text_length = 0
    
    # Method 1: Check individual runs for bold or underline
    for run in paragraph.runs:
        run_text = run.text.strip()
        if not run_text:  # Skip empty runs
            continue
        
        total_text_length += len(run_text)
        is_formatted = False
        
        # Check python-docx properties
        if run.bold or run.underline:
            is_formatted = True
        else:
            # Check XML-level bold (both regular and complex script)
            try:
                rpr = run._r.rPr
                if rpr is not None:
                    # Check for regular bold (w:b)
                    b = rpr.find('.//{*}b')
                    if b is not None and b.get('{*}val') != '0':
                        is_formatted = True
                    
                    # Check for complex script bold (w:bCs) - IMPORTANT for Hebrew!
                    if not is_formatted:
                        bCs = rpr.find('.//{*}bCs')
                        if bCs is not None and bCs.get('{*}val') != '0':
                            is_formatted = True
                    
                    # Check for underline element
                    if not is_formatted:
                        u = rpr.find('.//{*}u')
                        if u is not None:
                            is_formatted = True
            except:
                pass
        
        if is_formatted:
            formatted_text_length += len(run_text)
    
    # If no text found, return False
    if total_text_length == 0:
        return False
    
    # Calculate ratio of formatted text
    ratio = formatted_text_length / total_text_length
    
    # Method 2: Check paragraph style for bold formatting
    # (this applies to all text if no run-level formatting exists)
    if ratio < 0.9:  # Only check style if runs didn't show enough formatting
        try:
            style = paragraph.style
            if style is not None:
                if hasattr(style, '_element') and hasattr(style._element, 'rPr'):
                    rpr = style._element.rPr
                    if rpr is not None:
                        b = rpr.find('.//{*}b')
                        if b is not None and b.get('{*}val') != '0':
                            return True
                        
                        bCs = rpr.find('.//{*}bCs')
                        if bCs is not None and bCs.get('{*}val') != '0':
                            return True
                        
                        u = rpr.find('.//{*}u')
                        if u is not None:
                            return True
        except:
            pass
    
    # Method 3: Check paragraph properties directly
    if ratio < 0.9:
        try:
            pPr = paragraph._p.pPr
            if pPr is not None:
                rpr = pPr.find('.//{*}rPr')
                if rpr is not None:
                    b = rpr.find('.//{*}b')
                    if b is not None and b.get('{*}val') != '0':
                        return True
                    
                    bCs = rpr.find('.//{*}bCs')
                    if bCs is not None and bCs.get('{*}val') != '0':
                        return True
                    
                    u = rpr.find('.//{*}u')
                    if u is not None:
                        return True
        except:
            pass
    
    # Return True only if 90%+ of text is formatted
    # (allows for small inconsistencies like spaces or punctuation)
    return ratio >= 0.9

def iterate_block_items(parent):
    """Yield top-level paragraphs in the document; skip most tables.

    Special case: if a table has exactly one cell and its text contains
    'גזר דין', yield that cell's paragraphs instead of skipping.
    """
    if isinstance(parent, DocxDocument):
        parent_element = parent.element.body
    elif isinstance(parent, _Cell):
        parent_element = parent._tc
    else:
        raise ValueError("Unsupported parent type.")

    for child in parent_element.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)

        elif isinstance(child, CT_Tbl):
            table = Table(child, parent)

            # Check if table is a single cell
            if len(table.rows) == 1 and len(table.columns) == 1:
                cell = table.cell(0, 0)
                cell_text = cell.text or ""

                # If the single cell contains 'גזר דין', yield its paragraphs
                if "גזר דין" in cell_text:
                    for p in cell.paragraphs:
                        yield p
                    continue  # go to next child

            # Otherwise: skip this table entirely
            continue

def doc_to_csv(doc_path: str = None, result_path: str = None):
    """
    Converts a DOCX document to a CSV where each row is a paragraph.
    Only skips מיני רציו sections.

    Parameters:
    - doc_path (str, optional): The path to the DOCX document. Defaults to None.

    Returns:
    - DataFrame: A Pandas DataFrame containing the extracted text from the DOCX document with column 'text'.
    """

    data = {'verdict': [], 'text': []}
    data['verdict'] = os.path.splitext(os.path.basename(doc_path))[0]
    doc = load_doc(doc_path)
    skip_mini_ratio = False

    for block in iterate_block_items(doc):
        # Skip paragraphs that are inside a table (parent XML tag w:tc)
        try:
            if getattr(block, "_p", None) is not None:
                parent = block._p.getparent()
                if hasattr(parent, "tag") and str(parent.tag).endswith('}tc'):
                    text = (block.text or "").strip()
                    if "גזר דין" not in text:
                        continue
        except Exception:
            # If detection fails for any reason, fall back to processing
            pass
        
        block_text = block.text

        # Detect מיני-רציו section start (even if not bold)
        if "מיני-רציו" in block_text or "מיני רציו" in block_text or "מיני - רציו" in block_text:
            skip_mini_ratio = True
            continue
        
        # Skip all lines under מיני-רציו until next bold title
        if skip_mini_ratio:
            if is_paragraph_visually_bold(block):   # new section started
                skip_mini_ratio = False
                # Continue to process this line as normal text
            else:
                continue
        
        # Skip empty paragraphs
        if not block_text or len(block_text.strip()) == 0:
            continue
        
        # Add the text
        data['text'].append(block_text.strip())

    sentence_doc_df = pd.DataFrame(data)

    # Decide output path: allow result_path to be a file path (..csv) or a directory
    if result_path and result_path.lower().endswith('.csv'):
        out_path = result_path
    else:
        if result_path is None:
            out_path = os.path.splitext(doc_path)[0] + '.csv'
        else:
            out_path = os.path.join(result_path, 'preprocessing.csv')

    sentence_doc_df.to_csv(out_path, index=False, encoding='utf-8-sig')
    #from df to big text
    full_text = '\n'.join(sentence_doc_df['text'].tolist())
    return out_path, full_text




if __name__ == "__main__":
    
    folder_path = r'C:\Users\user\OneDrive\טל\projects\justice-tal\bias_weapon\all_verdicts'
    output_base = f"CSV_OUTPUT"
    os.makedirs(output_base, exist_ok=True)
    files_list = os.listdir(folder_path)
    total_files = len(files_list)
    count_files = 0
    all_verdicts = []

    # Iterate files and process .doc/.docx
    for file in files_list:
        # Skip temp/hidden files and folders
        if file.startswith('~$') or file.startswith('.'):
            continue

        in_path = os.path.join(folder_path, file)
        if not os.path.isfile(in_path):
            continue

        name, ext = os.path.splitext(file)
        ext = ext.lower()
        if file.startswith('m01'):
            continue

        # if file != "SH-13-11-38875-116.docx":
        #     continue
        # print(1)
        # If .doc, try convert to .docx first

        # Process .docx files
        if ext == ".docx":
            count_files += 1
            out_csv = os.path.join(output_base, f"{name}.csv")
            # check if output already exists
            # if os.path.exists(out_csv):
            #     print(f"Skipping {file}: output CSV already exists. ({count_files}/{total_files})")
            #     # Still read existing CSV to add to big df
            #     try:
            #         existing_df = pd.read_csv(out_csv)
            #         full_text = ' '.join(existing_df['text'].tolist())
            #         all_verdicts.append({
            #             'verdict': name,
            #             'full_text': full_text
            #         })
            #     except Exception as e:
            #         print(f"[WARN] Could not read existing {out_csv}: {e}")
            #     continue
            try:
                print(f"Processing {os.path.basename(in_path)} -> {out_csv}")
                written, full_text = doc_to_csv(in_path, out_csv)
                all_verdicts.append({
                    'verdict': name,
                    'full_text': full_text
                })
                print(f"Saved sentences -> {written} - process {count_files}/{total_files} ({100*count_files//total_files}%)")
            except Exception as e:
                print(f"[ERROR] Failed processing {in_path}: {e} ({count_files}/{total_files})")
        else:
            # Not a Word document
            continue
        # Create big DataFrame with all verdicts
    big_df = pd.DataFrame(all_verdicts)
    # Save to CSV
    big_csv_path = os.path.join(r"C:\Users\user\OneDrive\טל\projects\justice-tal\bias_weapon\data", 'all_verdicts.csv')
    big_df.to_csv(big_csv_path, index=False, encoding='utf-8-sig')
    print(f"\nSaved all verdicts -> {big_csv_path}")
    print(f"Total verdicts: {len(big_df)}")