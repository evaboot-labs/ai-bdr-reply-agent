# Agent instructions

This repo is an AI BDR reply agent. It handles the replies to the user's outbound email campaign in Instantly: it sorts each reply, drafts the answer from the user's playbook, finds the person a referral points to with Evaboot, and sends only the answers the user approves. When the user asks for an AI BDR, reply handling or "answer my replies":

1. Follow the skill in `skills/ai-bdr-reply-agent/SKILL.md` step by step.
2. Read `PLAYBOOK.md` for the facts you may use and the rule for each kind of reply. If it says `Status: EXAMPLE`, ask the user and update it.
3. Use `bdr.py` to fetch the replies, check your triage, show the review and send. The Evaboot MCP server does the Sales Navigator work (`.mcp.json`).
4. If the user is not connected yet, follow `docs/connect-your-agent.md` with them.
5. If the user wants n8n instead, follow `docs/n8n.md` with them one step at a time: you cannot click inside n8n, so say exactly what to do and wait for their confirmation.

Never send a reply the user did not approve. Never state a fact that is not in `PLAYBOOK.md`. Confirm before any Evaboot email lookup (1 credit each). Never ask for or handle an API key: the user writes it into `.env`. Never commit `.env`, `data/` or `queue/`: they hold real people's emails.
