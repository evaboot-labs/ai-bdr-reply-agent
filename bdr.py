"""Helpers for the AI BDR reply agent. The agent reads each reply to your outbound campaign, sorts it,
drafts the answer and, when the reply points to someone else, finds that person with the Evaboot MCP.
These commands fetch the replies, check the agent's work and send only what you approved.

    python3 bdr.py replies --campaign <id> > queue/replies.json      new replies from Instantly, quotes removed
    python3 bdr.py check queue/replies.json queue/triage.json        every reply sorted, every draft within the rules
    python3 bdr.py review queue/replies.json queue/triage.json       the review list: reply, category, draft
    python3 bdr.py send queue/replies.json queue/triage.json --approve 1,3 [--send]
                                                                     dry run without --send; sends only the approved
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

CATEGORIES = {
    # category: (needs a draft, Instantly interest value or None)
    "interested": (True, 1),
    "question": (True, None),
    "not_now": (True, None),
    "referral": (True, -2),
    "objection": (True, None),
    "not_interested": (True, -1),
    "unsubscribe": (False, -1),   # blocked without approval, so the address never gets another email
    "out_of_office": (False, 0),
    "other": (False, None),
}
MIN_WORDS, MAX_WORDS, MAX_REASON = 15, 120, 25
HANDLED = "data/handled.txt"
LOG = "data/log.jsonl"   # one line per handled reply: category, draft, follow_up_on, referred
QUOTE = re.compile(r"^(On .{5,200}wrote:|Le .{5,200}a écrit|-{2,} ?Original Message|From: .+@|>)", re.M)


def instantly(method, path, body=None):
    key = os.environ.get("INSTANTLY_API_KEY")
    if not key:
        sys.exit("INSTANTLY_API_KEY is not set: write it in .env, then run `set -a; . ./.env; set +a`")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "ai-bdr-reply-agent"}
    req = urllib.request.Request("https://api.instantly.ai/api/v2" + path, method=method, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Instantly {method} {path}: {e.code} {e.read().decode()[:300]}")


def html(text):
    """Instantly drops the line breaks of a text body, so each paragraph also goes as HTML."""
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "".join(f"<p>{esc(p).replace(chr(10), '<br>')}</p>" for p in re.split(r"\n\s*\n", text.strip()))


def handled():
    try:
        return {line.strip() for line in open(HANDLED) if line.strip()}
    except FileNotFoundError:
        return set()


def new_text(email):
    body = email.get("body") or {}
    text = body.get("text") or re.sub(r"<[^>]+>", " ", body.get("html") or "") or email.get("content_preview") or ""
    m = QUOTE.search(text)
    return " ".join((text[:m.start()] if m else text).split())


def replies(campaign):
    """Every reply received on the campaign that is not handled yet, oldest first."""
    done, out, after = handled(), [], None
    while True:
        q = f"/emails?campaign_id={campaign}&email_type=received&limit=100" + (f"&starting_after={after}" if after else "")
        page = instantly("GET", q)
        for e in page.get("items") or []:
            if e["id"] in done:
                continue
            out.append({"id": e["id"], "lead": e.get("lead") or e.get("from_address_email"),
                        "subject": e.get("subject") or "", "text": new_text(e), "received": e.get("timestamp_email"),
                        "eaccount": e.get("eaccount") or (e.get("to_address_email_list") or "").split(",")[0],
                        "thread": e.get("thread_id"), "campaign": campaign})
        after = page.get("next_starting_after")
        if not after:
            break
    out.sort(key=lambda r: r["received"] or "")
    return out


def playbook():
    try:
        return open("PLAYBOOK.md").read()
    except FileNotFoundError:
        return ""


def check(replies_path, triage_path):
    """Problems in the agent's triage. A reply with no verdict, a draft where there should be none, a booking
    link missing from an interested answer, a price the playbook does not hold."""
    reps = {r["id"]: r for r in json.load(open(replies_path))}
    triage = {t.get("id"): t for t in json.load(open(triage_path))}
    book = playbook()
    link = re.search(r"Booking link: (\S+)", book)
    problems = []
    if link and "your-team" in link.group(1):
        problems.append("PLAYBOOK.md still has the example booking link: write yours first")
    for rid, r in reps.items():
        t = triage.get(rid)
        who = r["lead"]
        if not t:
            problems.append(f"{who}: no verdict")
            continue
        cat = t.get("category")
        if cat not in CATEGORIES:
            problems.append(f"{who}: category must be one of {', '.join(CATEGORIES)}")
            continue
        reason = str(t.get("reason") or "").strip()
        if not reason or len(reason.split()) > MAX_REASON:
            problems.append(f"{who}: one reason, under {MAX_REASON} words")
        draft = str(t.get("draft") or "").strip()
        needs = CATEGORIES[cat][0]
        if needs and not draft:
            problems.append(f"{who}: a {cat} reply needs a draft")
        if not needs and draft:
            problems.append(f"{who}: no draft for {cat}")
        if draft:
            n = len(draft.split())
            if not MIN_WORDS <= n <= MAX_WORDS:
                problems.append(f"{who}: draft is {n} words, keep it {MIN_WORDS} to {MAX_WORDS}")
            for price in re.findall(r"[$€£]\s?\d[\d,.]*|\d[\d,.]*\s?(?:USD|EUR|credits?)", draft):
                if price.replace(" ", "") not in book.replace(" ", ""):
                    problems.append(f"{who}: the draft quotes {price!r}, which PLAYBOOK.md does not hold")
        if cat == "interested" and link and link.group(1) not in draft:
            problems.append(f"{who}: an interested reply gets the booking link {link.group(1)}")
        if cat == "not_now" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(t.get("follow_up_on") or "")):
            problems.append(f"{who}: not_now needs follow_up_on as YYYY-MM-DD")
        if cat == "referral" and not (t.get("referred_role") or t.get("referred_name")):
            problems.append(f"{who}: referral needs referred_role or referred_name from the reply")
        found = t.get("referred") or {}
        if found and not found.get("linkedin"):
            problems.append(f"{who}: the referred person needs the LinkedIn URL Evaboot returned")
    for tid in triage:
        if tid not in reps:
            problems.append(f"unknown reply id {tid}")
    return problems


def review(replies_path, triage_path):
    reps = json.load(open(replies_path))
    triage = {t["id"]: t for t in json.load(open(triage_path))}
    for i, r in enumerate(reps, 1):
        t = triage.get(r["id"], {})
        print(f"#{i}  {r['lead']}  [{t.get('category', '?')}]  {t.get('reason', '')}")
        print(f"    they wrote: {r['text'][:300]}")
        if t.get("draft"):
            print("    draft: " + t["draft"].replace("\n", "\n           "))
        if t.get("follow_up_on"):
            print(f"    follow up on {t['follow_up_on']}")
        ref = t.get("referred") or {}
        if ref:
            print(f"    referred: {ref.get('name')}, {ref.get('title')}  {ref.get('linkedin')}  {ref.get('email') or ''}")
        print()


def mark(rid, entry):
    """Records one handled reply at once, so a crash later in the run never sends it twice. The log keeps
    the category, follow-up date and referred person after queue/ is overwritten."""
    os.makedirs(os.path.dirname(HANDLED), exist_ok=True)
    with open(HANDLED, "a") as f:
        f.write(rid + "\n")
    with open(LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def send(replies_path, triage_path, approve, really):
    """Sends the approved drafts as replies in the same thread, and sets each lead's interest status.
    Unsubscribes go to the block list without approval. `other` replies stay for you. Without --send,
    prints what would happen."""
    reps = json.load(open(replies_path))
    triage = {t["id"]: t for t in json.load(open(triage_path))}
    if check(replies_path, triage_path):
        sys.exit("fix the check first: python3 bdr.py check ...")
    done, already = 0, handled()
    for i, r in enumerate(reps, 1):
        t = triage[r["id"]]
        cat, draft = t["category"], str(t.get("draft") or "").strip()
        if r["id"] in already:
            print(f"#{i} {r['lead']}: already handled, skipped")
            continue
        if cat == "other":
            print(f"#{i} {r['lead']}: other, left for you")
            continue
        if draft and i not in approve:
            print(f"#{i} {r['lead']}: not approved, kept for the next review")
            continue
        if cat == "unsubscribe":
            print(f"#{i} {r['lead']}: block list, no reply")
            if really:
                instantly("POST", "/block-lists-entries", {"bl_value": r["lead"]})
        elif draft:
            subject = r["subject"] if r["subject"].lower().startswith("re:") else "Re: " + r["subject"]
            print(f"#{i} {r['lead']}: reply ({len(draft.split())} words)")
            if really:
                instantly("POST", "/emails/reply", {"eaccount": r["eaccount"], "reply_to_uuid": r["id"],
                                                    "subject": subject, "body": {"text": draft, "html": html(draft)}})
        else:
            print(f"#{i} {r['lead']}: {cat}, no reply")
        interest = CATEGORIES[cat][1]
        if interest is not None:
            print(f"    interest status {interest} ({cat})")
            if really:
                instantly("POST", "/leads/update-interest-status",
                          {"lead_email": r["lead"], "interest_value": interest, "campaign_id": r["campaign"]})
        if really:
            mark(r["id"], {"lead": r["lead"], "received": r["received"], **{k: v for k, v in t.items() if k != "id"}})
        done += 1
    print(f"{done} handled" + ("" if really else " (dry run: add --send)"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("replies").add_argument("--campaign", required=True)
    for name in ("check", "review", "send"):
        a = sub.add_parser(name)
        a.add_argument("replies")
        a.add_argument("triage")
    a.add_argument("--approve", default="", help="review numbers to send, e.g. 1,3; 'all' for every draft")
    a.add_argument("--send", action="store_true")
    args = ap.parse_args()
    if args.cmd == "replies":
        print(json.dumps(replies(args.campaign), indent=2, ensure_ascii=False))
    elif args.cmd == "check":
        problems = check(args.replies, args.triage)
        for p in problems:
            print("FAIL", p)
        print(f"{len(problems)} problems")
        sys.exit(1 if problems else 0)
    elif args.cmd == "review":
        review(args.replies, args.triage)
    else:
        n = len(json.load(open(args.replies)))
        approve = set(range(1, n + 1)) if args.approve == "all" else {int(x) for x in args.approve.split(",") if x.strip()}
        send(args.replies, args.triage, approve, args.send)


if __name__ == "__main__":
    main()
