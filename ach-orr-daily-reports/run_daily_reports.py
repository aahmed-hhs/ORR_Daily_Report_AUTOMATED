# Run Daily Report

from csv_convert import combine_files
from fo_deliverable_doc import create_fo_deliverable_doc
from datetime import date, timedelta
import glob

today = date.today()
today_formatted = today.strftime("%m-%d-%Y")
print(today_formatted)

tomorrow = today + timedelta(days = 1)
while tomorrow.weekday() >= 5:   # skip Saturday/Sunday: a Friday run reports Monday
    tomorrow += timedelta(days = 1)
tomorrow_formatted = tomorrow.strftime("%m-%d-%Y")

create_fo_deliverable_doc(f"./Data Sources/{today_formatted}", tomorrow)

# For UACB:

filepath1 = f"./Data Sources/{today_formatted}/UACB" 
outpath1 = f"./Data Sources/{today_formatted}/UACB/UACB Daily {tomorrow_formatted}.xlsx" 

combine_files(filepath1, outpath1)


# For HSI:

filepath2 = f"./Data Sources/{today_formatted}/HSI"
outpath2 = f"./Data Sources/{today_formatted}/HSI/HSI Daily {tomorrow_formatted}.xlsx"

combine_files(filepath2, outpath2)
