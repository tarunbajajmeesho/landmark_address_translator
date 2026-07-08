"""
Landmark Address Translator
----------------------------
Turns messy, landmark-based Indian addresses ("near the blue water tank,
behind Ramesh tea stall, opposite govt school") into a clean,
delivery-agent-friendly format, flags how likely the address is to
cause a failed/delayed delivery, and (when possible) shows an
approximate pin on a map.

Built for the Meesho Buildathon.
"""

import json
import time

import requests
import streamlit as st

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

st.set_page_config(
    page_title="Landmark Address Translator",
    page_icon="📍",
    layout="centered",
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Models on OpenRouter that are cheap/fast and good enough for this task.
MODEL_OPTIONS = {
    "Claude 3.5 Haiku (fast, cheap, recommended)": "anthropic/claude-3.5-haiku",
    "GPT-4o mini (fast, cheap)": "openai/gpt-4o-mini",
    "Llama 3.1 8B (free-tier friendly)": "meta-llama/llama-3.1-8b-instruct",
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
  "primary_landmark": "The single most well-known/searchable landmark \
mentioned (e.g. a temple, school, water tank, bus stand, petrol pump). This \
should be something that could plausibly be searched on a map. If none is \
clearly identifiable, return an empty string.",
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
- Do not invent details that were not given or reasonably implied.
- Output must be valid JSON and nothing else.
"""

# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------


def get_api_key() -> str:
    """Fetch the OpenRouter API key from Streamlit secrets or session state."""
    if "OPENROUTER_API_KEY" in st.secrets:
        return st.secrets["OPENROUTER_API_KEY"]
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
        "X-Title": "Landmark Address Translator",
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


def geocode_landmark(landmark: str, city_hint: str):
    """Best-effort geocode of the primary landmark via OpenStreetMap Nominatim."""
    if not landmark:
        return None

    query = landmark
    if city_hint.strip():
        query += f", {city_hint}"
    query += ", India"

    headers = {"User-Agent": "landmark-address-translator-hackathon-app"}
    params = {"q": query, "format": "json", "limit": 1}

    try:
        resp = requests.get(NOMINATIM_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        return None
    return None


def risk_badge(risk_level: str) -> str:
    colors = {"low": "🟢 Low risk", "medium": "🟠 Medium risk", "high": "🔴 High risk"}
    return colors.get(risk_level.lower(), risk_level)


# --------------------------------------------------------------------------
# SIDEBAR
# --------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Settings")

    has_secret_key = "OPENROUTER_API_KEY" in st.secrets
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
        "Built for the Meesho Buildathon 🚀\n\n"
        "Helps convert informal, landmark-based addresses "
        "(common in tier 2/3/4 towns) into a clear, structured "
        "format delivery agents can actually use — reducing "
        "failed deliveries and RTOs."
    )

# --------------------------------------------------------------------------
# MAIN UI
# --------------------------------------------------------------------------

st.title("📍 Landmark Address Translator")
st.write(
    "Describe an address the way you'd tell it to a neighbour — "
    "we'll turn it into something a delivery agent can actually follow, "
    "and flag if it's likely to cause a delivery problem."
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
    st.subheader("📦 Delivery-ready address")
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

    landmark = result.get("primary_landmark", "")
    if landmark:
        with st.spinner("Looking up landmark on the map..."):
            coords = geocode_landmark(landmark, city_hint)
        if coords:
            st.subheader("🗺️ Approximate location")
            st.caption(f"Best-effort pin for landmark: **{landmark}**. Always verify before dispatch.")
            st.map({"lat": [coords[0]], "lon": [coords[1]]}, zoom=14)
        else:
            st.caption(
                f"Primary landmark identified as **{landmark}**, but it could not be "
                "found on the map automatically — verify manually."
            )

    with st.expander("Raw JSON (for debugging / integration)"):
        st.json(result)

st.divider()
st.caption(
    "⚠️ This tool gives a best-effort interpretation — always let the customer "
    "confirm the final address before dispatch, especially for high-risk scores."
)
