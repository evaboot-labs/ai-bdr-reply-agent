---
name: ai-bdr-reply-agent
description: Handle the replies to an outbound email campaign like a BDR - fetch new replies from Instantly, sort each one (interested, question, not now, referral, objection, unsubscribe, out of office), draft the answer from PLAYBOOK.md, find the person a referral points to with the Evaboot MCP, and send only the answers the user approves. Use when the user asks for an AI BDR, reply handling, inbox triage, or "answer my replies".
---

# AI BDR reply agent

This skill runs inside a clone of https://github.com/evaboot-labs/ai-bdr-reply-agent: it uses the repo's `bdr.py`, `PLAYBOOK.md` and `docs/`. If `bdr.py` is not in the working directory, clone the repo and work from there.

You read and sort the replies and write the drafts yourself. `bdr.py` fetches the replies from Instantly, checks your work and sends what the user approved. The Evaboot MCP server (`https://mcp.evaboot.com/mcp`) finds the people a referral points to.

## Rules

- **Nothing is sent without the user's approval.** Show the review, then wait for the numbers to send.
- Use only the facts in `PLAYBOOK.md`. Never invent a price, a customer, a feature or a date.
- Never guess gender: use the first name or "they".
- Never ask for or paste an API key. The user writes `INSTANTLY_API_KEY` and `EVABOOT_API_KEY` into `.env` (`docs/connect-your-agent.md`).
- A referral lookup can cost Evaboot credits (1 per email found). Say so before you look up an email.

## Step 0: check the setup

1. Run `mkdir -p data queue`. If `INSTANTLY_API_KEY` is not set, run `set -a; . ./.env; set +a`. If it is still empty, walk the user through `docs/connect-your-agent.md`.
2. Read `PLAYBOOK.md`. If it says `Status: EXAMPLE`, ask the user for their booking link, their pricing page, the prices they allow you to quote (if any), and their offer in one line. Rewrite the file and set `Status: yours`.
3. Ask which Instantly campaign to work on, or list them: `curl -s -H "Authorization: Bearer $INSTANTLY_API_KEY" "https://api.instantly.ai/api/v2/campaigns?limit=50"`.

## Step 1: fetch the replies

```bash
python3 bdr.py replies --campaign <campaign_id> > queue/replies.json
```

Only replies not handled before come back, with the quoted original removed.

## Step 2: sort and draft

Write `queue/triage.json`, one entry per reply: `{"id", "category", "reason", "draft"}`, plus `follow_up_on` (YYYY-MM-DD) for `not_now`, and `referred_role` or `referred_name` for `referral`. The categories and what each one gets are the table in `PLAYBOOK.md`. No draft for `unsubscribe`, `out_of_office` and `other`.

## Step 3: find the person a referral points to

For each `referral`:

1. Find the company: `search_sn_accounts` with `https://www.linkedin.com/sales/search/company?query=(keywords%3A<company name>)`. Pick the account that matches the lead's company; its `entityUrn` ends in the company id.
2. List its people: `search_sn_leads` (`count: 25`, free) with
   `https://www.linkedin.com/sales/search/people?query=(filters%3AList((type%3ACURRENT_COMPANY%2Cvalues%3AList((id%3Aurn%253Ali%253Aorganization%253A<id>%2Ctext%3A<company name>%2CselectionType%3AINCLUDED)))))`.
   Read every title yourself and pick the person the reply points to. Page with `start` if the company is large.
3. Add `"referred": {"name", "title", "linkedin"}` to the entry. If the user wants the email, confirm the credit, then `find_email_single` and add `email`.

Do not use `build_sn_search_from_prompt` for this: when it cannot match the company, it falls back to the name as profile text and returns people from other companies. If no account matches, or no title fits, leave `referred` out and tell the user: never guess a person.

## Step 4: check, review, send

```bash
python3 bdr.py check queue/replies.json queue/triage.json
python3 bdr.py review queue/replies.json queue/triage.json
```

Fix every `FAIL`, then show the review. When the user names the drafts to send:

```bash
python3 bdr.py send queue/replies.json queue/triage.json --approve 1,3          # dry run
python3 bdr.py send queue/replies.json queue/triage.json --approve 1,3 --send
```

The answers go out from the same mailbox, in the same thread. Each lead's interest status is set, and unsubscribes go to the block list without approval, so tell the user which addresses will be blocked. Every handled reply is written to `data/handled.txt` at once, so it never comes back or goes out twice, and to `data/log.jsonl` with its category, follow-up date and referred person. Drafts that were not approved, and `other` replies, stay for the next review.

## Every day

Run steps 1 to 4 once or twice a day. Or set up the n8n version (`docs/n8n.md`): it sorts and drafts every hour into a Google Sheet, and sends a row when the user writes `yes` in its Send column.
