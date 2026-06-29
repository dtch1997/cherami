#!/usr/bin/env python3
"""cherami — a minimal French-learning card store + spaced-repetition CLI.

The workflow is "Claude in the loop": you write letters in French (`letters/`),
Claude corrects them, distils each gap into a card here, and drives review
sessions. This script just keeps the card store (`cards.jsonl`) consistent so
nobody has to hand-edit JSONL. See README.md for the full loop.

Stdlib only. Run: `python cherami.py <command>`.

Commands:
  add      Add a card.            (flags below)
  due      List cards due today.  [--tag T] [--json]
  list     List all cards.        [--tag T] [--json]
  show ID  Show one card in full.
  grade ID GRADE   Update scheduling. GRADE = again|good|easy
  edit ID  Edit fields of a card. (same flags as add)
  stats    Counts + how many are due.

add/edit flags:
  --type {grammar,vocab,phrase}  --front TEXT  --back TEXT  --note TEXT
  --tags a,b,c  --letter NAME  --you-wrote TEXT  --should-be TEXT
"""
import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CARDS = os.path.join(ROOT, "cards.jsonl")

# --- SRS: provisional SM-2-lite. Easy to swap; see README "Spaced repetition". ---
EASE_FLOOR = 1.3


def today():
    return datetime.date.today()


def parse_date(s):
    return datetime.date.fromisoformat(s)


def schedule(srs, grade):
    """Return a new srs dict after grading. Pure function of (srs, grade)."""
    reps = srs.get("reps", 0)
    ease = srs.get("ease", 2.5)
    lapses = srs.get("lapses", 0)
    interval = srs.get("interval", 0)

    if grade == "again":
        reps, lapses, interval = 0, lapses + 1, 0
        ease = max(EASE_FLOOR, ease - 0.20)
    elif grade == "good":
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 3
        else:
            interval = max(1, round(interval * ease))
        reps += 1
    elif grade == "easy":
        ease += 0.15
        interval = 4 if reps == 0 else max(1, round(interval * ease * 1.3))
        reps += 1
    else:
        raise SystemExit(f"unknown grade {grade!r}; use again|good|easy")

    due = today() + datetime.timedelta(days=interval)
    return {
        "due": due.isoformat(),
        "interval": interval,
        "reps": reps,
        "lapses": lapses,
        "ease": round(ease, 2),
    }


# --- store ---
def load():
    if not os.path.exists(CARDS):
        return []
    out = []
    with open(CARDS) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def save(cards):
    tmp = CARDS + ".tmp"
    with open(tmp, "w") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    os.replace(tmp, CARDS)


def next_id(cards):
    n = 0
    for c in cards:
        try:
            n = max(n, int(c["id"].lstrip("c")))
        except (ValueError, KeyError):
            pass
    return f"c{n + 1:04d}"


def find(cards, cid):
    for c in cards:
        if c["id"] == cid:
            return c
    raise SystemExit(f"no card with id {cid!r}")


# --- rendering ---
def fmt_row(c):
    tags = ",".join(c.get("tags", []))
    due = c.get("srs", {}).get("due", "?")
    front = c.get("front", "").replace("\n", " ")
    if len(front) > 60:
        front = front[:57] + "..."
    return f"{c['id']}  {due}  [{c.get('type','?'):7}] {front}   ({tags})"


def show_card(c):
    print(json.dumps(c, ensure_ascii=False, indent=2))


