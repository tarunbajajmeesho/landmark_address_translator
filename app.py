"""
PataPakka — Sahi Pata, Sahi Delivery
----------------------------
Turns messy, landmark-based Indian addresses ("near the blue water tank,
behind Ramesh tea stall, opposite govt school") into a clean,
delivery-agent-friendly format, flags how likely the address is to
cause a failed/delayed delivery, and (when possible) shows an
approximate pin on a colourful, familiar-looking Google Map.

Built for the Meesho Buildathon.
"""

import json
import time
import urllib.parse

import requests
import streamlit as st
import streamlit.components.v1 as components

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

st.set_page_config(
    page_title="PataPakka | Sahi Pata, Sahi Delivery",
    page_icon="📍",
    layout="centered",
)

# --------------------------------------------------------------------------
# THEME — Meesho-inspired Jamuni purple + Aam mango yellow
# --------------------------------------------------------------------------

MEESHO_PURPLE = "#7D58BA"
MEESHO_PURPLE_DARK = "#5C3D96"
MEESHO_YELLOW = "#FFC94A"
MEESHO_PINK = "#F43397"

st.markdown(
    f"""
    <style>
    .stApp {{
        background: linear-gradient(180deg, #FAF7FF 0%, #FFFFFF 100%);
    }}

    /* Hero banner */
    .pp-hero {{
        background: linear-gradient(120deg, {MEESHO_PURPLE} 0%, {MEESHO_PINK} 100%);
        padding: 28px 28px 24px 28px;
        border-radius: 18px;
        margin-bottom: 22px;
        box-shadow: 0 8px 24px rgba(125, 88, 186, 0.25);
    }}
    .pp-hero h1 {{
        color: white !important;
        font-size: 2.1rem;
        margin: 0;
        font-weight: 800;
        letter-spacing: -0.5px;
    }}
    .pp-hero p {{
        color: {MEESHO_YELLOW};
        font-size: 1.05rem;
        margin: 6px 0 0 0;
        font-weight: 600;
    }}
    .pp-hero span.sub {{
        color: rgba(255,255,255,0.85);
        font-size: 0.92rem;
        display: block;
        margin-top: 8px;
        font-weight: 400;
    }}

    /* Buttons */
    .stButton > button, .stLinkButton > a {{
        border-radius: 10px !important;
        border: none !important;
        font-weight: 700 !important;
    }}
    .stButton > button[kind="primary"] {{
        background: linear-gradient(90deg, {MEESHO_PURPLE} 0%, {MEESHO_PINK} 100%) !important;
        color: white !important;
    }}
    .stButton > button[kind="secondary"] {{
        background: #FFF6E0 !important;
        color: {MEESHO_PURPLE_DARK} !important;
        border: 1.5px solid {MEESHO_YELLOW} !important;
    }}
    .stLinkButton > a {{
        background: linear-gradient(90deg, {MEESHO_YELLOW} 0%, #FFB300 100%) !important;
        color: #4A2E00 !important;
    }}

    /* Headers */
    h2, h3 {{
        color: {MEESHO_PURPLE_DARK} !important;
    }}

    /* Metric cards */
    div[data-testid="stMetric"] {{
        background: #FFFFFF;
        border: 1.5px solid #EEE3FB;
        border-radius: 14px;
        padding: 10px 14px;
        box-shadow: 0 2px 8px rgba(125, 88, 186, 0.08);
    }}

    /* Sidebar */
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #FFFFFF 0%, #F6F0FF 100%);
        border-right: 1px solid #EEE3FB;
    }}

    /* Divider color */
    hr {{
        border-color: #EEE3FB !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"

# Models on OpenRouter that are cheap/fast and good enough for this task.
# NOTE: Claude 3.5 Haiku and GPT-4o mini are PAID models — they will return
# a 404 "No endpoints found" error if your OpenRouter account has $0 balance.
# The Llama option below uses the ":free" suffix, which is required to hit
# OpenRouter's free tier — without it, OpenRouter silently routes to the
# paid endpoint for the same model and you'll hit the same 404.
MODEL_OPTIONS = {
    "Llama 3.3 70B (free, recommended to start)": "meta-llama/llama-3.3-70b-instruct:free",
    "Claude 3.5 Haiku (paid — needs OpenRouter credits)": "anthropic/claude-3.5-haiku",
    "GPT-4o mini (paid — needs OpenRouter credits)": "openai/gpt-4o-mini",
}

LANGUAGES = [
    "English",
    "Hindi",
    "Tamil",
    "Telugu",
    "Kannada",
    "Bengali",
    "Marathi",
    "Malayalam",
]

SYSTEM_PROMPT = """You are an assistant that helps Indian e-commerce delivery agents \
find addresses that are described informally using landmarks, especially in \
tier 2/3/4 towns and villages where formal street addresses often don't exist \
or aren't reliable.

You will be given a raw, informal address description, possibly mixing local \
language words with English (Hinglish or similar), and possibly the \
city/town/pincode if provided separately.

Your job is to output ONLY a valid JSON object (no markdown fences, no extra \
text) with this exact structure:

{
  "formatted_address": "A clean, structured version of the address a delivery \
agent could read at a glance: house/shop identifier (if any), landmark chain \
ordered from most well-known to most specific, area, city, pincode if given.",
  "landmark_candidates": ["A ranked list of 1-4 short, map-searchable phrases, \
MOST well-known/findable first — e.g. a named temple, school, bus stand, \
petrol pump, or market. Each entry should be something you could plausibly \
type into a map search on its own. If genuinely nothing landmark-like is \
mentioned, return an empty list."],
  "area": "The neighbourhood/locality/village name if mentioned, else empty string.",
  "city": "The city/town/village name — use the provided city hint if given, \
otherwise infer from the text if clearly stated, else empty string.",
  "state": "Indian state if it can be inferred from the city hint or text, else empty string.",
  "pincode": "6-digit PIN code if mentioned or given in the city hint, else empty string.",
  "directions_summary": "A short 1-2 sentence plain-language direction \
summary a delivery agent could follow, e.g. 'From the bus stand, go towards \
the school, the house is the second lane on the left, blue gate.'",
  "clarity_score": An integer from 0 to 100 representing how likely a \
delivery agent unfamiliar with the area could find this address. 100 = very \
clear (has a real landmark + direction + area). 0 = essentially unfindable.,
  "risk_level": one of "low", "medium", "high" — the risk of a failed or \
delayed delivery / RTO based on address clarity,
  "missing_info": ["short list", "of specific missing details", "that would \
most improve findability, e.g. 'no house number', 'no area/locality name', \
'no distance or direction from landmark'"],
  "suggested_questions": ["1-3 short questions a delivery agent or the \
platform could ask the customer to clarify the address before dispatch"]
}

Rules:
- Be honest about clarity_score and risk_level — do not inflate them. Most \
informal landmark addresses without a clear direction or distance should \
score below 60.
- Keep formatted_address delivery-agent-friendly, not overly formal.
- landmark_candidates should be ordered from most generically findable (a \
famous/large landmark) to most specific (a small shop or personal name) — \
the app will try to geocode them in this order.
- Do not invent details that were not given or reasonably implied.
- Output must be valid JSON and nothing else.
"""

# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------


def get_secret_api_key() -> str:
    """Safely fetch the OpenRouter API key from Streamlit secrets, if present.

    Never raises — if no secrets.toml / Cloud secrets are configured at all,
    st.secrets access can raise, so we swallow that and just return "".
    """
    try:
        return st.secrets.get("OPENROUTER_API_KEY", "")
    except Exception:
        return ""


def get_api_key() -> str:
    """Fetch the OpenRouter API key from Streamlit secrets or session state."""
    secret_key = get_secret_api_key()
    if secret_key:
        return secret_key
    return st.session_state.get("manual_api_key", "")


def call_openrouter(raw_address: str, city_hint: str, model: str, api_key: str) -> dict:
    """Call OpenRouter chat completions endpoint and parse the JSON reply."""
    user_content = f"Raw address description:\n{raw_address}\n"
    if city_hint.strip():
        user_content += f"\nKnown city/town/pincode (if any): {city_hint}\n"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # Recommended by OpenRouter for attribution / rate-limit friendliness.
        "HTTP-Referer": "https://streamlit.io",
        "X-Title": "PataPakka",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
    }

    response = requests.post(headers=headers, url=OPENROUTER_URL, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()

    text = data["choices"][0]["message"]["content"].strip()

    # Defensive cleanup in case the model wraps JSON in markdown fences anyway.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    return json.loads(text)


def nominatim_search(query: str):
    """Single Nominatim forward-geocode call. Returns (lat, lon, display_name) or None."""
    headers = {"User-Agent": "landmark-address-translator-hackathon-app"}
    params = {"q": query, "format": "json", "limit": 1, "countrycodes": "in"}
    try:
        resp = requests.get(NOMINATIM_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        results = resp.json()
        if results:
            r = results[0]
            return float(r["lat"]), float(r["lon"]), r.get("display_name", "")
    except Exception:
        return None
    return None


def nominatim_reverse(lat: float, lon: float):
    """Reverse-geocode a coordinate to see what OSM actually knows is there —
    a sanity check against the landmark match, since a 'hit' can sometimes be
    a loose/wrong match."""
    headers = {"User-Agent": "landmark-address-translator-hackathon-app"}
    params = {"lat": lat, "lon": lon, "format": "json"}
    try:
        resp = requests.get(NOMINATIM_REVERSE_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("display_name", "")
    except Exception:
        return ""


def build_location_string(parts: list) -> str:
    """Join non-empty location parts into a single query string."""
    return ", ".join(p.strip() for p in parts if p and p.strip())


def geocode_best_match(landmark_candidates: list, area: str, city: str, state: str, pincode: str, city_hint: str):
    """Try to find the most accurate pin by attempting several queries, most
    specific/landmark-based first, falling back to just the area/city/pincode.

    Returns a dict: {lat, lon, matched_query, display_name, confidence} or None.
    confidence is 'landmark' (matched a specific named place), 'area' (only
    matched the general locality), or 'city' (only matched the town/city
    centre — least precise).
    """
    location_tail = build_location_string([area, city, state, pincode]) or city_hint

    attempts = []

    # 1) Each landmark candidate + full location context (most accurate if it hits)
    for lm in landmark_candidates:
        if lm and lm.strip():
            attempts.append((build_location_string([lm, location_tail, "India"]), "landmark"))

    # 2) Landmark candidates alone + just city (looser, in case area name confuses OSM)
    for lm in landmark_candidates:
        if lm and lm.strip():
            attempts.append((build_location_string([lm, city or city_hint, "India"]), "landmark"))

    # 3) Area + city + state + pincode (no landmark — general locality pin)
    if area:
        attempts.append((build_location_string([area, city, state, pincode, "India"]), "area"))

    # 4) City/town + pincode only (least precise — just gets you to the right town)
    if city or pincode or city_hint:
        attempts.append((build_location_string([city, pincode, city_hint, "India"]), "city"))

    seen = set()
    for query, confidence in attempts:
        if not query or query in seen:
            continue
        seen.add(query)
        result = nominatim_search(query)
        # Be polite to Nominatim's free usage policy (max ~1 request/sec).
        time.sleep(1)
        if result:
            lat, lon, display_name = result
            return {
                "lat": lat,
                "lon": lon,
                "matched_query": query,
                "display_name": display_name,
                "confidence": confidence,
            }
    return None


def google_maps_search_url(landmark_candidates: list, area: str, city: str, state: str, pincode: str, city_hint: str) -> str:
    """Build a no-API-key Google Maps search link using the best available
    text description. Google's coverage of small Indian landmarks is often
    much better than OpenStreetMap's, so this is offered as the primary
    'go verify this yourself' action regardless of whether OSM found a pin."""
    best_landmark = landmark_candidates[0] if landmark_candidates else ""
    location_tail = build_location_string([area, city, state, pincode]) or city_hint
    query = build_location_string([best_landmark, location_tail, "India"])
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(query)


def google_maps_embed_by_coords(lat: float, lon: float, zoom: int = 15) -> str:
    """Build a no-API-key Google Maps EMBED url for a lat/lon pin — this is
    the actual colourful Google Maps look (roads, POIs, satellite toggle)
    rather than the flat st.map() view."""
    return f"https://maps.google.com/maps?q={lat},{lon}&z={zoom}&output=embed"


def google_maps_embed_by_query(query: str, zoom: int = 13) -> str:
    """Build a no-API-key Google Maps EMBED url from a free-text search query.
    Used as a fallback when OSM couldn't find a confident pin, so the user
    still gets a colourful, familiar map instead of nothing."""
    return f"https://maps.google.com/maps?q={urllib.parse.quote(query)}&z={zoom}&output=embed"


def render_google_map(embed_url: str, height: int = 380):
    """Render an embedded Google Map iframe inline in the app."""
    components.iframe(embed_url, height=height, scrolling=False)


def risk_badge(risk_level: str) -> str:
    colors = {"low": "🟢 Low risk", "medium": "🟠 Medium risk", "high": "🔴 High risk"}
    return colors.get(risk_level.lower(), risk_level)


# --------------------------------------------------------------------------
# SIDEBAR
# --------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Settings")

    has_secret_key = bool(get_secret_api_key())
    if has_secret_key:
        st.success("API key loaded from app secrets.")
    else:
        st.text_input(
            "OpenRouter API key",
            type="password",
            key="manual_api_key",
            help="Get a free key at https://openrouter.ai/keys. "
            "Not stored anywhere except this browser session.",
        )

    model_label = st.selectbox("Model", list(MODEL_OPTIONS.keys()), index=0)
    selected_model = MODEL_OPTIONS[model_label]

    st.divider()
    st.caption(
        "**PataPakka** 🚀 · Built for the Meesho Buildathon\n\n"
        "Pata (address) + Pakka (confirmed) — turns informal, "
        "landmark-based addresses (common in tier 2/3/4 towns) into a "
        "clear, structured format delivery agents can actually use — "
        "reducing failed deliveries and RTOs."
    )

# --------------------------------------------------------------------------
# MAIN UI
# --------------------------------------------------------------------------

st.markdown(
    """
    <div class="pp-hero">
        <h1>📍 PataPakka</h1>
        <p>Sahi Pata, Sahi Delivery</p>
        <span class="sub">Describe an address the way you'd tell it to a neighbour —
        we'll turn it into something a delivery agent can actually follow,
        and flag if it's likely to cause a delivery problem.</span>
    </div>
    """,
    unsafe_allow_html=True,
)

example_col1, example_col2 = st.columns(2)
with example_col1:
    if st.button("Try an example (Hindi-English mix)", use_container_width=True):
        st.session_state["raw_address"] = (
            "Ramesh tea stall ke peeche, blue paani ki tanki ke pass, "
            "school wali gali me teesra ghar, neela gate hai"
        )
        st.session_state["city_hint"] = "Sitapur, Uttar Pradesh"
with example_col2:
    if st.button("Try an example (very vague)", use_container_width=True):
        st.session_state["raw_address"] = "near the big tree, ask anyone for Suresh's house"
        st.session_state["city_hint"] = "Bhagalpur, Bihar"

raw_address = st.text_area(
    "Describe the address (any language, however you'd normally say it)",
    key="raw_address",
    height=120,
    placeholder=(
        "e.g. Ramesh chaha ki dukaan ke peeche, neeli paani ki tanki ke pass, "
        "school wali gali mein teesra ghar"
    ),
)

city_hint = st.text_input(
    "City / town / pincode (optional, but helps a LOT)",
    key="city_hint",
    placeholder="e.g. Sitapur, Uttar Pradesh, 261001",
)

output_language = st.selectbox(
    "Output language for the formatted address",
    LANGUAGES,
    index=0,
)

submit = st.button("✨ Translate address", type="primary", use_container_width=True)

st.divider()

if submit:
    api_key = get_api_key()

    if not raw_address.strip():
        st.warning("Please describe the address first.")
        st.stop()

    if not api_key:
        st.error(
            "No OpenRouter API key found. Add one in the sidebar, "
            "or set OPENROUTER_API_KEY in your Streamlit secrets."
        )
        st.stop()

    prompt_address = raw_address
    if output_language != "English":
        prompt_address += f"\n\n(Please write formatted_address, directions_summary, and suggested_questions in {output_language}.)"

    with st.spinner("Reading the address like a delivery agent would..."):
        try:
            result = call_openrouter(prompt_address, city_hint, selected_model, api_key)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status == 404:
                st.error(
                    "OpenRouter couldn't find an available endpoint for this model "
                    "(404). This almost always means either: (1) your OpenRouter "
                    "account has $0 balance and you picked a paid model — switch to "
                    "the free Llama 3.3 70B option in the sidebar, or add credits at "
                    "openrouter.ai/settings/credits, or (2) the model slug is stale — "
                    "check openrouter.ai/models for the current one."
                )
            elif status == 401:
                st.error("OpenRouter rejected the API key (401) — double-check it's correct and active.")
            elif status == 402:
                st.error("OpenRouter says payment is required (402) — add credits at openrouter.ai/settings/credits.")
            else:
                st.error(f"OpenRouter API error: {e}")
            st.stop()
        except (KeyError, json.JSONDecodeError):
            st.error(
                "Couldn't parse a clean response from the model. "
                "Try again, or switch to a different model in the sidebar."
            )
            st.stop()
        except Exception as e:
            st.error(f"Something went wrong: {e}")
            st.stop()

    # ---------------- Results ----------------
    st.subheader("📦 Pakka address, ready to dispatch")
    st.info(result.get("formatted_address", "—"))

    score = result.get("clarity_score", 0)
    risk = result.get("risk_level", "unknown")

    m1, m2 = st.columns(2)
    with m1:
        st.metric("Clarity score", f"{score}/100")
        st.progress(min(max(score, 0), 100) / 100)
    with m2:
        st.metric("Delivery risk", risk_badge(risk))

    st.subheader("🧭 Directions summary")
    st.write(result.get("directions_summary", "—"))

    missing = result.get("missing_info", [])
    if missing:
        st.subheader("⚠️ What's missing")
        for item in missing:
            st.write(f"- {item}")

    questions = result.get("suggested_questions", [])
    if questions:
        st.subheader("❓ Ask the customer")
        for q in questions:
            st.write(f"- {q}")

    landmark_candidates = result.get("landmark_candidates", [])
    area = result.get("area", "")
    city = result.get("city", "")
    state = result.get("state", "")
    pincode = result.get("pincode", "")

    st.subheader("🗺️ Location lookup")

    with st.spinner("Trying to pin the exact location (checking multiple landmarks)..."):
        match = geocode_best_match(landmark_candidates, area, city, state, pincode, city_hint)

    confidence_labels = {
        "landmark": "🟢 High confidence — matched a specific landmark",
        "area": "🟠 Medium confidence — matched the general area, not a specific landmark",
        "city": "🔴 Low confidence — only matched the town/city centre",
    }

    if match:
        st.success(confidence_labels.get(match["confidence"], ""))
        st.caption(f"Matched on: *{match['matched_query']}*")

        zoom_level = 16 if match["confidence"] == "landmark" else 13
        render_google_map(google_maps_embed_by_coords(match["lat"], match["lon"], zoom=zoom_level))

        with st.spinner("Double-checking what's actually at this pin..."):
            nearby = nominatim_reverse(match["lat"], match["lon"])
        if nearby:
            st.caption(f"📍 OpenStreetMap's nearest known address for this pin: {nearby}")
            st.caption("Compare this against the description above — if it doesn't line up, trust the map less and verify with the customer.")
    else:
        st.warning(
            "Could not find any confident pin on OpenStreetMap for this address. "
            "Small/unnamed landmarks in tier 2/3/4 areas often aren't mapped — "
            "here's a Google Maps search on the best-guess description instead."
        )
        fallback_query = build_location_string(
            [landmark_candidates[0] if landmark_candidates else "", area, city, state, pincode]
        ) or city_hint
        if fallback_query:
            render_google_map(google_maps_embed_by_query(fallback_query))

    maps_url = google_maps_search_url(landmark_candidates, area, city, state, pincode, city_hint)
    st.link_button("🛵 Open in Google Maps for final check", maps_url, use_container_width=True)
    st.caption(
        "Google's map coverage of small-town India is usually more complete than OpenStreetMap's — "
        "use this link to visually confirm the location before dispatch, especially for medium/low confidence matches."
    )

    with st.expander("Raw JSON (for debugging / integration)"):
        st.json(result)

st.divider()
st.caption(
    "⚠️ **PataPakka** gives a best-effort interpretation — always let the customer "
    "confirm the final address before dispatch, especially for high-risk scores."
)
