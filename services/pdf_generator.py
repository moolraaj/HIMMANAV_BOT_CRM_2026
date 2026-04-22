# services/pdf_generator.py
import os
import requests
import base64
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch, mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect
from PIL import Image
import io
import re
from dotenv import load_dotenv

load_dotenv('.env')

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('PHONE_NUMBER_ID')

# Try to register a Unicode font for better rendering
try:
    pdfmetrics.registerFont(TTFont('DejaVu', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    FONT_NAME = 'DejaVu'
except:
    try:
        pdfmetrics.registerFont(TTFont('Arial', 'Arial.ttf'))
        FONT_NAME = 'Arial'
    except:
        FONT_NAME = 'Helvetica'


def clean_html(text):
    """Remove HTML tags from text"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&#8211;', '-', text)
    text = re.sub(r'&#8217;', "'", text)
    text = re.sub(r'&#8220;', '"', text)
    text = re.sub(r'&#8221;', '"', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def download_image(url):
    """Download image from URL and return as BytesIO object"""
    try:
        if not url:
            print(f"⚠️ No URL provided for image download")
            return None
        print(f"📥 Downloading image from: {url}")
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            print(f"✅ Image downloaded successfully, size: {len(response.content)} bytes")
            return io.BytesIO(response.content)
        else:
            print(f"❌ Failed to download image, status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Failed to download image: {e}")
        return None


def create_gradient_rect(c, x, y, width, height, color1, color2):
    """Create gradient rectangle for background"""
    for i in range(int(height)):
        ratio = i / height
        r = color1[0] + (color2[0] - color1[0]) * ratio
        g = color1[1] + (color2[1] - color1[1]) * ratio
        b = color1[2] + (color2[2] - color1[2]) * ratio
        c.setFillColor(colors.Color(r/255, g/255, b/255))
        c.rect(x, y + i, width, 1, fill=1, stroke=0)


# ── Proper ReportLab Flowable ──────────────────────────────────────────────────
class BackgroundImageFrame(Flowable):
    """A ReportLab Flowable that draws a background image (or gradient) with
    overlaid paragraph content."""

    def __init__(self, bg_image, width, height, text_content, is_even):
        super().__init__()
        self.bg_image = bg_image
        self.width = width
        self.height = height
        self.text_content = text_content
        self.is_even = is_even

    def wrap(self, availWidth, availHeight):
        # Tell ReportLab how much space we need
        return (self.width, self.height)

    def getKeepWithNext(self):
        """Required by ReportLab's document template. 
        Return False to prevent keeping this flowable with the next one."""
        return False

    def draw(self):
        # self.canv is set automatically by ReportLab before draw() is called
        c = self.canv
        x, y = 0, 0   # coordinates are relative to the flowable's own origin

        if self.bg_image:
            try:
                # Reset to start of BytesIO before opening
                if hasattr(self.bg_image, 'seek'):
                    self.bg_image.seek(0)
                img = Image.open(self.bg_image)
                img_width, img_height = img.size
                aspect = img_height / img_width
                draw_width = self.width
                draw_height = draw_width * aspect

                # Seek again before drawImage (ReportLab needs it from the start)
                if hasattr(self.bg_image, 'seek'):
                    self.bg_image.seek(0)

                c.saveState()
                c.drawImage(self.bg_image, x, y, width=draw_width, height=min(draw_height, self.height))
                c.setFillColor(colors.Color(0, 0, 0, alpha=0.6))
                c.rect(x, y, self.width, self.height, fill=1, stroke=0)
                c.restoreState()
            except Exception as e:
                print(f"⚠️ Failed to draw background image: {e}")
                create_gradient_rect(c, x, y, self.width, self.height,
                                     (26, 26, 46), (15, 21, 38))
        else:
            create_gradient_rect(c, x, y, self.width, self.height,
                                 (26, 26, 46), (15, 21, 38))

        # Draw text content from top-down
        text_x = x + 0.2 * inch
        text_y = y + self.height - 0.3 * inch

        for para in self.text_content:
            w, h = para.wrap(self.width - 0.4 * inch, self.height)
            text_y -= h
            para.drawOn(c, text_x, text_y)
            text_y -= 5   # small gap between paragraphs
# ──────────────────────────────────────────────────────────────────────────────


class StyledPDF:
    def __init__(self, filename, pagesize=A4):
        self.filename = filename
        self.pagesize = pagesize
        self.doc = SimpleDocTemplate(filename, pagesize=pagesize,
                                     leftMargin=15*mm, rightMargin=15*mm,
                                     topMargin=20*mm, bottomMargin=20*mm)
        self.story = []
        self.styles = self._create_styles()

    def _create_styles(self):
        styles = getSampleStyleSheet()

        styles.add(ParagraphStyle(
            name='MainTitle',
            parent=styles['Title'],
            fontSize=40,
            textColor=colors.HexColor('#1a1a2e'),
            alignment=TA_CENTER,
            spaceAfter=30,
            spaceBefore=20,
            fontName=FONT_NAME
        ))

        styles.add(ParagraphStyle(
            name='SectionHeading',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#16213e'),
            alignment=TA_CENTER,
            spaceAfter=20,
            spaceBefore=25,
            fontName=FONT_NAME
        ))

        styles.add(ParagraphStyle(
            name='DayTitle',
            parent=styles['Heading2'],
            fontSize=20,
            textColor=colors.HexColor('#e94560'),
            spaceAfter=10,
            fontName=FONT_NAME
        ))

        styles.add(ParagraphStyle(
            name='Subheading',
            parent=styles['Heading3'],
            fontSize=18,
            textColor=colors.HexColor('#0f3460'),
            spaceAfter=8,
            fontName=FONT_NAME
        ))

        if 'BodyTextStyle' not in styles:
            styles.add(ParagraphStyle(
                name='BodyTextStyle',
                parent=styles['Normal'],
                fontSize=11,
                textColor=colors.HexColor('#2c2c2c'),
                alignment=TA_JUSTIFY,
                spaceAfter=6,
                leading=16,
                fontName=FONT_NAME
            ))

        if 'ListItemStyle' not in styles:
            styles.add(ParagraphStyle(
                name='ListItemStyle',
                parent=styles['Normal'],
                fontSize=11,
                textColor=colors.HexColor('#2c2c2c'),
                leftIndent=20,
                bulletIndent=10,
                spaceAfter=4,
                leading=16,
                fontName=FONT_NAME
            ))

        if 'HighlightStyle' not in styles:
            styles.add(ParagraphStyle(
                name='HighlightStyle',
                parent=styles['Normal'],
                fontSize=12,
                textColor=colors.HexColor('#e94560'),
                fontName=FONT_NAME
            ))

        if 'ContactTextStyle' not in styles:
            styles.add(ParagraphStyle(
                name='ContactTextStyle',
                parent=styles['Normal'],
                fontSize=14,
                textColor=colors.HexColor('#ffffff'),
                alignment=TA_CENTER,
                fontName=FONT_NAME
            ))

        return styles

    def add_cover_page(self, package_name, package_price, duration, locations):
        """Add cover page with package info"""
        cover_story = []

        cover_story.append(Paragraph(package_name.upper(), self.styles['MainTitle']))
        cover_story.append(Spacer(1, 0.5*inch))

        price_data = [
            ["💰 PRICE", "📅 DURATION", "📍 DESTINATION"],
            [
                f"₹{package_price}",
                f"{duration.get('days', 0)} Days / {duration.get('nights', 0)} Nights",
                ', '.join(locations[:3])
            ]
        ]

        price_table = Table(price_data, colWidths=[2.2*inch, 2.2*inch, 2.2*inch])
        price_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16213e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('FONTSIZE', (0, 1), (-1, 1), 14),
            ('BOLD', (0, 0), (-1, 0), 1),
            ('BOLD', (0, 1), (-1, 1), 1),
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#e94560')),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f5f5f5')),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ]))

        cover_story.append(price_table)
        cover_story.append(Spacer(1, 0.3*inch))
        cover_story.append(Paragraph("━" * 60, self.styles['BodyTextStyle']))
        cover_story.append(Spacer(1, 0.2*inch))
        cover_story.append(Paragraph("Your Journey Begins Here", self.styles['Subheading']))
        cover_story.append(Spacer(1, 0.5*inch))

        doc = SimpleDocTemplate(self.filename.replace('.pdf', '_cover.pdf'), pagesize=self.pagesize)
        doc.build(cover_story)
        self.story.append(PageBreak())

    def add_section_header(self, title, icon="📋"):
        """Add section header with icon"""
        self.story.append(Paragraph(f"{icon} <b>{title.upper()}</b>", self.styles['SectionHeading']))
        self.story.append(Spacer(1, 0.1*inch))
        self.story.append(Paragraph("━" * 50, self.styles['BodyTextStyle']))
        self.story.append(Spacer(1, 0.2*inch))

    def add_itinerary_day_alternating(self, day, title, description, hotel, gallery_urls, index):
        """Add itinerary day with alternating layout and background image"""
        
        # Get the first image from gallery to use as background
        bg_image = None
        if gallery_urls and len(gallery_urls) > 0:
            bg_image = download_image(gallery_urls[0])

        # Add day title
        self.story.append(Paragraph(f"✨ DAY {day}: {title}", self.styles['DayTitle']))
        self.story.append(Spacer(1, 0.1*inch))

        # Clean description and extract bullet points
        clean_desc = clean_html(description)

        lines = []
        if '<li>' in description or '•' in description:
            items = re.findall(r'<li>(.*?)</li>', description)
            if items:
                for item in items[:5]:
                    clean_item = clean_html(item)
                    if clean_item and len(clean_item) > 10:
                        lines.append(f"• {clean_item[:150]}")
            else:
                for line in clean_desc.split('\n'):
                    line = line.strip()
                    if line and len(line) > 10:
                        if line.startswith('•') or line.startswith('-'):
                            lines.append(line[:200])
                        else:
                            lines.append(f"• {line[:200]}")
        else:
            lines = [clean_desc[:300] + "..." if len(clean_desc) > 300 else clean_desc]

        text_content = []
        for line in lines[:4]:
            text_content.append(Paragraph(line, self.styles['BodyTextStyle']))

        if hotel:
            text_content.append(Spacer(1, 0.05*inch))
            text_content.append(Paragraph(f"🏨 <b>Hotel:</b> {hotel}", self.styles['BodyTextStyle']))

        # Create the background frame
        frame = BackgroundImageFrame(bg_image, 6.5*inch, 2.5*inch, text_content, index % 2 == 0)
        self.story.append(frame)
        self.story.append(Spacer(1, 0.2*inch))

    def add_inclusions_exclusions(self, inclusions, exclusions):
        """Add inclusions and exclusions in two columns"""

        max_len = max(len(inclusions), len(exclusions))
        inclusions += [''] * (max_len - len(inclusions))
        exclusions += [''] * (max_len - len(exclusions))

        data = []
        data.append([
            Paragraph("<b>✅ WHAT'S INCLUDED</b>", self.styles['Subheading']),
            Paragraph("<b>❌ WHAT'S NOT INCLUDED</b>", self.styles['Subheading'])
        ])

        for inc, exc in zip(inclusions[:15], exclusions[:15]):
            inc_para = Paragraph(f"• {inc}", self.styles['BodyTextStyle']) if inc else Paragraph("", self.styles['BodyTextStyle'])
            exc_para = Paragraph(f"• {exc}", self.styles['BodyTextStyle']) if exc else Paragraph("", self.styles['BodyTextStyle'])
            data.append([inc_para, exc_para])

        table = Table(data, colWidths=[3*inch, 3*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16213e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ]))

        self.story.append(table)
        self.story.append(Spacer(1, 0.3*inch))

    def add_contact_section(self, email, phone, package_name):
        """Add contact section with gradient background"""

        contact_data = [
            [Paragraph(f"<b>{package_name}</b>", self.styles['Subheading'])],
            [Paragraph(f"📧 {email} | 📞 {phone}", self.styles['ContactTextStyle'])],
            [Paragraph("For booking assistance, please contact our support team", self.styles['BodyTextStyle'])],
            [Paragraph(f"Generated on: {datetime.now().strftime('%d %B %Y at %H:%M')}", self.styles['BodyTextStyle'])]
        ]

        table = Table(contact_data, colWidths=[6.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#16213e')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, 0), 16),
            ('FONTSIZE', (0, 1), (-1, 1), 14),
            ('FONTSIZE', (0, 2), (-1, 2), 11),
            ('FONTSIZE', (0, 3), (-1, 3), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ]))

        self.story.append(table)

    def build(self):
        """Build the PDF document"""
        self.doc.build(self.story)


def generate_package_pdf(package, user_info=None):
    """Generate stunning PDF for package"""
    try:
        os.makedirs("generated_pdfs", exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pkg_name = package.get('package_name', 'Package')[:30]
        pkg_name_clean = "".join(c for c in pkg_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"generated_pdfs/{pkg_name_clean}_{timestamp}.pdf"

        pdf = StyledPDF(filename)

        package_name = package.get('package_name', 'Travel Package')
        package_price = package.get('package_price', 'N/A')
        if isinstance(package_price, str):
            package_price = package_price.replace('₹', '').strip()

        duration = package.get('duration', {'days': 0, 'nights': 0})
        locations = package.get('locations', [])

        pdf.add_cover_page(package_name, package_price, duration, locations)
        pdf.story.append(PageBreak())

        pdf.add_section_header("ITINERARY", "📅")

        itinerary = package.get('itinerary', [])
        for idx, day in enumerate(itinerary):
            day_num = day.get('day', idx + 1)
            title = day.get('title', f'Day {day_num}')
            description = day.get('description', '')
            hotel = day.get('hotel', '')
            gallery = day.get('gallery', [])  # This picks the gallery images from each itinerary day
            
            pdf.add_itinerary_day_alternating(day_num, title, description, hotel, gallery, idx)

        pdf.story.append(PageBreak())

        pdf.add_section_header("INCLUSIONS & EXCLUSIONS", "📋")

        inclusions = package.get('inclusion', [])
        exclusions = package.get('exclusion', [])

        clean_inclusions = [clean_html(inc) for inc in inclusions if inc and clean_html(inc)]
        clean_exclusions = [clean_html(exc) for exc in exclusions if exc and clean_html(exc)]

        pdf.add_inclusions_exclusions(clean_inclusions, clean_exclusions)

        vehicles = package.get('vehicles', [])
        activities = package.get('activities', [])

        if vehicles or activities:
            pdf.story.append(PageBreak())
            pdf.add_section_header("VEHICLES & ACTIVITIES", "🚗")

            veh_act_data = []
            veh_act_data.append([
                Paragraph("<b>🚗 VEHICLES</b>", pdf.styles['Subheading']),
                Paragraph("<b>🎯 ACTIVITIES</b>", pdf.styles['Subheading'])
            ])

            max_len = max(len(vehicles), len(activities))
            vehicles_extended = vehicles + [''] * (max_len - len(vehicles))
            activities_extended = activities + [''] * (max_len - len(activities))

            for veh, act in zip(vehicles_extended[:10], activities_extended[:10]):
                veh_para = Paragraph(f"• {veh}", pdf.styles['BodyTextStyle']) if veh else Paragraph("", pdf.styles['BodyTextStyle'])
                act_para = Paragraph(f"• {act}", pdf.styles['BodyTextStyle']) if act else Paragraph("", pdf.styles['BodyTextStyle'])
                veh_act_data.append([veh_para, act_para])

            table = Table(veh_act_data, colWidths=[3.2*inch, 3.2*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16213e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
            ]))

            pdf.story.append(table)
            pdf.story.append(Spacer(1, 0.3*inch))

        email = "himmanavofficial@gmail.com"
        phone = "9459679357"

        if user_info:
            if user_info.get('email'):
                email = user_info.get('email')
            if user_info.get('number') or user_info.get('phone'):
                phone = user_info.get('number') or user_info.get('phone')

        pdf.add_contact_section(email, phone, package_name)

        pdf.build()

        print(f"✅ PDF generated: {filename}")
        return filename

    except Exception as e:
        print(f"❌ PDF generation error: {e}")
        import traceback
        traceback.print_exc()
        return None


def upload_pdf_to_whatsapp(pdf_path):
    """Upload PDF to WhatsApp Cloud API and get media ID"""
    try:
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/media"

        with open(pdf_path, 'rb') as f:
            files = {
                'file': (os.path.basename(pdf_path), f, 'application/pdf'),
                'messaging_product': (None, 'whatsapp'),
                'type': (None, 'application/pdf')
            }
            headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}
            response = requests.post(url, headers=headers, files=files)

            if response.status_code == 200:
                media_id = response.json().get('id')
                print(f"✅ PDF uploaded, Media ID: {media_id}")
                return media_id
            else:
                print(f"❌ Upload failed: {response.text}")
                return None

    except Exception as e:
        print(f"❌ Upload error: {e}")
        return None


def send_pdf_via_whatsapp(to_phone, pdf_path, caption=""):
    """Send PDF file to WhatsApp user"""
    try:
        media_id = upload_pdf_to_whatsapp(pdf_path)

        if not media_id:
            return None

        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "document",
            "document": {
                "id": media_id,
                "caption": caption or "📄 Your travel package details",
                "filename": os.path.basename(pdf_path)
            }
        }

        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 200:
            print(f"✅ PDF sent successfully to {to_phone}")
            return response.json()
        else:
            print(f"❌ Failed to send PDF: {response.text}")
            return None

    except Exception as e:
        print(f"❌ Send PDF error: {e}")