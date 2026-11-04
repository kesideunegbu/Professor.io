# Professor.io

The backend (server) for an app that helps students choose professors. It builds on Rate My Professor–style reviews and adds three features:

| Feature | What the student sees |
|---|---|
| **AI review summaries** | A short summary of all a professor's reviews (strengths, criticisms, workload, grading, and who the class suits), written by Google's Gemini Flash. |
| **Professor comparison** | Two professors side by side for the same course, plus a "choose this one if…" write-up. |
| **Personalized recommendations** | Students say what they like in a professor (e.g. "lighter workload", "hands-on assignments"), and each professor gets a **compatibility score** with reasons. |

> **About the compatibility score:** it shows how well what students say about a professor matches *your* preferences. It does **not** predict your grade or how well you'll do. The app includes this note with every score.

---

## Getting started

You need **Python 3.12 or newer**.

**1. Install**

```bash
python -m venv .venv
.venv\Scripts\activate               # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

**2. Add your settings.** Copy the example settings file:

```bash
cp .env.example .env
```

Then open `.env` and fill in these two values:

| Setting | What to put |
|---|---|
| `GEMINI_API_KEY` | Your key from [Google AI Studio](https://aistudio.google.com/apikey). |
| `JWT_SECRET` | Any long random text. To generate one, run `python -c "import secrets; print(secrets.token_urlsafe(48))"` |

⚠️ **Never commit `.env`.** It holds your private keys. Git already ignores it.

**3. Load sample data (optional).** This adds 3 professors and 11 reviews:

```bash
python -m scripts.seed
```

**4. Start the server**

```bash
uvicorn app.main:app --reload
```

Then open **http://localhost:8000**. It takes you to an interactive page where you can try every feature in the browser.

---

## Trying it out in the browser

On the http://localhost:8000 page:

1. **Create an account** with `POST /auth/register`.
2. **Log in:** click **Authorize** (top right) and enter your email as the username, plus your password.
3. **Set your preferences** with `PUT /me/preferences`. To see every option, run `GET /preferences/options` first.
4. **Try the features:**
   - `GET /me/recommendations` shows professors ranked for you.
   - `GET /professors/2/summary` shows an AI summary.
   - `GET /compare` with `a=1` and `b=2` compares two professors.

---

## For the front-end team

- The page at http://localhost:8000/docs lists every endpoint with example requests and responses.
- **Login:** send `username` (the email) and `password` as form data to `POST /auth/login`. You'll get back an `access_token`. Then send it on later requests as the header `Authorization: Bearer <token>`.
- **Blocked requests (CORS):** if the browser blocks your requests, add your dev server's address to `CORS_ORIGINS` in `.env`. Addresses `localhost:3000` and `localhost:5173` already work.
- **Show the extra fields on scores:** every compatibility score comes with a `confidence` level (`low` / `medium` / `high`) and a `disclaimer`. Please show both next to the score.

### All endpoints

🔒 = the user must be logged in.

| What it does | Endpoint |
|---|---|
| Create an account | `POST /auth/register` |
| Log in (get a token) | `POST /auth/login` |
| Get the current user 🔒 | `GET /me` |
| List preference options (for onboarding) | `GET /preferences/options` |
| View / save preferences 🔒 | `GET` / `PUT /me/preferences` |
| Get recommended professors 🔒 | `GET /me/recommendations?course=CS101` |
| Search professors | `GET /professors?q=smith` |
| Add a professor 🔒 | `POST /professors` |
| Get a professor's details and stats | `GET /professors/{id}` |
| List a professor's reviews | `GET /professors/{id}/reviews` |
| Write a review (one per course) 🔒 | `POST /professors/{id}/reviews` |
| Edit / delete your own review 🔒 | `PATCH` / `DELETE /reviews/{id}` |
| Get an AI summary of reviews | `GET /professors/{id}/summary` |
| Get your score for one professor 🔒 | `GET /professors/{id}/compatibility` |
| Compare two professors | `GET /compare?a=1&b=2&course=CS101` |

---

## For the database team

- The tables are defined in [app/models.py](app/models.py):

  | Table | Holds |
  |---|---|
  | `users` | Accounts |
  | `user_preferences` | What each student likes in a professor |
  | `professors` | Professor info |
  | `reviews` | Ratings and review text |
  | `ai_cache` | Saved Gemini results, so the app doesn't pay for the same summary twice |

- The app uses a local SQLite file by default. To use your database instead, set `DATABASE_URL` in `.env`, e.g. `postgresql://user:password@host/dbname`.
- Tables are created automatically when the server starts. If your schema differs, let's agree on one version so we don't end up with two `users` tables.

---

## How the compatibility score works

The logic is in [app/traits.py](app/traits.py) and [app/services/matching.py](app/services/matching.py).

**1. Professors are rated on 7 traits:** clear explanations, workload, hands-on assignments, deadline flexibility, challenge, extra credit, and approachability.

**2. Each review tells us about some of these traits.** That information comes from three places. When they disagree, the higher one in this list wins:
1. Tags the student picks when writing the review (e.g. "heavy workload")
2. The difficulty rating (4–5 means challenging, 1–2 means easy)
3. Gemini reading the review text

**3. The reviews are combined per trait.** For example: "4 of the 5 reviews that mention workload say it's heavy." Until a trait has several mentions, its value stays close to neutral, so one review can't decide it.

**4. The score is the match between the professor's traits and the student's preferences,** from 0 to 100. Preferences the student marked as more important count for more. Each score also includes:
- **Confidence:** how many reviews actually mention the things the student cares about.
- **Reasons and concerns** in plain English, e.g. *"Assignments provide practical, hands-on experience (3 of 3 reviews that mention it)."* A trait is only quoted if at least 2 reviews mention it.

Gemini never makes up the score or the reasons. It only reads reviews. The score itself is simple math, so it's predictable and can be checked.

---

## Gemini notes

- **Free-tier limit.** A free key allows about **5 requests per minute.** Each new review, first-time summary, and first-time comparison uses one request. When the limit is hit, users see "The AI service is busy," and everything else keeps working.
- **Saved results.** Summaries and comparisons are saved and only regenerated when reviews change, so viewing them again is free and instant.
- **Changing the model.** Set `GEMINI_MODEL` in `.env`. The default is `gemini-3.5-flash`.
- **Without a key** the app still runs. Summaries and comparison write-ups are turned off, and recommendations use tags and ratings only.
- **Safety.** Gemini is told to treat review text strictly as content to analyze, so a review can't trick it with hidden instructions.

---

## Running the tests

```bash
pytest
```

The tests use a fake version of Gemini, so they don't need an API key or internet access.

---

## Project layout

```
app/
  main.py          starts the app
  models.py        database tables
  schemas.py       the shape of request/response data
  traits.py        the 7 professor traits and review tags
  security.py      passwords and login tokens
  routers/         the API endpoints, grouped by feature
  services/
    ai.py          everything that talks to Gemini
    matching.py    the compatibility score
    professors.py  stats, caching, review analysis
scripts/seed.py    loads sample data
tests/             automated tests
```

---

## Still to do

- **Database migrations,** so table changes don't require recreating the database.
- **Rate limiting,** especially on features that call Gemini.
- **Moderation:** let students report inappropriate reviews.
- **Email verification,** e.g. only allowing `.edu` addresses.
