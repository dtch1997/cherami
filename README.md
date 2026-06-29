# cherami

A minimal system for learning French, structured around **things you actually
want to say**. You write short letters to friends in French; Claude corrects
them, distils each place you struggled into a **bite-size lesson card** (grammar
or vocab, with the *general principle* spelled out), and those cards come back on
a **spaced-repetition** schedule until you have them down.

The design is deliberately tiny: **Claude is the tutor, a file is the database.**
There is no app server and no LLM API plumbing — just markdown letters, a
JSONL card store, and a small CLI that keeps the store consistent.

```
letters/*.md   ──correct──▶  gaps  ──distil──▶  cards.jsonl  ──review──▶  you
   (you write)    (Claude)            (Claude)                  (SRS, Claude quizzes)
```

## The loop

1. **Write** — Put a letter in `letters/NNN-topic.md`. Write as much French as
   you can; where you get stuck, drop into English or mark a `[gap]` in
   brackets. The point is to surface what you *want to say but can't yet*.
2. **Correct** — Ask Claude to mark it up. You get a corrected version, inline
   explanations, and a list of the specific gaps (grammar + vocab).
3. **Distil** — Claude turns each gap into one or more cards via
   `cherami.py add`, capturing the underlying **principle**, not just the fix.
4. **Review** — Ask Claude to "review french". It pulls due cards
   (`cherami.py due`), quizzes you, and records each result
   (`cherami.py grade ...`). Cards you miss come back sooner; cards you know
   drift further out.

## CLI

Stdlib-only, no install needed (use `python3`; alias to `python` if you like):

```bash
python3 cherami.py stats                 # how many cards, how many due
python3 cherami.py due                    # cards due today
python3 cherami.py list --tag passe-compose
python3 cherami.py show c0007
python3 cherami.py grade c0007 good       # again | good | easy
python3 cherami.py add --type grammar \
  --front "I went to the market (passé composé)" \
  --back  "Je suis allé au marché" \
  --note  "aller is an être verb → use être + past participle; agree the participle with the subject (allée if feminine)." \
  --tags  passe-compose,etre-verbs,agreement \
  --letter 001-vacances --you-wrote "J'ai allé au marché" --should-be "Je suis allé au marché"
```

## Card schema (one JSON object per line in `cards.jsonl`)

```jsonc
{
  "id": "c0001",
  "type": "grammar",            // grammar | vocab | phrase
  "front": "prompt shown first (EN→FR, fill-in-the-blank, or 'how do you say…')",
  "back": "the answer in French",
  "note": "the GENERAL PRINCIPLE — the rule/pattern, not just this instance",
  "tags": ["passe-compose", "agreement"],
  "source": {                   // where this came from, so review has context
    "letter": "001-vacances",
    "you_wrote": "J'ai allé au marché",
    "should_be": "Je suis allé au marché"
  },
  "created": "2026-06-29",
  "srs": {"due": "2026-06-29", "interval": 0, "reps": 0, "lapses": 0, "ease": 2.5}
}
```

## Spaced repetition (provisional)

The scheduler in `cherami.py` (`schedule()`) is a small SM-2-lite:

- **again** → reps reset, ease −0.20 (floor 1.3), due today.
- **good** → interval 1d, then 3d, then `interval × ease`.
- **easy** → bigger jumps, ease +0.15.

It is intentionally simple and isolated in one pure function so it's easy to
swap (full SM-2, FSRS, Leitner boxes, or Anki export) once there are enough
cards to know what we want. The card store already carries the state any of
those would need.

## For Claude (how to drive this)

- **Correcting a letter:** read `letters/NNN-*.md`, append a `## Correction`
  section (corrected text + brief explanations), then create one card per
  distinct gap. Prefer fewer, principle-level cards over many near-duplicates.
  Always fill `note` with the *generalisable* rule and set `source` so review
  has context.
- **Review session:** run `python3 cherami.py due --json`, quiz the user one card
  at a time (show `front`, withhold `back`), then `grade` each based on their
  answer. Re-teach from `note` when they miss one.
