import requests
import re
WORDPRESS_API_URL = "https://silver-spoonbill-286441.hostingersite.com"
OWNER_PHONE = "6230097248"

# =========================
# CACHE
# =========================
_cached_packages = None

# Per-user session: stores which package they last viewed
# key = session_id, value = package dict
_user_sessions = {}

def fetch_packages():
    global _cached_packages
    if _cached_packages is not None:
        return _cached_packages
    try:
        url = f"{WORDPRESS_API_URL}/wp-json/hm/v1/packages?phone={OWNER_PHONE}"
        res = requests.get(url, timeout=10)
        data = res.json()
        if data.get("status"):
            _cached_packages = data.get("packages", [])
            return _cached_packages
        return []
    except Exception as e:
        print(f"API Error: {e}")
        return []

# =========================
# CLEAN HTML
# =========================
def clean_html(text):
    text = re.sub(r'<[^>]+>', '', text or '')
    text = text.replace("&amp;", "&").replace("&nbsp;", " ").strip()
    return text

# =========================
# EXTRACT DESTINATION
# =========================
def extract_destination(text, packages):
    t = text.lower()
    all_locations = set()
    for p in packages:
        for loc in p.get("locations", []):
            all_locations.add(loc.lower().strip())
    for loc in sorted(all_locations, key=len, reverse=True):
        if loc in t:
            return loc
    return None

# =========================
# EXTRACT BUDGET
# =========================
def extract_budget(text):
    t = text.lower().replace(",", "")
    patterns = [
        (r'₹\s*(\d+)',      1),
        (r'rs\.?\s*(\d+)',  1),
        (r'(\d+)\s*k\b', 1000),
        (r'under\s*(\d+)',  1),
        (r'within\s*(\d+)', 1),
        (r'below\s*(\d+)',  1),
        (r'upto\s*(\d+)',   1),
        (r'(\d{4,6})',      1),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, t)
        if match:
            val = int(match.group(1)) * multiplier
            if val > 500:
                return val
    return None

# =========================
# DETECT MAIN INTENT
# =========================
def detect_intent(text):
    t = text.lower()
    greet_words = ["hi", "hello", "hey", "hii", "helo", "namaste", "good morning", "good evening","how are you"]
    tour_words  = ["tour", "package", "trip", "travel", "visit", "holiday", "vacation",
                   "suggest", "show", "provide", "give", "batao", "chahiye", "dikhao",
                   "recommend", "plan", "book", "tired", "mood", "relax", "escape", "need"]
    is_greeting = any(g == t.strip() or t.strip().startswith(g) for g in greet_words)
    is_tour     = any(w in t for w in tour_words)
    return is_greeting, is_tour

# =========================
# DETECT FOLLOW-UP QUESTION
# about the current package
# =========================
def detect_followup(text):
    t = text.lower()

    # vehicles / transport
    if any(w in t for w in ["vehicle", "transport", "car", "bus", "bike", "cab",
                             "conveyance", "travel by", "how to reach", "gaadi", "tempo"]):
        return "vehicles"

    # hotel / accommodation
    if any(w in t for w in ["hotel", "stay", "accommodation", "room", "lodge",
                             "night stay", "where stay", "ruk", "thehra"]):
        return "hotels"

    # activities
    if any(w in t for w in ["activit", "adventure", "fun", "do there", "kya kar",
                             "rafting", "camping", "trek", "zoo", "sport"]):
        return "activities"

    # inclusion / facilities
    if any(w in t for w in ["includ", "facilit", "provide", "offer", "cover",
                             "contain", "mil", "diya", "kya milega", "what get",
                             "breakfast", "dinner", "meal", "food", "pickup", "drop"]):
        return "inclusion"

    # exclusion
    if any(w in t for w in ["exclud", "not includ", "extra", "additional",
                             "pay extra", "kya nahi", "bahar", "separately"]):
        return "exclusion"

    # price / cost
    if any(w in t for w in ["price", "cost", "rate", "kitna", "how much",
                             "charge", "fee", "amount", "paisa", "rupee"]):
        return "price"

    # itinerary / day plan
    if any(w in t for w in ["itinerary", "day", "schedule", "plan", "din",
                             "day 1", "day 2", "day by day", "agenda", "program"]):
        return "itinerary"

    # locations
    if any(w in t for w in ["location", "place", "destination", "cover", "visit",
                             "kahan", "where", "jagah", "spot"]):
        return "locations"

    # description / about
    if any(w in t for w in ["about", "detail", "describe", "explain", "tell me",
                             "batao", "kya hai", "what is", "overview", "summary"]):
        return "description"

    return None

