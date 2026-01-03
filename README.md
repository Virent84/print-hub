# PrintHub – QR Based Xerox Automation System

PrintHub is a Flask-based web application that automates Xerox/print shop workflows using QR codes.

## Features
- Multi-owner Xerox system
- Owner registration with custom pricing
- Unique QR code per owner
- Customer uploads via phone
- Automatic order queue
- Owner dashboard
- Cross-device support (Laptop + Mobile)

## Tech Stack
- Python (Flask)
- HTML (Jinja templates)
- QR Code generation
- Local network deployment

## How to Run
1. Install Python
2. Install dependencies:
   pip install flask qrcode[pil]
3. Run the app:
   python app.py
4. Open in browser:
   http://<your-ip>:5000

## Note
This is a local MVP. Database, payments, and authentication can be added later.
