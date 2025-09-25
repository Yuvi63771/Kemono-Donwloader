import os
import re
try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True

    # --- FIX: Move the class definition inside the try block ---
    class PDF(FPDF):
        """Custom PDF class to handle headers and footers."""
        def header(self):
            pass 

        def footer(self):
            self.set_y(-15)
            if self.font_family:
                 self.set_font(self.font_family, '', 8)
            else:
                 self.set_font('Arial', '', 8)
            self.cell(0, 10, 'Page ' + str(self.page_no()), 0, 0, 'C')

except ImportError:
    FPDF_AVAILABLE = False
    # If the import fails, FPDF and PDF will not be defined,
    # but the program won't crash here.
    FPDF = None 
    PDF = None

def strip_html_tags(text):
    if not text:
        return ""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)

def create_single_pdf_from_content(posts_data, output_filename, font_path, logger=print):
    """
    Creates a single, continuous PDF, correctly formatting both descriptions and comments.
    """
    if not FPDF_AVAILABLE:
        logger("❌ PDF Creation failed: 'fpdf2' library is not installed. Please run: pip install fpdf2")
        return False

    if not posts_data:
        logger("   No text content was collected to create a PDF.")
        return False

    pdf = PDF()
    default_font_family = 'DejaVu'
    
    bold_font_path = ""
    if font_path:
        bold_font_path = font_path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")

    try:
        if not os.path.exists(font_path): raise RuntimeError(f"Font file not found: {font_path}")
        if not os.path.exists(bold_font_path): raise RuntimeError(f"Bold font file not found: {bold_font_path}")
        
        pdf.add_font('DejaVu', '', font_path, uni=True)
        pdf.add_font('DejaVu', 'B', bold_font_path, uni=True)
    except Exception as font_error:
        logger(f"   ⚠️ Could not load DejaVu font: {font_error}. Falling back to Arial.")
        default_font_family = 'Arial'
    
    pdf.add_page()

    logger(f"   Starting continuous PDF creation with content from {len(posts_data)} posts...")

    for i, post in enumerate(posts_data):
        if i > 0:
            # This ensures every post after the first gets its own page.
            pdf.add_page()

        pdf.set_font(default_font_family, 'B', 16)
        pdf.multi_cell(w=0, h=10, txt=post.get('title', 'Untitled Post'), align='L')
        pdf.ln(5)

        if 'comments' in post and post['comments']:
            comments_list = post['comments']
            for comment_index, comment in enumerate(comments_list):
                user = comment.get('commenter_name', 'Unknown User')
                timestamp = comment.get('published', 'No Date')
                body = strip_html_tags(comment.get('content', ''))

                pdf.set_font(default_font_family, '', 10)
                pdf.write(8, "Comment by: ")
                if user is not None:
                    pdf.set_font(default_font_family, 'B', 10)
                    pdf.write(8, str(user))
                
                pdf.set_font(default_font_family, '', 10)
                pdf.write(8, f" on {timestamp}")
                pdf.ln(10)

                pdf.set_font(default_font_family, '', 11)
                pdf.multi_cell(w=0, h=7, txt=body)
                
                if comment_index < len(comments_list) - 1:
                    pdf.ln(3)
                    pdf.cell(w=0, h=0, border='T')
                    pdf.ln(3)
        elif 'content' in post:
            pdf.set_font(default_font_family, '', 12)
            pdf.multi_cell(w=0, h=7, txt=post.get('content', 'No Content'))
    
    try:
        pdf.output(output_filename)
        logger(f"✅ Successfully created single PDF: '{os.path.basename(output_filename)}'")
        return True
    except Exception as e:
        logger(f"❌ A critical error occurred while saving the final PDF: {e}")
        return False
