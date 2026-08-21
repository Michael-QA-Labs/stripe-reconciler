# Conventions

Stable across every stage. Load this with any stage that writes code.

## Python

- **3.13**, pinned. See `D-001`.
- `uv venv --python 3.13` for the environment, `uv pip install -r
  requirements-dev.txt` to install. uv for speed; plain requirements files so
  CI and Render read them without needing uv.
- **Two requirements files.** `requirements.txt` is the service alone, because
  Render's buildCommand installs it directly. `requirements-dev.txt` includes it
  and adds the test and reporting stack.
- **Every dependency pinned to an exact version, with a why-comment** where the
  choice is not obvious.

## Git

- **Commit straight to `main`.** No feature branches. This is a solo repo and
  branching adds a step for no benefit.
- Commit at every stage boundary at minimum, more often when a piece works.
- `.env` is gitignored from the first commit, before any secret exists on disk.
  The WAL sidecars (`*.db-wal`, `*.db-shm`) are gitignored too; they appear
  beside the database the moment stage 01 runs.

## Tests

- **Every bug found ships with a regression test pinning it, in the same commit
  as the fix.** The suite is built as the project is built. There is no testing
  phase at the end.
- Tests never read the database directly. They hit `GET /test/payments/{id}`,
  which is gated behind `TESTING=true` and 404s otherwise. That keeps tests
  decoupled from the schema and matches how a real team inspects service state.
- Live-Stripe tests carry `@pytest.mark.live` and run serially. Everything else
  parallelizes.
- A stage is not done because the code looks right. It is done when a command
  passes and its output is pasted into `RESULT.md`.

## Writing

- **No em dashes or en dashes**, anywhere: docs, comments, commit messages,
  README. Use commas, colons, parentheses, or a full stop.
- Docs state what is true now. Aspirations go in `DECISIONS.md` or the v2 plan,
  not in present tense.
- A file that cites a decision by number (`D-014`) must list `DECISIONS.md` in
  its Inputs. A cited decision with no route to it cannot be read from inside
  the stage, and the citation reads as satisfied when it is not.
- A stage's **Outputs** list names principal artifacts. A supporting file that
  exists only to serve one of them, a stylesheet for a named page or a helper
  beside a named suite, is implied and does not need listing. Anything that is
  not merely serving a named artifact is never implied: a new module, endpoint,
  dependency, or committed asset gets named in the contract or asked about
  before it is added.

## Code

- Minimum code that solves the problem. No speculative abstraction, no
  configurability nobody asked for, no error handling for impossible states.
- Match the surrounding style. Change only what the current stage requires.
- The state machine is the exception to brevity: it is the piece a reader is
  meant to study, so it gets clear naming and comments explaining the ordering
  rules.
