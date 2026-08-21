# 00_prereqs: get the tools and the secret

One job: reach the point where `stripe listen --print-secret` returns a value.
That secret backs every signature and replay test in stages 04a and 04b, so
nothing downstream is real until it exists.

Timebox: half a day. This stage is blocking.

## Inputs

- Reference (every run): ../../_shared/conventions.md
- Reference (fill in its capture table): ../../_shared/stripe-facts.md

Do NOT load: `../../_shared/scope-original.md`, any other stage's contract,
`../../CONTEXT.md`.

## Process

1. Confirm the Stripe CLI is installed and authenticated:
   ```
   stripe --version                      # 1.50.1 via brew stripe-cli, already installed
   stripe balance retrieve >/dev/null && echo AUTHED || echo "run: stripe login"
   stripe listen --print-secret          # must print whsec_...
   ```
   If not authenticated, run `stripe login` (interactive: it opens a browser and
   waits on a pairing code, so a human runs it, not an agent). `stripe login`
   mints a **restricted** key valid 90 days, listed under *Restricted keys* on
   the dashboard API keys page under this device's name, not under *Standard
   keys*. That distinction matters when revoking one.
   **Never run `stripe config --list`.** It prints the test secret key in full.
   Use `stripe config --list | grep -c test_mode_api_key` to check that a key
   exists without displaying it. See `D-010`.
2. Install the Allure CLI now, not in stage 07. It is Java-backed and the
   install is the kind of thing that derails a session at the finish line:
   ```
   brew install allure
   ```
3. Create the virtualenv: `uv venv --python 3.13` (see `D-001`).
4. Fill in the capture table in `../../_shared/stripe-facts.md`: the pinned API
   version string and the current test-mode rate limit. Read them from the
   dashboard and the Stripe docs, not from memory.
5. Write `.env.example` at the repo root, naming **both** signing secrets
   distinctly and never holding a real value:
   ```
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET_CLI=whsec_...        # from: stripe listen --print-secret
   STRIPE_WEBHOOK_SECRET_DASHBOARD=whsec_...  # from the dashboard, after stage 01 deploys
   TESTING=false
   ```
6. Write the real `.env` (gitignored). **Pipe the values, never echo them**, so
   no secret enters a terminal transcript:
   ```
   umask 077
   {
     echo "STRIPE_SECRET_KEY=$(stripe config --list | sed -n 's/^test_mode_api_key = .\(.*\).$/\1/p')"
     echo "STRIPE_WEBHOOK_SECRET_CLI=$(stripe listen --print-secret)"
     echo "STRIPE_WEBHOOK_SECRET_DASHBOARD="
     echo "TESTING=false"
   } > .env
   ```
   `umask 077` makes the file owner-readable only. The dashboard secret stays
   empty until stage 01 deploys. Verify with `wc -l .env`, not by printing it.
7. Set the GitHub repo secrets: `STRIPE_SECRET_KEY`,
   `STRIPE_WEBHOOK_SECRET_CLI`. The dashboard one is added in stage 01.

## Outputs

- `.env.example` (committed)
- `.env` (gitignored, real values)
- `.venv/` (gitignored)
- `_build/_shared/stripe-facts.md` capture table filled in
- `_build/stages/00_prereqs/RESULT.md`

## Human check

Run `git status` and confirm `.env` does **not** appear. Then open
`.env.example` and confirm the two webhook secrets have visibly different names
and a comment saying where each comes from. Mixing these two up is the single
most likely afternoon lost on this project.