# =========================
# ANSWER FOLLOW-UP from saved package
# =========================
def answer_followup(pkg, topic):
    name = pkg.get("package_name", "this package")

    if topic == "vehicles":
        vehicles = pkg.get("vehicles", [])
        if vehicles:
            v_list = "\n".join([f"  🚗 {v}" for v in vehicles])
            return f"🚗 Vehicles available in '{name}':\n{v_list}"
        return f"No vehicle information available for '{name}'."

    elif topic == "hotels":
        itinerary = pkg.get("itinerary", [])
        hotels = list(dict.fromkeys([
            day.get("hotel", "") for day in itinerary if day.get("hotel")
        ]))
        if hotels:
            h_list = "\n".join([f"  🏨 {h}" for h in hotels])
            return f"🏨 Hotels in '{name}':\n{h_list}"
        return f"No hotel info found in '{name}'."

    elif topic == "activities":
        activities = pkg.get("activities", [])
        if activities:
            a_list = "\n".join([f"  🎯 {a}" for a in activities])
            return f"🎯 Activities in '{name}':\n{a_list}"
        return f"No activities listed for '{name}'."

    elif topic == "inclusion":
        inclusion = [clean_html(i) for i in pkg.get("inclusion", [])]
        if inclusion:
            i_list = "\n".join([f"  ✅ {i}" for i in inclusion])
            return f"✅ What's included in '{name}':\n{i_list}"
        return f"No inclusion info for '{name}'."

    elif topic == "exclusion":
        exclusion = [clean_html(e) for e in pkg.get("exclusion", [])]
        if exclusion:
            e_list = "\n".join([f"  ❌ {e}" for e in exclusion])
            return f"❌ Not included in '{name}':\n{e_list}"
        return f"No exclusion info for '{name}'."

    elif topic == "price":
        price = pkg.get("package_price", "N/A")
        return f"💰 Price for '{name}': Rs.{price} per person"

    elif topic == "itinerary":
        itinerary = pkg.get("itinerary", [])
        if itinerary:
            lines = [f"📅 Day-by-day plan for '{name}':"]
            for d, day in enumerate(itinerary, 1):
                title    = day.get("title", "")
                desc     = clean_html(day.get("description", ""))
                hotel    = day.get("hotel", "")
                lines.append(f"\n  Day {d}: {title}")
                if desc:
                    lines.append(f"  📝 {desc}")
                if hotel:
                    lines.append(f"  🏨 Hotel: {hotel}")
            return "\n".join(lines)
        return f"No itinerary available for '{name}'."

    elif topic == "locations":
        locations = pkg.get("locations", [])
        if locations:
            l_list = "\n".join([f"  📍 {l}" for l in locations])
            return f"📍 Places covered in '{name}':\n{l_list}"
        return f"No location info for '{name}'."

    elif topic == "description":
        desc = clean_html(pkg.get("package_description", ""))
        ptype    = pkg.get("package_type", "")
        category = pkg.get("package_category", "")
        return (
            f"📦 About '{name}':\n\n"
            f"  🏷️  Type     : {ptype}\n"
            f"  🗂️  Category : {category}\n\n"
            f"  📝 {desc}"
        )

    return None

# =========================
# FILTER PACKAGES
# =========================
def filter_packages(packages, destination=None, budget=None):
    results = []
    for p in packages:
        try:
            price = float(p.get("package_price", 0) or 0)
        except:
            price = 0
        locations = [loc.lower().strip() for loc in p.get("locations", [])]
        name      = p.get("package_name", "").lower()
        if destination:
            if destination not in locations and destination not in name:
                continue
        if budget is not None:
            if price > budget:
                continue
        results.append(p)
    return results

