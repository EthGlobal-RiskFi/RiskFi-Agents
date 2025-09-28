#!/usr/bin/env python3
"""
Markdown to PDF Converter with Image Support (Cross-Platform)

This script converts a Markdown file with embedded images to PDF using multiple backends.
Automatically selects the best available PDF generation method for your system.

Dependencies:
    Option 1 (Recommended): pip install markdown pdfkit
    Option 2: pip install markdown reportlab
    Option 3: pip install markdown playwright (requires: playwright install)

For pdfkit on Windows, you also need to install wkhtmltopdf:
https://wkhtmltopdf.org/downloads.html

Usage:
    python md_to_pdf.py input.md output.pdf
"""

import os
import sys
import re
import markdown
from pathlib import Path
import base64
import mimetypes
from urllib.parse import urljoin
from urllib.request import pathname2url


class MarkdownToPDFConverter:
    def __init__(self):
        self.available_backends = self._check_available_backends()
        if not self.available_backends:
            raise ImportError("No PDF generation backend available. Please install one of: pdfkit, reportlab, or playwright")
    
    def _check_available_backends(self):
        """Check which PDF generation backends are available"""
        backends = []
        
        # Check pdfkit + wkhtmltopdf
        try:
            import pdfkit
            # Test if wkhtmltopdf is available
            pdfkit.configuration()
            backends.append('pdfkit')
        except (ImportError, OSError):
            pass
        
        # Check reportlab
        try:
            import reportlab
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter, A4
            backends.append('reportlab')
        except ImportError:
            pass
        
        # Check playwright
        try:
            import playwright
            from playwright.sync_api import sync_playwright
            backends.append('playwright')
        except ImportError:
            pass
        
        return backends
    
    def resolve_image_paths(self, md_content, md_file_path, embed_images=True):
        """
        Resolve relative image paths in markdown content.
        
        Args:
            embed_images: If True, convert to data URIs. If False, convert to file:// URLs
        """
        md_dir = Path(md_file_path).parent
        
        # Pattern to match markdown image syntax: ![alt](path)
        img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        
        def replace_image_path(match):
            alt_text = match.group(1)
            img_path = match.group(2)
            
            # Skip if it's already a URL or data URI
            if img_path.startswith(('http://', 'https://', 'data:', 'file://')):
                return match.group(0)
            
            # Resolve relative path
            if not os.path.isabs(img_path):
                abs_img_path = md_dir / img_path
            else:
                abs_img_path = Path(img_path)
            
            if abs_img_path.exists():
                if embed_images:
                    # Convert to data URI
                    try:
                        with open(abs_img_path, 'rb') as img_file:
                            img_data = img_file.read()
                            mime_type = mimetypes.guess_type(str(abs_img_path))[0]
                            if mime_type:
                                encoded_data = base64.b64encode(img_data).decode('utf-8')
                                data_uri = f"data:{mime_type};base64,{encoded_data}"
                                return f'![{alt_text}]({data_uri})'
                    except Exception as e:
                        print(f"Warning: Could not embed image {abs_img_path}: {e}")
                else:
                    # Convert to file:// URL for local file access
                    file_url = abs_img_path.as_uri()
                    return f'![{alt_text}]({file_url})'
            else:
                print(f"Warning: Image not found: {abs_img_path}")
            
            return match.group(0)  # Return original if processing fails
        
        return re.sub(img_pattern, replace_image_path, md_content)
    
    def create_html_template(self, html_content, title="Converted from Markdown"):
        """Create a complete HTML document with CSS styling"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>{title}</title>
            <style>
                @page {{
                    margin: 2cm;
                    size: A4;
                }}
                
                body {{
                    font-family: 'Arial', 'Helvetica', sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 100%;
                    margin: 0;
                    padding: 20px;
                }}
                
                h1, h2, h3, h4, h5, h6 {{
                    color: #2c3e50;
                    margin-top: 1.5em;
                    margin-bottom: 0.5em;
                }}
                
                h1 {{
                    font-size: 2em;
                    border-bottom: 2px solid #3498db;
                    padding-bottom: 0.3em;
                }}
                
                h2 {{
                    font-size: 1.5em;
                    border-bottom: 1px solid #bdc3c7;
                    padding-bottom: 0.2em;
                }}
                
                img {{
                    max-width: 100%;
                    height: auto;
                    display: block;
                    margin: 1em auto;
                    border-radius: 4px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}
                
                code {{
                    background-color: #f8f9fa;
                    padding: 0.2em 0.4em;
                    border-radius: 3px;
                    font-family: 'Courier New', monospace;
                    font-size: 0.9em;
                }}
                
                pre {{
                    background-color: #f8f9fa;
                    padding: 1em;
                    border-radius: 5px;
                    border-left: 4px solid #3498db;
                    overflow-x: auto;
                    white-space: pre-wrap;
                }}
                
                pre code {{
                    background: none;
                    padding: 0;
                }}
                
                blockquote {{
                    border-left: 4px solid #3498db;
                    margin: 1em 0;
                    padding-left: 1em;
                    color: #7f8c8d;
                    font-style: italic;
                }}
                
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 1em 0;
                }}
                
                table th, table td {{
                    border: 1px solid #ddd;
                    padding: 0.5em;
                    text-align: left;
                }}
                
                table th {{
                    background-color: #f2f2f2;
                    font-weight: bold;
                }}
                
                ul, ol {{
                    padding-left: 2em;
                }}
                
                li {{
                    margin: 0.2em 0;
                }}
                
                a {{
                    color: #3498db;
                    text-decoration: none;
                }}
                
                a:hover {{
                    text-decoration: underline;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
    
    def convert_with_pdfkit(self, html_content, pdf_path):
        """Convert using pdfkit (requires wkhtmltopdf)"""
        import pdfkit
        
        options = {
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'encoding': "UTF-8",
            'no-outline': None,
            'enable-local-file-access': None,
        }
        
        pdfkit.from_string(html_content, str(pdf_path), options=options)
    
    def convert_with_playwright(self, html_content, pdf_path):
        """Convert using playwright (headless browser)"""
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html_content, wait_until='networkidle')
            page.pdf(
                path=str(pdf_path),
                format='A4',
                margin={'top': '2cm', 'right': '2cm', 'bottom': '2cm', 'left': '2cm'},
                print_background=True
            )
            browser.close()
    
    def convert_with_reportlab(self, html_content, pdf_path):
        """Convert using reportlab (basic HTML support)"""
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import inch
        from bs4 import BeautifulSoup
        import io
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Create PDF
        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        # Simple conversion (limited HTML support)
        for element in soup.body.find_all(['h1', 'h2', 'h3', 'p', 'img']):
            if element.name in ['h1', 'h2', 'h3']:
                style = styles['Heading1'] if element.name == 'h1' else styles['Heading2']
                story.append(Paragraph(element.get_text(), style))
                story.append(Spacer(1, 12))
            elif element.name == 'p':
                story.append(Paragraph(element.get_text(), styles['Normal']))
                story.append(Spacer(1, 6))
            elif element.name == 'img':
                src = element.get('src', '')
                if src.startswith('data:'):
                    # Handle base64 images
                    try:
                        header, encoded = src.split(',', 1)
                        data = base64.b64decode(encoded)
                        img = Image(io.BytesIO(data), width=400, height=300)
                        story.append(img)
                        story.append(Spacer(1, 12))
                    except Exception as e:
                        print(f"Warning: Could not process image: {e}")
        
        doc.build(story)
    
    def convert(self, md_file_path, pdf_file_path=None, backend=None):
        """
        Convert Markdown to PDF using the best available backend
        
        Args:
            md_file_path: Path to input Markdown file
            pdf_file_path: Path to output PDF file (optional)
            backend: Specific backend to use ('pdfkit', 'playwright', 'reportlab')
        """
        # Validate input
        md_path = Path(md_file_path)
        if not md_path.exists():
            raise FileNotFoundError(f"Markdown file not found: {md_file_path}")
        
        # Set output path
        if pdf_file_path is None:
            pdf_file_path = md_path.with_suffix('.pdf')
        
        # Select backend
        if backend and backend in self.available_backends:
            selected_backend = backend
        else:
            selected_backend = self.available_backends[0]
        
        print(f"Converting {md_file_path} to {pdf_file_path} using {selected_backend}")
        
        try:
            # Read markdown
            with open(md_file_path, 'r', encoding='utf-8') as file:
                md_content = file.read()
            
            # Process images based on backend
            embed_images = selected_backend != 'pdfkit'  # pdfkit can handle file:// URLs
            md_content = self.resolve_image_paths(md_content, md_file_path, embed_images)
            
            # Convert markdown to HTML
            print("Converting Markdown to HTML...")
            md = markdown.Markdown(extensions=[
                'markdown.extensions.extra',
                'markdown.extensions.codehilite',
                'markdown.extensions.toc',
            ])
            
            html_body = md.convert(md_content)
            html_content = self.create_html_template(html_body)
            
            # Convert to PDF using selected backend
            print(f"Generating PDF with {selected_backend}...")
            
            if selected_backend == 'pdfkit':
                self.convert_with_pdfkit(html_content, pdf_file_path)
            elif selected_backend == 'playwright':
                self.convert_with_playwright(html_content, pdf_file_path)
            elif selected_backend == 'reportlab':
                self.convert_with_reportlab(html_content, pdf_file_path)
            
            print(f"✅ PDF successfully created: {pdf_file_path}")
            return str(pdf_file_path)
            
        except Exception as e:
            print(f"❌ Error converting to PDF: {e}")
            raise


def main():
    """Command line interface"""
    if len(sys.argv) < 2:
        print("Usage: python md_to_pdf.py <input.md> [output.pdf] [backend]")
        print("Backends: pdfkit, playwright, reportlab")
        print("Example: python md_to_pdf.py README.md document.pdf pdfkit")
        sys.exit(1)
    
    md_file = sys.argv[1]
    pdf_file = sys.argv[2] if len(sys.argv) > 2 else None
    backend = sys.argv[3] if len(sys.argv) > 3 else None
    
    try:
        converter = MarkdownToPDFConverter()
        print(f"Available backends: {', '.join(converter.available_backends)}")
        converter.convert(md_file, pdf_file, backend)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


# Convenience function for direct use
def convert_md_to_pdf(md_file_path, pdf_file_path=None, backend=None):
    """Simple function interface"""
    converter = MarkdownToPDFConverter()
    return converter.convert(md_file_path, pdf_file_path, backend)


if __name__ == "__main__":
    main()