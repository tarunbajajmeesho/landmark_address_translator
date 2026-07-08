# 📍 Landmark Address Translator

**Built for the Meesho Buildathon**

A huge share of failed and delayed deliveries in tier 2/3/4 towns and villages
happens not because of logistics, but because addresses are described by
**landmarks, not streets**: *"near the blue water tank, behind Ramesh's tea
stall, opposite the school."* Delivery agents unfamiliar with the area waste
time calling customers, guessing, or giving up (RTO — Return to Origin),
which is a real, hidden cost for e-commerce platforms.

This app takes a raw, informal address description (in any mix of language)
and:

- 🧭 Rewrites it into a clean, **delivery-agent-friendly formatted address**
- 📝 Generates a short **plain-language directions summary**
- 📊 Scores the address on a **0–100 clarity score**
- 🚦 Flags a **delivery risk level** (low / medium / high)
- ❓ Suggests **specific clarifying questions** to ask the customer
- 🗺️ Attempts to **pin the primary landmark on a map** (via OpenStreetMap)

---

## Demo flow

1. User types (or pastes) an address the way they'd describe it to a
   neighbour — in Hindi, English, Hinglish, or any regional language.
2. App sends it to an LLM (via [OpenRouter](https://openrouter.ai)) with a
   structured prompt asking for a clean JSON breakdown.
3. App renders the formatted address, risk score, missing info, and a
   best-effort map pin.

---

## 🛠️ Local setup

### 1. Clone and install

```bash
git clone https://github.com/<your-username>/landmark-address-translator.git
cd landmark-address-translator
python -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Get an OpenRouter API key

1. Go to [openrouter.ai/keys](https://openrouter.ai/keys) and sign up (free).
2. Create a new API key.
3. OpenRouter gives some free-tier models (like Llama 3.1 8B) at no cost —
   good enough to test without spending anything. Paid models (Claude,
   GPT-4o mini) are extremely cheap per request (fractions of a cent).

### 3. Add your key

Copy the example secrets file:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` and paste your real key:

```toml
OPENROUTER_API_KEY = "sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

> This file is already in `.gitignore` — it will never be committed.

Alternatively, skip this step entirely and just paste your API key into the
sidebar text box when the app is running — it's kept only in that browser
session and never saved to disk.

### 4. Run it

```bash
streamlit run app.py
```

It'll open at `http://localhost:8501`.

---

## ☁️ Deploying on Streamlit Community Cloud (streamlit.io)

1. Push this repo to **your own GitHub account** (steps below).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with
   GitHub.
3. Click **"New app"** → select this repo → branch `main` → main file
   path `app.py`.
4. Before/after deploying, go to **App settings → Secrets** and paste:

   ```toml
   OPENROUTER_API_KEY = "sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ```

5. Click **Deploy**. You'll get a public URL like
   `https://landmark-address-translator.streamlit.app` — that's your
   **App link** for the hackathon submission form.

---

## 📤 Pushing this folder to a new GitHub repo

If you downloaded this project as a folder and haven't pushed it to GitHub
yet:

```bash
cd landmark-address-translator
git init
git add .
git commit -m "Initial commit: Landmark Address Translator"
git branch -M main
git remote add origin https://github.com/<your-username>/landmark-address-translator.git
git push -u origin main
```

(Create the empty repo on GitHub first at
[github.com/new](https://github.com/new) — don't initialize it with a
README, or the push will conflict.)

---

## 🔩 How it works (technical)

- **Frontend/app**: Streamlit (`app.py`) — single-page app, no database.
- **LLM call**: Direct REST call to OpenRouter's `/chat/completions`
  endpoint (OpenAI-compatible API), using a strict system prompt that forces
  a structured JSON response (formatted address, clarity score, risk level,
  missing info, clarifying questions).
- **Geocoding**: Best-effort landmark lookup via the free
  [OpenStreetMap Nominatim](https://nominatim.org/) API — no key required.
  This is approximate and meant for visual confirmation, not precision
  routing.
- **Model choice**: Selectable in the sidebar — defaults to Claude 3.5 Haiku
  for speed/cost, with a free Llama 3.1 8B option if you want to test at
  zero cost.

---

## 🧪 Try these example inputs

```
Ramesh chaha ki dukaan ke peeche, neeli paani ki tanki ke pass,
school wali gali mein teesra ghar, neela gate hai
```
City hint: `Sitapur, Uttar Pradesh`

```
near the big tree, ask anyone for Suresh's house
```
City hint: `Bhagalpur, Bihar`

The first should score much higher on clarity than the second — that
contrast is the whole point of the tool.

---

## 💡 Why this matters (for the submission form)

**Who hurts today:** Buyers in tier 2/3/4 towns whose addresses aren't
standard street addresses, delivery agents who waste time/calls locating
these addresses, and the platform (Meesho) which absorbs the cost of failed
deliveries, RTOs, and repeat delivery attempts.

**How this helps:** Turning a fuzzy, spoken-style address into a structured,
scored, agent-readable format — before the order ever ships — so problems
get caught and clarified upfront instead of at the doorstep.

---

## 🚧 Known limitations / future improvements

- Geocoding is best-effort and may not always find obscure local landmarks.
- No persistence/database — every request is stateless (by design, to keep
  this simple and fast to build).
- Could be extended to auto-flag high-risk addresses *before* checkout, or
  to feed a delivery agent app directly via API.
- Voice input (speak the address instead of typing) would help low
  text-literacy users even more — a natural next step.
