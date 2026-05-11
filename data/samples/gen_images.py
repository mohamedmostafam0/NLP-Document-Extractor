import os
from PIL import Image, ImageDraw, ImageFont

def generate_business_card():
    # Create a blank white image
    img = Image.new('RGB', (600, 350), color = (255, 255, 255))
    d = ImageDraw.Draw(img)
    
    # Try to load a generic sans-serif font
    try:
        font_large = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
        font_medium = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 18)
    except IOError:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Draw Text
    d.text((40, 40), "Richard Hendricks", fill=(0, 0, 0), font=font_large)
    d.text((40, 90), "CEO & Founder", fill=(100, 100, 100), font=font_medium)
    
    d.line([(40, 130), (560, 130)], fill=(200, 200, 200), width=2)
    
    d.text((40, 160), "Pied Piper Inc.", fill=(0, 0, 0), font=font_medium)
    d.text((40, 190), "5230 Penfield Ave\nWoodland Hills, CA 91364", fill=(50, 50, 50), font=font_small)
    
    d.text((320, 160), "Mobile: (555) 867-5309", fill=(50, 50, 50), font=font_small)
    d.text((320, 190), "Email: richard@piedpiper.com", fill=(50, 50, 50), font=font_small)
    d.text((320, 220), "Web: https://www.piedpiper.com", fill=(50, 50, 50), font=font_small)
    
    # Save it
    img.save("/app/data/samples/business_card.png")
    img.save("/app/data/samples/business_card.pdf", "PDF", resolution=100.0)


def generate_medical_report():
    img = Image.new('RGB', (850, 1100), color = (255, 255, 255))
    d = ImageDraw.Draw(img)
    
    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
        font_bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
        font_norm = ImageFont.truetype("DejaVuSans.ttf", 18)
    except IOError:
        font_title = ImageFont.load_default()
        font_bold = ImageFont.load_default()
        font_norm = ImageFont.load_default()

    content = [
        ("MERCY GENERAL HOSPITAL - PATIENT ENCOUNTER REPORT", font_title),
        ("", font_norm),
        ("Patient Name: Sarah Jenkins", font_norm),
        ("Date of Birth: 05/14/1982", font_norm),
        ("Date of Visit: October 12, 2025", font_norm),
        ("Provider: Dr. Gregory House, MD", font_norm),
        ("", font_norm),
        ("VITALS", font_bold),
        ("BP: 120/80    HR: 72 bpm    Temp: 98.6 F    Weight: 145 lbs", font_norm),
        ("", font_norm),
        ("REASON FOR VISIT", font_bold),
        ("Patient complains of persistent migraine and nausea over the past 3 days.", font_norm),
        ("", font_norm),
        ("ASSESSMENT & DIAGNOSES", font_bold),
        ("1. Acute Migraine without aura", font_norm),
        ("2. Mild dehydration", font_norm),
        ("", font_norm),
        ("MEDICATIONS PRESCRIBED", font_bold),
        ("- Sumatriptan 50mg tablets, take one at onset of migraine", font_norm),
        ("- Ibuprofen 400mg every 6 hours as needed", font_norm),
        ("- Zofran 4mg for nausea", font_norm)
    ]
    
    y_text = 60
    for text, font in content:
        d.text((60, y_text), text, fill=(0, 0, 0), font=font)
        y_text += 40

    img.save("/app/data/samples/medical_report.png")
    img.save("/app/data/samples/medical_report.pdf", "PDF", resolution=100.0)

if __name__ == "__main__":
    generate_business_card()
    generate_medical_report()
    print("Generated PNG and PDF samples in /app/data/samples/")