# --- commands ---
def apply_fields(card, args):
    if args.type is not None:
        card["type"] = args.type
    if args.front is not None:
        card["front"] = args.front
    if args.back is not None:
        card["back"] = args.back
    if args.note is not None:
        card["note"] = args.note
    if args.tags is not None:
        card["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    src = card.setdefault("source", {})
    if args.letter is not None:
        src["letter"] = args.letter
    if getattr(args, "you_wrote") is not None:
        src["you_wrote"] = args.you_wrote
    if getattr(args, "should_be") is not None:
        src["should_be"] = args.should_be


def cmd_add(args):
    cards = load()
    cid = next_id(cards)
    card = {
        "id": cid,
        "type": "vocab",
        "front": "",
        "back": "",
        "note": "",
        "tags": [],
        "source": {},
        "created": today().isoformat(),
        "srs": {"due": today().isoformat(), "interval": 0, "reps": 0, "lapses": 0, "ease": 2.5},
    }
    apply_fields(card, args)
    if not card["front"] or not card["back"]:
        raise SystemExit("add requires at least --front and --back")
    cards.append(card)
    save(cards)
    print(cid)


def cmd_edit(args):
    cards = load()
    apply_fields(find(cards, args.id), args)
    save(cards)
    print(f"updated {args.id}")


def cmd_grade(args):
    cards = load()
    card = find(cards, args.id)
    card["srs"] = schedule(card.get("srs", {}), args.grade)
    save(cards)
    print(f"{args.id} -> due {card['srs']['due']} (interval {card['srs']['interval']}d)")


def _filter(cards, tag, due_only):
    out = cards
    if tag:
        out = [c for c in out if tag in c.get("tags", [])]
    if due_only:
        t = today()
        out = [c for c in out if parse_date(c.get("srs", {}).get("due", t.isoformat())) <= t]
    return out


def cmd_due(args):
    rows = _filter(load(), args.tag, due_only=True)
    rows.sort(key=lambda c: c.get("srs", {}).get("due", ""))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("Nothing due. \U0001F37B")
        return
    for c in rows:
        print(fmt_row(c))


def cmd_list(args):
    rows = _filter(load(), args.tag, due_only=False)
    rows.sort(key=lambda c: c["id"])
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    for c in rows:
        print(fmt_row(c))


def cmd_show(args):
    show_card(find(load(), args.id))


def cmd_stats(args):
    cards = load()
    due = _filter(cards, None, due_only=True)
    by_type, by_tag = {}, {}
    for c in cards:
        by_type[c.get("type", "?")] = by_type.get(c.get("type", "?"), 0) + 1
        for t in c.get("tags", []):
            by_tag[t] = by_tag.get(t, 0) + 1
    print(f"cards: {len(cards)}   due today: {len(due)}")
    if by_type:
        print("by type: " + ", ".join(f"{k}={v}" for k, v in sorted(by_type.items())))
    if by_tag:
        top = sorted(by_tag.items(), key=lambda kv: -kv[1])[:12]
        print("top tags: " + ", ".join(f"{k}={v}" for k, v in top))


def build_parser():
    p = argparse.ArgumentParser(description="cherami — minimal French SRS card store")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_field_flags(sp):
        sp.add_argument("--type", choices=["grammar", "vocab", "phrase"])
        sp.add_argument("--front")
        sp.add_argument("--back")
        sp.add_argument("--note")
        sp.add_argument("--tags")
        sp.add_argument("--letter")
        sp.add_argument("--you-wrote", dest="you_wrote")
        sp.add_argument("--should-be", dest="should_be")

    sp = sub.add_parser("add"); add_field_flags(sp); sp.set_defaults(func=cmd_add)
    sp = sub.add_parser("edit"); sp.add_argument("id"); add_field_flags(sp); sp.set_defaults(func=cmd_edit)
    sp = sub.add_parser("grade"); sp.add_argument("id"); sp.add_argument("grade"); sp.set_defaults(func=cmd_grade)
    sp = sub.add_parser("due"); sp.add_argument("--tag"); sp.add_argument("--json", action="store_true"); sp.set_defaults(func=cmd_due)
    sp = sub.add_parser("list"); sp.add_argument("--tag"); sp.add_argument("--json", action="store_true"); sp.set_defaults(func=cmd_list)
    sp = sub.add_parser("show"); sp.add_argument("id"); sp.set_defaults(func=cmd_show)
    sp = sub.add_parser("stats"); sp.set_defaults(func=cmd_stats)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
