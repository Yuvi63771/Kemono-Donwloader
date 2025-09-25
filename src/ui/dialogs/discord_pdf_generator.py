import os
import re
import datetime
import time
try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True

    class PDF(FPDF):
        """Custom PDF class for Discord chat logs."""
        def __init__(self, server_name, channel_name, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.server_name = server_name
            self.channel_name = channel_name
            self.default_font_family = 'DejaVu' # Can be changed to Arial if font fails

        def header(self):
            if self.page_no() == 1:
                return # No header on the title page
            self.set_font(self.default_font_family, '', 8)
            self.cell(0, 10, f'{self.server_name} - #{self.channel_name}', 0, 0, 'L')
            self.cell(0, 10, 'Page ' + str(self.page_no()), 0, 0, 'R')
            self.ln(10)

        def footer(self):
            pass # No footer needed, header has page number

except ImportError:
    FPDF_AVAILABLE = False
    FPDF = None 
    PDF = None

def create_pdf_from_discord_messages(messages_data, server_name, channel_name, output_filename, font_path, logger=print, cancellation_event=None, pause_event=None):
    """
    Creates a single PDF from a list of Discord message objects, formatted as a chat log.
    UPDATED to include clickable links for attachments and embeds.
    """
    if not FPDF_AVAILABLE:
        logger("❌ PDF Creation failed: 'fpdf2' library is not installed.")
        return False

    if not messages_data:
        logger("   No messages were found or fetched to create a PDF.")
        return False

    # --- FIX: This helper function now correctly accepts and checks the event objects ---
    def check_events(c_event, p_event):
        """Helper to safely check for pause and cancel events."""
        if c_event and hasattr(c_event, 'is_cancelled') and c_event.is_cancelled:
            return True # Stop
        if p_event and hasattr(p_event, 'is_paused'):
            while p_event.is_paused:
                time.sleep(0.5)
                if c_event and hasattr(c_event, 'is_cancelled') and c_event.is_cancelled:
                    return True
        return False

    logger("   Sorting messages by date (oldest first)...")
    messages_data.sort(key=lambda m: m.get('published', m.get('timestamp', '')))

    pdf = PDF(server_name, channel_name)
    default_font_family = 'DejaVu'
    
    try:
        bold_font_path = font_path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
        if not os.path.exists(font_path) or not os.path.exists(bold_font_path):
            raise RuntimeError("Font files not found")
        
        pdf.add_font('DejaVu', '', font_path, uni=True)
        pdf.add_font('DejaVu', 'B', bold_font_path, uni=True)
    except Exception as font_error:
        logger(f"   ⚠️ Could not load DejaVu font: {font_error}. Falling back to Arial.")
        default_font_family = 'Arial'
        pdf.default_font_family = 'Arial'
    
    # --- Title Page ---
    pdf.add_page()
    pdf.set_font(default_font_family, 'B', 24)
    pdf.cell(w=0, h=20, text="Discord Chat Log", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font(default_font_family, '', 16)
    pdf.cell(w=0, h=10, text=f"Server: {server_name}", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.cell(w=0, h=10, text=f"Channel: #{channel_name}", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font(default_font_family, '', 10)
    pdf.cell(w=0, h=10, text=f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.cell(w=0, h=10, text=f"Total Messages: {len(messages_data)}", align='C', new_x="LMARGIN", new_y="NEXT")
    
    pdf.add_page()
    
    logger(f"   Starting PDF creation with {len(messages_data)} messages...")

    for i, message in enumerate(messages_data):
        # --- FIX: Pass the event objects to the helper function ---
        if i % 50 == 0:
            if check_events(cancellation_event, pause_event):
                logger("   PDF generation cancelled by user.")
                return False

        author = message.get('author', {}).get('global_name') or message.get('author', {}).get('username', 'Unknown User')
        timestamp_str = message.get('published', message.get('timestamp', ''))
        content = message.get('content', '')
        attachments = message.get('attachments', [])
        embeds = message.get('embeds', [])

        try:
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str[:-1] + '+00:00'
            dt_obj = datetime.datetime.fromisoformat(timestamp_str)
            formatted_timestamp = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            formatted_timestamp = timestamp_str

        if i > 0:
            pdf.ln(2)
            pdf.set_draw_color(200, 200, 200)
            pdf.cell(0, 0, '', border='T')
            pdf.ln(2)

        pdf.set_font(default_font_family, 'B', 11)
        pdf.write(5, f"{author} ")
        pdf.set_font(default_font_family, '', 9)
        pdf.set_text_color(128, 128, 128)
        pdf.write(5, f"({formatted_timestamp})")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(6)

        if content:
            pdf.set_font(default_font_family, '', 10)
            pdf.multi_cell(w=0, h=5, text=content)
        
        if attachments or embeds:
            pdf.ln(1)
            pdf.set_font(default_font_family, '', 9)
            pdf.set_text_color(22, 119, 219)

            for att in attachments:
                file_name = att.get('filename', 'untitled')
                full_url = att.get('url', '#')
                pdf.write(5, text=f"[Attachment: {file_name}]", link=full_url)
                pdf.ln()

            for embed in embeds:
                embed_url = embed.get('url', 'no url')
                pdf.write(5, text=f"[Embed: {embed_url}]", link=embed_url)
                pdf.ln()

            pdf.set_text_color(0, 0, 0)

    if check_events(cancellation_event, pause_event):
        logger("   PDF generation cancelled by user before final save.")
        return False

    try:
        pdf.output(output_filename)
        logger(f"✅ Successfully created Discord chat log PDF: '{os.path.basename(output_filename)}'")
        return True
    except Exception as e:
        logger(f"❌ A critical error occurred while saving the final PDF: {e}")
        return False