# # app.py
# from flask import Flask, request, jsonify, render_template, session
# from bot import process_message
# import os
# from dotenv import load_dotenv
# load_dotenv('.env')
# SECRET_KEY =os.getenv('SECRET_KEY')
# OWNER_PHONE=os.getenv('OWNER_PHONE')
# DEBUG_MODE=os.getenv('DEBUG_MODE')
# import uuid

# app = Flask(__name__)
# app.secret_key = SECRET_KEY

 
# conversation_states = {}

# @app.route("/")
# def home():
#     if "session_id" not in session:
#         session["session_id"] = str(uuid.uuid4())
#         conversation_states[session["session_id"]] = {
#             "step": "greeting",
#             "context": {},
#             "packages": []
#         }
#     return render_template("index.html")

# @app.route("/chat", methods=["POST"])
# def chat():
#     try:
#         data = request.get_json()
#         user_message = data.get("message", "").strip()
#         session_id = session.get("session_id", "default")
        
       
#         if session_id not in conversation_states:
#             conversation_states[session_id] = {
#                 "step": "greeting",
#                 "context": {},
#                 "packages": []
#             }
        
#         state = conversation_states[session_id]
        
#         print("\n" + "="*50)
#         print(f"💬 Session: {session_id}")
#         print(f"👤 User: {user_message}")
#         print(f"📍 Step: {state.get('step')}")
        
       
#         response = process_message(user_message, OWNER_PHONE, state)
        
         
#         if response.get("new_state"):
#             conversation_states[session_id].update(response["new_state"])
        
#         print(f"🤖 Bot: {response.get('content', '')[:100]}")
#         print("="*50 + "\n")
        
#         return jsonify({
#             "success": True,
#             "type": response.get("type", "text"),
#             "content": response.get("content", ""),
#             "buttons": response.get("buttons", [])
#         })
        
#     except Exception as e:
#         print(f"❌ Chat Error: {e}")
#         import traceback
#         traceback.print_exc()
#         return jsonify({
#             "success": False,
#             "type": "text",
#             "content": "⚠️ Sorry, something went wrong. Please try again."
#         }), 500

# @app.route("/clear", methods=["POST"])
# def clear_history():
#     session_id = session.get("session_id", "default")
#     if session_id in conversation_states:
#         conversation_states[session_id] = {
#             "step": "greeting",
#             "context": {},
#             "packages": []
#         }
#     return jsonify({"success": True})

# if __name__ == "__main__":
#     print("🚀 Travel Bot Starting...")

#     port = int(os.environ.get("PORT", 5000))  
#     debug = str(DEBUG_MODE).lower() == "true"

#     app.run(host="0.0.0.0", port=port, debug=debug)



 
 """
app.py - Flask Web Chat Interface
Supports: step-by-step flow, PDF download, close chat
"""

from flask import Flask, request, jsonify, render_template, session, send_file
from bot import process_message, generate_full_package_details_for_chat
import os
import uuid
import io
from dotenv import load_dotenv
load_dotenv('.env')

SECRET_KEY = os.getenv('SECRET_KEY')
OWNER_PHONE = os.getenv('OWNER_PHONE')
AGENT_PHONE = os.getenv('AGENT_PHONE')
DEBUG_MODE = os.getenv('DEBUG_MODE')

app = Flask(__name__)
app.secret_key = SECRET_KEY

# In-memory conversation states
conversation_states = {}