# =========================
# FORMAT FULL PACKAGE
# =========================
def format_package(p, index):
    name       = p.get("package_name", "N/A")
    price      = p.get("package_price", "N/A")
    ptype      = p.get("package_type", "")
    category   = p.get("package_category", "")
    locations  = ", ".join(p.get("locations", []))
    vehicles   = ", ".join(p.get("vehicles", []))
    activities = ", ".join(p.get("activities", []))
    inclusion  = ", ".join([clean_html(i) for i in p.get("inclusion", [])])
    exclusion  = ", ".join([clean_html(e) for e in p.get("exclusion", [])])
    desc       = clean_html(p.get("package_description", ""))[:150]
    itinerary  = p.get("itinerary", [])

    lines = [
        f"📦 {index}. {name}",
        f"💰 Price      : Rs.{price}",
        f"🏷️  Type       : {ptype}  |  Category: {category}",
        f"📍 Locations  : {locations}",
        f"🚗 Vehicles   : {vehicles}",
        f"🎯 Activities : {activities}",
        f"✅ Includes   : {inclusion}",
        f"❌ Excludes   : {exclusion}",
        f"📝 {desc}...",
    ]
    if itinerary:
        lines.append("📅 Itinerary:")
        for d, day in enumerate(itinerary, 1):
            day_title = day.get("title", "")
            day_desc  = clean_html(day.get("description", ""))
            hotel     = day.get("hotel", "")
            lines.append(f"   Day {d}: {day_title}")
            if day_desc:
                lines.append(f"           {day_desc}")
            if hotel:
                lines.append(f"           🏨 Hotel: {hotel}")
    lines.append("─" * 45)
    return "\n".join(lines)

# =========================
# MAIN BOT
# =========================
def process_message(user_input, session_id="default"):
    if not user_input.strip():
        return "Please type something! 😊"

    packages = fetch_packages()
    if not packages:
        return "⚠️ Could not load packages right now. Please try again later."

    text = user_input.strip()
    is_greeting, is_tour = detect_intent(text)
    destination = extract_destination(text, packages)
    budget      = extract_budget(text)
    followup    = detect_followup(text)

    # ── Step 1: Follow-up question about current package ──
    current_pkg = _user_sessions.get(session_id)
    if followup and current_pkg:
        return answer_followup(current_pkg, followup)

    # ── Step 2: Pure greeting ──
    if is_greeting and not is_tour and not destination and not budget:
        loc_list = set()
        for p in packages:
            for loc in p.get("locations", []):
                loc_list.add(loc)
        locations_preview = ", ".join(list(loc_list)[:6])
        return (
            "👋 Namaste! Welcome to our Tour Service!\n\n"
            f"We cover: {locations_preview} and more!\n\n"
            "Tell me your destination and budget, I'll find the best package for you."
        )

    # ── Step 3: Random text ──
    if not is_tour and not destination and not budget and not followup:
        return "🤔 I didn't understand that. Please ask about a tour or package."

    # ── Step 4: Filter packages ──
    matched = filter_packages(packages, destination, budget)

    if budget is not None and not matched:
        min_price = min(float(p.get("package_price", 0) or 0) for p in packages)
        return (
            f"😔 No packages available under Rs.{budget}.\n"
            f"Our lowest package starts at Rs.{int(min_price)}.\n"
            "Would you like to see it?"
        )

    if destination and not matched:
        return f"😔 No packages found for '{destination.capitalize()}'. Try another destination."

    if not matched and is_tour:
        matched = packages

    if not matched:
        return "😔 No packages found. Try a different destination or budget."

    # ── Step 5: Save the first matched package in session ──
    _user_sessions[session_id] = matched[0]

    # ── Step 6: Build response ──
    lines = []
    if destination:
        lines.append(f"🔍 Results for: {destination.capitalize()}")
    if budget:
        lines.append(f"💰 Under: Rs.{budget}")
    lines.append(f"✅ Found {len(matched)} package(s)\n")
    lines.append("=" * 45)
    for i, p in enumerate(matched, 1):
        lines.append(format_package(p, i))
    lines.append("You can ask me about vehicles, hotels, activities, inclusions, itinerary and more! 😊")
    return "\n".join(lines)





















from flask import Flask, request, jsonify, render_template, session
from bot import process_message
import uuid

app = Flask(__name__)
app.secret_key = "tour_bot_secret_123"

@app.route("/")
def home():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data       = request.get_json()
    user_msg   = data.get("message", "")
    session_id = session.get("session_id", "default")

    reply = process_message(user_msg, session_id)

    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(debug=True)






