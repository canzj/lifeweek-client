import io
import os
import tempfile
from functools import lru_cache
from logging import getLogger
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlretrieve, urlcleanup

import PyPDF4
import eyed3
import requests
from eyed3.id3 import ID3_V2_4

logger = getLogger(__name__)


class Visitor:
    def __init__(self, ticket: str):
        self.ticket = ticket

    def api_call(self, path: str, params_map: dict = None):
        api = urljoin("https://apis.lifeweek.com.cn/", path)
        params = {
            "isAsc": 1,
            "appVer": "9.6.0",
            "apiVer": "9.6.0",
            "_plf": "iPhone",
            "_net": "WIFI",
            "_ver": "16.3.1",
            "mac": "",
            "channel": "IPHONE",
            "_os": "iOS",
            "ticket": self.ticket
        }
        params_map.update(params)
        response = requests.get(api, params=params_map).json()
        assert response["success"]
        assert "model" in response.keys()
        return response["model"]

    def search_content(self, keyword: str):
        data = []
        param = {'word': keyword}
        model = self.api_call(f"api/search/queryAllV3", param)
        concern_category_type = [
            27,  # 有声书
            2,  # 专栏
            74,  # 数字刊
        ]
        for category in model:
            if category["categoryType"] in concern_category_type:
                for item in category["data"]:
                    item["category"] = category["category"]
                    data.append(item)

        return data

    def save_column_article(self, column_id):
        import pdfkit
        from PyPDF4 import PdfFileReader

        model = self.api_call("zhuanlan/zhuanlanV50305.do", {"id": column_id})
        article_list = [(article["webUrl"], article["title"]) for article in model["articleList"]]
        cover_url = model["zhuanlan"]["shareData"]["image"]
        column_title = self.parse_column_title(model)
        column_dir = Path(column_title)
        column_dir.mkdir(exist_ok=True)

        # Convert and merge each chapter
        temp_files = []
        successful_article_list = []
        for i, (url, title) in enumerate(article_list, start=0):
            response = requests.get(url)
            html_content = response.text
            try:
                pdf_bytes = pdfkit.from_string(html_content, output_path=None)  # Get PDF as bytes
                temp_file = io.BytesIO(pdf_bytes)  # Store bytes in a BytesIO object
                temp_files.append(temp_file)
                successful_article_list.append((url, title))  # Add the successful article to a new list
            except Exception as e:
                logger.error(f"Error parsing content {html_content}")
                continue
        article_list = successful_article_list  # Replace the original list with the filtered list

        # Save merged PDF
        final_output = column_dir / "{}.pdf".format(column_title)
        with final_output.open("wb") as f:
            pdf_writer = PyPDF4.PdfFileWriter()

            # Add the cover page
            cover_pdf = self.create_cover_pdf(cover_url)
            pdf_reader = PdfFileReader(cover_pdf)
            cover_page_num = pdf_reader.getNumPages()
            for page_num in range(cover_page_num):
                page = pdf_reader.getPage(page_num)
                pdf_writer.addPage(page)

            # Add table of contents PDF
            toc_pdf = self.create_toc_pdf(article_list)
            pdf_reader = PdfFileReader(toc_pdf)
            toc_page_num = pdf_reader.getNumPages()
            for page_num in range(toc_page_num):
                page = pdf_reader.getPage(page_num)
                pdf_writer.addPage(page)

            # Loop through each temporary PDF file and add pages
            for index, temp_file in enumerate(temp_files):
                temp_file.seek(0)
                pdf_reader = PdfFileReader(temp_file)
                for page_num in range(pdf_reader.getNumPages()):
                    page = pdf_reader.getPage(page_num)
                    pdf_writer.addPage(page)

            # Loop through the temporary files again and add bookmarks
            current_page = cover_page_num + toc_page_num
            for index, temp_file in enumerate(temp_files):
                temp_file.seek(0)
                pdf_reader = PdfFileReader(temp_file)
                pdf_writer.addBookmark(article_list[index][1], current_page)
                current_page += pdf_reader.getNumPages()

            # Save the merged output
            pdf_writer.write(f)

    @staticmethod
    def create_toc_pdf(article_list):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

        font_path = "/System/Library/Fonts/STHeiti Medium.ttc"
        font_name = "STHeiti"
        pdfmetrics.registerFont(TTFont(font_name, font_path))

        toc_buffer = io.BytesIO()
        doc = SimpleDocTemplate(toc_buffer, pagesize=letter)

        story = [Spacer(1, 2 * inch)]

        table_data = []
        for index, (_, title) in enumerate(article_list):
            table_data.append([f"第{index + 1}章", title])

        table = Table(table_data, colWidths=[1.5 * inch, 4.5 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                    ("FONTNAME", (0, 0), (-1, -1), font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 14),
                ]
            )
        )
        story.append(table)
        doc.build(story)
        toc_buffer.seek(0)
        return toc_buffer

    @staticmethod
    def create_cover_pdf(cover_url):
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import inch
        import requests
        from PIL import Image
        from reportlab.pdfgen import canvas

        # Download the cover image
        response = requests.get(cover_url)
        cover_image = Image.open(io.BytesIO(response.content))

        # Save the cover image to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
            cover_image.save(temp_file.name, "JPEG")
            temp_image_path = temp_file.name

        # Create a new PDF with a single page
        cover_pdf = io.BytesIO()
        c = canvas.Canvas(cover_pdf, pagesize=A4)

        # Place the cover image on the page (you can adjust the size and position as needed)
        c.drawImage(temp_image_path, 0.5 * inch, 0.5 * inch, width=7 * inch, height=10 * inch)

        # Close the canvas and return the PDF
        c.showPage()
        c.save()
        cover_pdf.seek(0)

        # Clean up the temporary image file
        os.remove(temp_image_path)

        return cover_pdf

    def save_column_audio(self, column_id):
        model = self.api_call("zhuanlan/zhuanlanV50305.do", {"id": column_id})

        column_title = self.parse_column_title(model)
        column_dir = Path(column_title)
        column_dir.mkdir(exist_ok=True)

        column_author = model["author"]
        article_map = {article["title"]: article for article in model["articleList"]}
        audio_list = model["songlist"]
        for audio in audio_list:
            track_no = audio["lessionNo"]
            title = audio["title"]
            img_url = audio["pic"]
            fname = column_dir / "{}.mp3".format(title)
            if not fname.exists():
                urlretrieve(audio["audio_url"], fname)

            self.retag(fname, column_title, title, column_author, track_no, article_map[title]["dayStr"])
            self.retag_cover(fname, img_url)
            logger.info(f"save audio {str(fname)}")

    @staticmethod
    def parse_column_title(model):
        column_title = model["zhuanlan"]["shareData"]["title"]
        column_subtitle = model["zhuanlan"]["shareData"]["desc"]
        if column_subtitle:
            if column_title[-1] in ['。', '？', '！']:
                return column_title + column_subtitle
            else:
                return column_title + ' - ' + column_subtitle
        else:
            return column_title

    @staticmethod
    def retag(fname, column_title, title, author, track_no, pub_date):
        audio = eyed3.load(fname)

        audio.initTag(version=ID3_V2_4)
        audio.tag.title = title
        audio.tag.album = column_title
        audio.tag.artist = author
        audio.tag.track_num = track_no
        audio.tag.recording_date = pub_date

        audio.tag.save()

    @staticmethod
    def retag_cover(fname, img_url):
        @lru_cache()
        def _get_cover(url: str) -> bytes:
            cover_fname, _ = urlretrieve(url)
            with open(cover_fname, "rb") as fp:
                cover = fp.read()
            urlcleanup()
            return cover

        cover = _get_cover(img_url)

        audio = eyed3.load(fname)
        if audio.tag is None:
            audio.initTag(version=ID3_V2_4)

        audio.tag.images.set(3, cover, "image/jpeg", description="Cover")
        audio.tag.save()