# ══════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/")
def home():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
        conversation_states[session["session_id"]] = {
            "step": "greeting",
            "context": {},
            "packages": []
        }
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()
        session_id = session.get("session_id", "default")

        if session_id not in conversation_states:
            conversation_states[session_id] = {
                "step": "greeting",
                "context": {},
                "packages": []
            }

        state = conversation_states[session_id]

        print(f"\n{'='*50}")
        print(f"💬 Session: {session_id}")
        print(f"👤 User: {user_message}")
        print(f"📍 Step: {state.get('step')}")

        response = process_message(user_message, OWNER_PHONE, state)

        # Update state
        if response.get("new_state"):
            conversation_states[session_id].update(response["new_state"])

        # Notify agent if chat closed
        if response.get("notify_agent") and response.get("agent_message"):
            _notify_agent_email_or_log(response["agent_message"], session_id, state)

        print(f"🤖 Bot: {response.get('content', '')[:100]}")
        print(f"{'='*50}\n")

        return jsonify({
            "success": True,
            "type": response.get("type", "text"),
            "content": response.get("content", ""),
            "buttons": response.get("buttons", []),
            # Tell frontend if PDF download should be offered
            "show_pdf": response.get("type") == "buttons" and
                        conversation_states[session_id].get("context", {}).get("selected_package") is not None,
            "notify_agent": response.get("notify_agent", False)
        })

    except Exception as e:
        print(f"❌ Chat Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "type": "text",
            "content": "⚠️ Something went wrong. Please try again."
        }), 500


@app.route("/download-pdf", methods=["GET"])
def download_pdf():
    """
    Generate and return a PDF of the selected package details.
    Uses reportlab to create the PDF in memory.
    """
    session_id = session.get("session_id", "default")
    state = conversation_states.get(session_id, {})
    context = state.get("context", {})
    selected_package = context.get("selected_package")

    if not selected_package:
        return jsonify({"error": "No package selected"}), 400

    try:
        pdf_bytes = _generate_pdf(selected_package, context)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"travel_package_{selected_package.get('id', 'details')}.pdf"
        )
    except Exception as e:
        print(f"❌ PDF Error: {e}")
        return jsonify({"error": "Could not generate PDF"}), 500


@app.route("/clear", methods=["POST"])
def clear_history():
    session_id = session.get("session_id", "default")
    if session_id in conversation_states:
        conversation_states[session_id] = {
            "step": "greeting",
            "context": {},
            "packages": []
        }
    return jsonify({"success": True})


# ══════════════════════════════════════════════════════════════
# PDF GENERATOR
# ══════════════════════════════════════════════════════════════

