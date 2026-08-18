# stripe-reconciler build factory

The pipeline that produces the service. What leaves it: a deployed webhook
receiver and a test suite that proves it handles unordered, duplicate, and late
delivery.

Built on ICM. Folders carry sequencing, hierarchy carries context, files carry
state. If something needs explaining, the explanation goes in that folder's
`CONTEXT.md`, not in your head.

## Where things live

| Path | What it holds |
|---|---|
| `CONTEXT.md` | the pipeline definition, the deviations, the ship gate |
| `DECISIONS.md` | every settled "why", numbered `D-NNN` |
| `_shared/` | factory reference, stable across all stages |
| `stages/` | the pipeline, in execution order |
| `../service/`, `../tests/`, `../web/`, `../docs/` | the product |

## Find the current stage

```
ls _build/stages/*/RESULT.md
```

The first stage folder **without** a `RESULT.md` is the current one. Open its
`CONTEXT.md` and work from there. That scan is the only status surface; there is
no status file to read or maintain.

## Route by what you need

| If you need | Go to |
|---|---|
| to start or resume work | the scan above, then that stage's `CONTEXT.md` |
| to report status | the scan above |
| a code or repo convention | `_shared/conventions.md` |
| a Stripe fact (cards, limits, secrets, API version) | `_shared/stripe-facts.md` |
| to know why a choice was made | `DECISIONS.md` |
| the shape of the whole pipeline | `CONTEXT.md` |
| the original intent behind the project | `_shared/scope-original.md` (rarely) |

Load a stage's contract, its named references, and its inputs. Not this whole
folder. `_shared/scope-original.md` is roughly 4k tokens and is on every stage's
do-not-load line by default.

## The one rule

Nothing moves to the next stage until a person has read the previous stage's
`RESULT.md`.
