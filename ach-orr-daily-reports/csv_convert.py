### Convert CSV files to a singular, formatted Excel

## PLEASE NOTE: Actual data will contain PII, so script executes based on sample data (for now);
## please confirm appropriateness of use w/ PII before executing on actual data
## Dummy headers correspond to target data headers but do NOT contain actual data

import pandas as pd
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import NamedStyle, Font, PatternFill, Border, Side, Alignment
from pathlib import Path
import glob


def create_styles(name1, name2, name3):
    """
    Docstring for create_styles
    
    Parameters:
    name1: The name that will be used to call the header style.
    name2: The name that will be used to call the normal style.

    Returns: 
    wb: An empty Excel workbook with named styles applied. 
    """
    # Create named styles
    header_style = NamedStyle(name=name1)
    header_style.font = Font(name="Aptos Narrow", bold=True, size=12)
    header_side = Side(border_style="thick", color="000000")
    header_style.border = Border(left=header_side, right=header_side, top=header_side, bottom=header_side)
    header_style.fill = PatternFill(patternType = 'solid',
                                    fill_type = 'solid', 
                                    fgColor = "DAE9F8")
    header_style.alignment = Alignment(horizontal = "center")

    normal_style = NamedStyle(name=name2)
    normal_style.font = Font(name="Aptos Narrow", size = 12)
    side = Side(border_style="thin", color="000000")
    normal_style.border = Border(left=side, right=side, top=side, bottom=side)
    normal_style.alignment = Alignment(horizontal = "center")

    # Add a date style
    date_style = NamedStyle(name=name3)
    date_style.font = Font(name="Aptos Narrow", size=12)
    side = Side(border_style="thin", color="000000")
    date_style.border = Border(left=side, right=side, top=side, bottom=side)
    date_style.alignment = Alignment(horizontal="center")
    date_style.number_format = 'mm/dd/yyyy'  # Add date format
    
    # Establish workbook
    wb = Workbook()
    wb.remove(wb.active)

    # Add styles
    wb.add_named_style(header_style)
    wb.add_named_style(normal_style)
    wb.add_named_style(date_style)

    return wb



def format_worksheet(ws, name1, name2):
    """
    Docstring for format_worksheet
    
    Parameters:
    ws: Description
    name1: The names of the style to be applied to the header.
    name2: The name of the style to be applied to the non-header cells.
    """
    print(f"Formatting worksheet", ws.title)

    print("    Applying header style to header rows")
    for cell in ws[1]:
        cell.value = cell.value.upper()
        cell.style = name1

    # Apply named style to specific range
    max_col_letter = get_column_letter(ws.max_column)
    max_row = ws.max_row
    print(f"    Applying normal_style to range A2:{max_col_letter}{max_row}")
    for row in ws[f'A2:{max_col_letter}{max_row}']:
        for cell in row:
            if cell.coordinate:  # Make sure cell exists
                cell.style = name2

    for col in range(1, ws.max_column+1):
          column_letter = ws.cell(row=1, column=col).column_letter
          ws.column_dimensions[column_letter].width = 25  

def combine_files(input_path, output_file, sort_files = True, sheet_names=None, name1 = "header_style", name2 = "normal_style", name3 = "date_style"):
    """
    A function to combine multiple csv files into a single Excel workbook,
    and apply style.
    
    Parameters:
        csv_path: The path to the directory that contains the relevant csv files.
        output_file: PathName where the final Excel file should be saved. 
        sheet_names: (optional) A list of sheet names to be applied to the final workbook.

    Returns:
        output_file: A formatted Excel workbook containing the data within each .csv as a separate
        sheet. 
    """

    # Establish workbook
    wb = create_styles(name1, name2, name3)

    # Iterate over csv files
    path = input_path + "/*.xlsx"
    input_files = glob.glob(path)

    if sort_files == True:
        input_dict = dict.fromkeys(input_files, "")

        for key in input_dict.keys():
            if "TODAY".casefold() in key.casefold():
                input_dict[key] = 0
            elif "MASTER".casefold() in key.casefold():
                input_dict[key] = 1
            elif "NOT SENT".casefold() in key.casefold():
                input_dict[key] = 2
            elif "CLOSED".casefold() in key.casefold():
                input_dict[key] = 3
            else: 
                input_dict[key] = 999
        
        sorted_files = sorted(input_dict, key=input_dict.get)
        print(sorted_files)

    else:
        sorted_files = input_files # No sort; pass directly into the next function unsorted

    for i, csv_file in enumerate(sorted_files):
        df = pd.read_excel(csv_file, sheet_name=0,
                           parse_dates = ["DATE DATA SUMMARY SENT TO HSI"])

        df = df[~df['TRACKING NUMBER'].str.contains("Applied filters:", na=False)]

        if sheet_names is None:
            sheet_title = Path(csv_file).stem
        else:
            sheet_title = sheet_names[i]

        ws = wb.create_sheet(title=sheet_title)

        for r in dataframe_to_rows(df, index=False, header=True):
            ws.append(r)

        format_worksheet(ws, name1, name2)

        # Apply date style to date columns
        date_col = "DATE DATA SUMMARY SENT TO HSI"

        if date_col in df.columns:
            date_col_idx = df.columns.get_loc(date_col) + 1
            for row in range(2, ws.max_row + 1):
                cell = ws.cell(row=row, column=date_col_idx)
                if cell.value is not None:
                    cell.style = "date_style" 

    # Save and listed output
    wb.save(output_file)
    print(f"New file created at {output_file} !")


# Load and apply
if __name__ == "__main__" :

    file_path = "./Data Sources"

    sheet_names = ['Master', 'Today', 'Closed', 'Not Sent']

    combine_files(
        file_path,
        name1 = "header_style",
        name2 = "normal_style",
        output_file='./output.xlsx',
        sheet_names=sheet_names
    )

    




        