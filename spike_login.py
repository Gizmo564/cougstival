"""Phase 0: can we log in to Goosechase Studio unattended and pull submissions?

Run on the Linux box:
    pip install playwright && playwright install --with-deps chromium
    export GC_EMAIL='...' GC_PASSWORD='...'
    python3 spike_login.py            # headless first
    python3 spike_login.py --headed   # if headless fails (e.g. a captcha)

It reuses a saved browser profile, so after one successful login it may not need to log in again.
Nothing secret is printed (the token is never shown).
"""
import base64
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

CFG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")))
EXP = CFG["experience_id"]
API = "https://api.goosechase.com/studio"
PROFILE = os.path.expanduser("~/.cache/cougstival-profile")
QUERY = """query S($experienceId: ID!, $first: Int, $offset: Int) {
  experienceStatistics(experienceId: $experienceId) {
    submissions(first: $first, offset: $offset) {
      totalCount
      edges { node { teamName missionPoints bonusPoints submissionCreatedAt } }
    }
  }
}"""


def jwt_expiry(auth):
    """Seconds until the token expires, or None if it isn't a readable JWT."""
    try:
        payload = auth.split()[-1].split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))["exp"] - time.time()
    except Exception:
        return None


def main():
    headed = "--headed" in sys.argv
    email, password = os.environ.get("GC_EMAIL"), os.environ.get("GC_PASSWORD")
    token = {}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFILE, headless=not headed)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_request(req):
            auth = req.headers.get("authorization")
            if req.url.startswith(API) and auth:
                token["auth"] = auth
        page.on("request", on_request)

        page.goto(f"https://studio.goosechase.com/experience/{EXP}/participants")
        page.wait_for_timeout(4000)

        if "auth" not in token and page.locator("input[type=password]").count():
            if not (email and password):
                sys.exit("Login page shown, but GC_EMAIL / GC_PASSWORD are not set.")
            print("login page shown: filling credentials")
            page.locator("input[type=email], input[name=email], input[type=text]").first.fill(email)
            page.locator("input[type=password]").first.fill(password)
            page.locator("button[type=submit]").first.click()

        for _ in range(60):  # wait up to ~60s for the app to call the API with a token
            if "auth" in token:
                break
            page.wait_for_timeout(1000)

        if "auth" not in token:
            page.screenshot(path="spike_failed.png")
            ctx.close()
            sys.exit("FAILED: never saw an authenticated API call. Saved spike_failed.png. "
                     "If it shows a captcha, rerun with --headed; if headed works, we use the manual-login plan.")

        left = jwt_expiry(token["auth"])
        print("token captured; expires in", f"{left/60:.0f} min" if left is not None else "unknown (not a readable JWT)")

        r = ctx.request.post(API, headers={"authorization": token["auth"], "content-type": "application/json"},
                             data=json.dumps({"query": QUERY, "variables": {"experienceId": EXP, "first": 5, "offset": 0}}))
        body = r.json()
        print("API status:", r.status)
        if "errors" in body:
            print("API errors:", json.dumps(body["errors"])[:500])
        else:
            subs = body["data"]["experienceStatistics"]["submissions"]
            print("totalCount:", subs["totalCount"])
            for e in subs["edges"][:3]:
                print(" ", e["node"])
            print("OK: login + data pull works")
        ctx.close()


if __name__ == "__main__":
    main()
