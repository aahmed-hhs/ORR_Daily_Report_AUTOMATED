# Daily Reports -- Excel Converter
This repository has been developed to support ORR IAB in the production of daily reports.

The functions here will take four (or fewer) Excel or csv files, add them as unique sheets into an Excel workbook,
apply formatting, and return the formatted workbook.

## Installation
Please clone this repo via Github for use:

```bash
git clone https://github.com/HHS/ach-orr-daily-reports.git
```

## Instructions for Use

(Please see Sharepoint for instructions on pulling the individual .csv files from PowerBI.)
1. Before executing: Save all .csv's in the repository in a "Data Sources" folder, with a subfolder containing today's date in MM-DD-YYYY format and subfolders for
the HSI deliverables (titled "HSI") and UACB (titled "UACB") deliverables.

3. Activate the venv for this 
```bash
.\venv\Scripts\Activate
```
3. Run the following command:
```bash
python run_daily_reports.py
```
4. Inspect the generated input for consistency.
5. Upload results to Sharepoint.

If there are any questions, please contact Declan Murphy. 



