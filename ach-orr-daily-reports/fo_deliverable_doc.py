from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


REPORT_TITLE = "ORR IAB Division of Vetting - Data Summary Report"
WORD_IMAGE_MAX_WIDTH_EMU = 5_943_600
WORD_IMAGE_MAX_HEIGHT_EMU = 8_229_600
EMU_PER_PX_AT_96_DPI = 9_525


def create_fo_deliverable_doc(daily_folder, report_date):
    fo_deliverable_png = find_fo_deliverable_png(Path(daily_folder))
    return create_word_doc_from_png(fo_deliverable_png, report_date)


def find_fo_deliverable_png(daily_folder):
    if not daily_folder.exists():
        raise FileNotFoundError(
            "Required daily data folder was not found. "
            f"Expected folder: {daily_folder}. "
            "Create the folder for today's run under Data Sources using the MM-DD-YYYY date format, "
            "then place the FO Deliverable PNG directly inside it."
        )

    if not daily_folder.is_dir():
        raise FileNotFoundError(
            "Required daily data folder path exists but is not a folder. "
            f"Expected a folder at: {daily_folder}. "
            "Replace this path with a folder containing today's source files."
        )

    matches = sorted(
        path
        for path in daily_folder.iterdir()
        if path.is_file()
        and path.suffix.lower() == ".png"
        and "fo deliverable" in path.name.lower()
    )

    if not matches:
        png_files = sorted(
            path.name
            for path in daily_folder.iterdir()
            if path.is_file() and path.suffix.lower() == ".png"
        )
        png_file_summary = (
            "PNG files found: " + ", ".join(png_files)
            if png_files
            else "No PNG files were found in this folder."
        )
        raise FileNotFoundError(
            "Required FO Deliverable PNG was not found. "
            f"Searched folder: {daily_folder}. "
            "Expected a .png file with 'FO Deliverable' in the filename, placed directly in the daily folder. "
            f"{png_file_summary}"
        )

    return matches[0]


def get_png_dimensions(png_path):
    with png_path.open("rb") as image_file:
        header = image_file.read(24)

    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"The FO Deliverable file is not a valid PNG: {png_path}")

    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return width, height


def scaled_image_size_emu(png_path):
    width_px, height_px = get_png_dimensions(png_path)
    width_emu = width_px * EMU_PER_PX_AT_96_DPI
    height_emu = height_px * EMU_PER_PX_AT_96_DPI

    scale = min(
        WORD_IMAGE_MAX_WIDTH_EMU / width_emu,
        WORD_IMAGE_MAX_HEIGHT_EMU / height_emu,
        1,
    )
    return int(width_emu * scale), int(height_emu * scale)


def format_report_date(report_date):
    day = report_date.day
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

    return f"{report_date.strftime('%A, %B')} {day}{suffix}, {report_date.year}"


def create_word_doc_from_png(png_path, report_date):
    output_path = png_path.with_suffix(".docx")
    width_emu, height_emu = scaled_image_size_emu(png_path)
    image_name = escape(png_path.name, {'"': "&quot;"})
    report_title = escape(REPORT_TITLE)
    report_date_text = escape(format_report_date(report_date))

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
    package_relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
    document_relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>
"""
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    <w:p>
      <w:pPr>
        <w:jc w:val="center"/>
      </w:pPr>
      <w:r>
        <w:rPr>
          <w:b/>
          <w:sz w:val="28"/>
          <w:szCs w:val="28"/>
        </w:rPr>
        <w:t>{report_title}</w:t>
        <w:br/>
        <w:t>{report_date_text}</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:r>
        <w:drawing>
          <wp:inline distT="0" distB="0" distL="0" distR="0">
            <wp:extent cx="{width_emu}" cy="{height_emu}"/>
            <wp:docPr id="1" name="{image_name}"/>
            <a:graphic>
              <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
                <pic:pic>
                  <pic:nvPicPr>
                    <pic:cNvPr id="1" name="{image_name}"/>
                    <pic:cNvPicPr/>
                  </pic:nvPicPr>
                  <pic:blipFill>
                    <a:blip r:embed="rId1"/>
                    <a:stretch>
                      <a:fillRect/>
                    </a:stretch>
                  </pic:blipFill>
                  <pic:spPr>
                    <a:xfrm>
                      <a:off x="0" y="0"/>
                      <a:ext cx="{width_emu}" cy="{height_emu}"/>
                    </a:xfrm>
                    <a:prstGeom prst="rect">
                      <a:avLst/>
                    </a:prstGeom>
                  </pic:spPr>
                </pic:pic>
              </a:graphicData>
            </a:graphic>
          </wp:inline>
        </w:drawing>
      </w:r>
    </w:p>
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"""

    with ZipFile(output_path, "w", ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", package_relationships)
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/_rels/document.xml.rels", document_relationships)
        docx.write(png_path, "word/media/image1.png")

    print(f"New Word file created at {output_path} !")
    return output_path