<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Himachal Tour Bot</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
       font-family: Arial, sans-serif;
  background: #f0f2f5;

  /* FIX */
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: flex-start;   /* 👈 CHANGE THIS */
  padding: 20px 0;
    }

.chat-box {
    width: 480px;
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    position: relative;
}

    .chat-header {
      background: #075e54;
      color: white;
      padding: 16px 20px;
      font-size: 16px;
      font-weight: bold;
    }

    .chat-header span {
      display: block;
      font-size: 12px;
      font-weight: normal;
      opacity: 0.8;
      margin-top: 2px;
    }
    .chat_h_outer {
    position: absolute;
    width: 100%;
    top: -4px;
}

#messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    height: 420px;
    background: #ece5dd;
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 101px;
}

    .bubble {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 10px;
      font-size: 14px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .user-bubble {
      align-self: flex-end;
      background: #dcf8c6;
      border-bottom-right-radius: 2px;
    }

    .bot-bubble {
      align-self: flex-start;
      background: #ffffff;
      border-bottom-left-radius: 2px;
    }

    .typing {
      align-self: flex-start;
      background: #fff;
      padding: 10px 14px;
      border-radius: 10px;
      font-size: 13px;
      color: #888;
      font-style: italic;
    }

    .input-row {
      display: flex;
      padding: 12px;
      gap: 8px;
      background: #f0f0f0;
      border-top: 1px solid #ddd;
    }

    #msg {
      flex: 1;
      padding: 10px 14px;
      border-radius: 24px;
      border: 1px solid #ccc;
      font-size: 14px;
      outline: none;
    }

    #msg:focus { border-color: #075e54; }

    button {
      background: #075e54;
      color: white;
      border: none;
      padding: 10px 18px;
      border-radius: 24px;
      cursor: pointer;
      font-size: 14px;
    }

    button:hover { background: #128c7e; }
    button:disabled { background: #aaa; cursor: not-allowed; }

    .quick-btns {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 10px 12px 0;
      background: #f0f0f0;
    }

    .quick-btns button {
      font-size: 12px;
      padding: 6px 12px;
      background: #25d366;
      border-radius: 16px;
    }
  </style>
</head>
<body>

<div class="chat-box">

    <div class="chat_h_outer">

        <div class="chat-header">
          🏔️ Himachal Tour Bot
          <span>Ask me about packages, hotels & itineraries</span>
        </div>
      
        <!-- Quick suggestion buttons -->
        <div class="quick-btns">
          <button onclick="quickSend('Show Shimla packages')">Shimla Packages</button>
          <button onclick="quickSend('Tour under Rs.25000')">Under ₹25000</button>
          <button onclick="quickSend('Show all packages')">All Packages</button>
        </div>
    </div>

  <div id="messages"></div>

  <div class="input-row">
    <input id="msg" type="text" placeholder="Type your message..." onkeydown="if(event.key==='Enter') send()" />
    <button id="send-btn" onclick="send()">Send</button>
  </div>

</div>

<script>
  const messagesEl = document.getElementById("messages");
  const sendBtn    = document.getElementById("send-btn");

  // Show welcome message on load
  window.onload = () => {
    addBubble("bot", "👋 Namaste! Welcome!");
  };

  function addBubble(role, text) {
    const div = document.createElement("div");
    div.className = `bubble ${role === "user" ? "user-bubble" : "bot-bubble"}`;
    div.innerText = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function addTyping() {
    const div = document.createElement("div");
    div.className = "typing";
    div.id = "typing";
    div.innerText = "Bot is typing...";
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function removeTyping() {
    const el = document.getElementById("typing");
    if (el) el.remove();
  }

  function quickSend(text) {
    document.getElementById("msg").value = text;
    send();
  }

  async function send() {
    const input = document.getElementById("msg");
    const msg   = input.value.trim();
    if (!msg) return;

    addBubble("user", msg);
    input.value = "";
    sendBtn.disabled = true;
    addTyping();

    try {
      const res  = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg })
      });
      const data = await res.json();
      removeTyping();
      addBubble("bot", data.reply);
    } catch (e) {
      removeTyping();
      addBubble("bot", "⚠️ Error connecting to server. Please try again.");
    }

    sendBtn.disabled = false;
    input.focus();
  }
</script>

</body>
</html>