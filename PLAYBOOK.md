# How you answer replies

Status: EXAMPLE. Your agent asks you and replaces this line with "Status: yours" once the file is yours.

## What you sell, in one line

Evaboot exports Sales Navigator searches to clean lists with verified emails, and can send each week's new people straight to the CRM.

## Facts the agent may use

Booking link: https://cal.com/your-team/20min
Pricing page: https://evaboot.com/pricing
Prices you may quote: none. For any price question, answer with the pricing page.

Never state a number, a customer name or a feature that is not in this file.

## One rule per kind of reply

| Category | What it looks like | What the agent does |
|---|---|---|
| `interested` | "Sounds good, let's talk" | Short thanks, the booking link, two sentences at most. Interest status: interested. |
| `question` | "How does it work with HubSpot?" | Answers from the facts above only, then offers a call. If the answer is not here, says a colleague will reply. |
| `not_now` | "Not this quarter" | Thanks them, says when you will check back. Sets `follow_up_on` to the date they gave, or 90 days later. |
| `referral` | "Talk to our Head of Growth" | Thanks them, asks for a short intro. Finds the person they named with Evaboot, for you to contact next. Interest status: wrong person. |
| `objection` | "We already use another tool" | One sentence that acknowledges it, one difference from the facts above, no pressure. |
| `not_interested` | "Not interested" | One polite line, no pitch. Interest status: not interested. |
| `unsubscribe` | "Remove me" | No reply. Added to the block list. |
| `out_of_office` | Auto-reply | No reply. The sequence resumes on its own. |
| `other` | Anything else | No draft. Left for you. |

## The tone

- Plain text, first name, no greeting line longer than "Hi Ana,".
- 15 to 120 words. Most answers fit in 40.
- Sign with your first name only.
- Never argue, never repeat the original pitch, never add a second call to action.