def _generate_pdf(package, user_context=None):
    """
    Generate a PDF for the selected package.
    Requires: pip install reportlab
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        import re

        def clean(text):
            if not text:
                return ""
            text = str(text)
            text = re.sub(r'&amp;', '&', text)
            text = re.sub(r'&#\d+;', '', text)
            text = re.sub(r'<[^>]+>', '', text)
            return text.strip()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=2*cm, leftMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)

        styles = getSampleStyleSheet()
        story = []

        # Title style
        title_style = ParagraphStyle('Title', parent=styles['Title'],
                                     fontSize=20, spaceAfter=6,
                                     textColor=colors.HexColor('#1a237e'))
        heading_style = ParagraphStyle('Heading', parent=styles['Heading2'],
                                       fontSize=13, spaceAfter=4,
                                       textColor=colors.HexColor('#283593'))
        normal_style = styles['Normal']
        normal_style.fontSize = 10

        # Header
        story.append(Paragraph(f"🌍 Travel Package Details", title_style))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1a237e')))
        story.append(Spacer(1, 0.3*cm))

        # Package Info Table
        name = clean(package.get('package_name', 'Package'))
        price = package.get('package_price', 'N/A')
        pkg_type = package.get('package_type', 'Standard')
        pkg_cat = package.get('package_category', 'Tour')
        locations = package.get('locations', [])

        story.append(Paragraph(name, title_style))
        story.append(Spacer(1, 0.2*cm))

        info_data = [
            ['💰 Price', f'₹{price}'],
            ['🏷️ Type', pkg_type],
            ['📂 Category', pkg_cat],
            ['📍 Destinations', ', '.join(locations) if locations else 'Various'],
        ]

        # Add user context if available
        if user_context:
            if user_context.get('travel_dates'):
                info_data.append(['📅 Travel Dates', user_context['travel_dates']])
            if user_context.get('travellers'):
                info_data.append(['👨‍👩‍👧‍👦 Travellers', user_context['travellers']])
            if user_context.get('travel_days'):
                info_data.append(['🌙 Duration', user_context['travel_days']])
            if user_context.get('pickup_drop'):
                info_data.append(['📍 Pickup/Drop', user_context['pickup_drop']])

        info_table = Table(info_data, colWidths=[4*cm, 13*cm])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8eaf6')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (1, 0), (1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.5*cm))

        # Itinerary
        itinerary = package.get('itinerary', [])
        if itinerary:
            story.append(Paragraph("📅 Itinerary", heading_style))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
            story.append(Spacer(1, 0.2*cm))
            for i, day in enumerate(itinerary, 1):
                title = day.get('title', f'Day {i}')
                desc = clean(re.sub(r'<[^>]+>', '', day.get('description', '')))
                hotel = clean(day.get('hotel', ''))
                story.append(Paragraph(f"<b>Day {i}: {title}</b>", normal_style))
                if desc:
                    story.append(Paragraph(f"  📍 {desc}", normal_style))
                if hotel:
                    story.append(Paragraph(f"  🏨 Hotel: {hotel}", normal_style))
                story.append(Spacer(1, 0.15*cm))
            story.append(Spacer(1, 0.3*cm))

        # Activities
        activities = package.get('activities', [])
        if activities:
            story.append(Paragraph("🎯 Activities", heading_style))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
            for act in activities:
                story.append(Paragraph(f"  • {act}", normal_style))
            story.append(Spacer(1, 0.3*cm))

        # Inclusions
        inclusions = package.get('inclusion', [])
        if inclusions:
            story.append(Paragraph("✅ Inclusions", heading_style))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
            for inc in inclusions:
                story.append(Paragraph(f"  ✓ {clean(inc)}", normal_style))
            story.append(Spacer(1, 0.3*cm))

        # Exclusions
        exclusions = package.get('exclusion', [])
        if exclusions:
            story.append(Paragraph("❌ Exclusions", heading_style))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
            for exc in exclusions:
                story.append(Paragraph(f"  ✗ {clean(exc)}", normal_style))
            story.append(Spacer(1, 0.3*cm))

        # Footer
        story.append(Spacer(1, 0.5*cm))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1a237e')))
        story.append(Paragraph(
            "Our Chief Executive will contact you soon. Thank you for choosing us! 🌟",
            ParagraphStyle('Footer', parent=normal_style,
                           alignment=TA_CENTER, textColor=colors.grey)
        ))

        doc.build(story)
        return buffer.getvalue()

    except ImportError:
        # Fallback: plain text PDF-like response if reportlab not installed
        raise Exception("reportlab not installed. Run: pip install reportlab")


# ══════════════════════════════════════════════════════════════
# AGENT NOTIFICATION (Web Version)
# ══════════════════════════════════════════════════════════════

def _notify_agent_email_or_log(agent_message, session_id, state):
    """
    For web version: log the inquiry (or send via WhatsApp API if configured).
    For WhatsApp bot, notification is handled in message_handler.py.
    """
    print(f"\n{'🔔'*20}")
    print("AGENT NOTIFICATION:")
    print(agent_message)
    print(f"{'🔔'*20}\n")

    # Optional: send to agent via WhatsApp if AGENT_PHONE is set
    if AGENT_PHONE:
        try:
            from chats.whatsapp_sender import send_whatsapp_message
            send_whatsapp_message(AGENT_PHONE, {
                "type": "text",
                "content": agent_message
            })
            print(f"✅ Agent notified at {AGENT_PHONE}")
        except Exception as e:
            print(f"⚠️ Could not WhatsApp agent: {e}")


# ══════════════════════════════════════════════════════════════
# RUN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🚀 Travel Bot Web Starting...")
    port = int(os.environ.get("PORT", 5000))
    debug = str(DEBUG_MODE).lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)