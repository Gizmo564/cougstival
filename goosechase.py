"""Log in to Goosechase Studio and run API queries.

The Studio app calls a GraphQL API with a short-lived bearer token (about 30 minutes).
We open the site in a saved browser profile, let the app get its token (logging in if needed),
and reuse that token for our own queries.
"""
import json
import os
from contextlib import contextmanager

API = "https://api.goosechase.com/studio"
PROFILE = os.path.expanduser("~/.cache/cougstival-profile")

SUBMISSIONS = """query S($experienceId: ID!, $first: Int, $offset: Int) {
  experienceStatistics(experienceId: $experienceId) {
    submissions(first: $first, offset: $offset) {
      totalCount
      edges { node { teamName participantName missionPoints bonusPoints submissionCreatedAt } }
    }
  }
}"""

PARTICIPANTS = """query P($experienceId: ID!, $first: Int, $offset: Int) {
  experienceStatistics(experienceId: $experienceId) {
    participants(first: $first, offset: $offset) {
      totalCount
      edges { node { teamName totalPoints } }
    }
  }
}"""


class LoginError(Exception):
    """We are not (or no longer) logged in."""


@contextmanager
def session(experience_id, email, password, headed=False):
    """Yield gql(query, variables) -> data. Raises LoginError if we can't authenticate."""
    from playwright.sync_api import sync_playwright  # imported here so tests don't need it

    token = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFILE, headless=not headed)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            def on_request(req):
                auth = req.headers.get("authorization")
                if req.url.startswith(API) and auth:
                    token["auth"] = auth
            page.on("request", on_request)

            page.goto(f"https://studio.goosechase.com/experience/{experience_id}/participants")
            page.wait_for_timeout(4000)

            if "auth" not in token and page.locator("input[type=password]").count():
                if not (email and password):
                    raise LoginError("login page shown but GC_EMAIL / GC_PASSWORD are not set")
                page.locator("input[type=email], input[name=email], input[type=text]").first.fill(email)
                page.locator("input[type=password]").first.fill(password)
                page.locator("button[type=submit]").first.click()

            for _ in range(45):
                if "auth" in token:
                    break
                page.wait_for_timeout(1000)
            if "auth" not in token:
                raise LoginError("login did not complete (wrong password, captcha, or changed login page)")

            def gql(query, variables):
                r = ctx.request.post(
                    API,
                    headers={"authorization": token["auth"], "content-type": "application/json"},
                    data=json.dumps({"query": query, "variables": variables}),
                )
                if r.status in (401, 403):
                    raise LoginError(f"API returned {r.status}")
                body = r.json()
                if "errors" in body:
                    text = json.dumps(body["errors"])
                    if "UNAUTHENTICATED" in text.upper() or "UNAUTHORIZED" in text.upper():
                        raise LoginError("API says unauthenticated")
                    raise RuntimeError("API errors: " + text[:300])
                return body["data"]

            yield gql
        finally:
            ctx.close()


def fetch_all(gql, experience_id):
    """Return (all submissions, {teamName: official total points}). Raises if the fetch looks partial."""
    v = {"experienceId": experience_id, "first": None, "offset": None}  # null/null = everything, like the app
    s = gql(SUBMISSIONS, v)["experienceStatistics"]["submissions"]
    p = gql(PARTICIPANTS, v)["experienceStatistics"]["participants"]
    subs = [e["node"] for e in s["edges"]]
    parts = [e["node"] for e in p["edges"]]
    if len(subs) != s["totalCount"] or len(parts) != p["totalCount"]:
        raise RuntimeError(f"partial fetch: {len(subs)}/{s['totalCount']} submissions, {len(parts)}/{p['totalCount']} teams")
    official = {x["teamName"]: x["totalPoints"] for x in parts}
    if len(official) != len(parts):
        raise RuntimeError("two teams share a display name; boards would merge them")
    return subs, official
