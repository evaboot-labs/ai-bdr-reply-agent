# Run it in n8n

[`n8n/ai-bdr-reply-agent.json`](../n8n/ai-bdr-reply-agent.json) is the same reply agent for n8n. Every hour it sorts and drafts the new replies of your Instantly campaign into a Google Sheet; you write `yes` in the Send column, and it sends.

## What runs

**Sort** (every hour):

1. **Get the replies** (HTTP Request): the replies received on your campaign, from the Instantly API.
2. **Replies so far** and **New replies** (Code): keeps only the replies not in the sheet yet, and removes the quoted original.
3. **Sort and draft** (AI Agent with Claude): one category per reply, a reason, and a draft from the playbook in the settings.
4. **Check the drafts** (Code): the same rules as `bdr.py check`. A draft that breaks one is dropped, and the Check column says why.
5. **Add to Replies**: one row per reply, with an empty Send column.

**Send** (every 15 minutes):

1. **Replies** and **Approved or unsubscribe** (Code): rows with `ok` in Check and nothing in Sent: those with `yes` in Send, plus every unsubscribe. Unsubscribes are blocked without approval, so the address never gets another email.
2. **Reply or block**: the draft goes out as a reply in the same thread, from the same mailbox; an unsubscribe goes to your block list.
3. **Set interest status**: interested, wrong person or not interested, in Instantly.
4. **Mark as sent**: the time in the Sent column, so a row is never sent twice.

## Set it up

1. **Make the sheet:** a Google Sheet with this header row:
   `Received, Id, Lead, They wrote, Category, Reason, Draft, Follow up on, Referred, Check, Send, Sent, Subject, Mailbox, Campaign`
2. **Import** the JSON in n8n: *Workflows > Import from file*.
3. **Add three credentials:**
   - **Header Auth** named `Instantly API key`: name `Authorization`, value `Bearer <your Instantly API v2 key>`. Select it on the three Instantly nodes.
   - **Anthropic** on the Claude node.
   - **Google Sheets** on the three sheet nodes.
4. **Fill in Sort settings:** `instantly_campaign_id`, `replies_tab_url` (with its `gid`), and `playbook`: your offer, booking link, pricing page and the prices you allow. The check refuses every draft while the playbook still has the example booking link. **Send settings** only needs the same `replies_tab_url`.
5. **Publish** the workflow.
6. **Test:** click **Execute workflow** on **Every hour**, read the new rows, write `yes` in Send on one of them, then click **Execute workflow** on **Every 15 minutes**.

## Good to know

- A draft is only sent from the Draft column, so you can edit it in the sheet before you write `yes`.
- The referral lookup (finding the person they named in Sales Navigator) is in the agent version: the Referred column tells you who to look for.
- Rows marked `not_now` carry a Follow up on date. Filter the sheet on it to plan the next touch.
- A failed send leaves the row without a Sent time, so it is tried again 15 minutes later; the other rows still go out.
- Each hourly run reads the latest 100 replies. On a campaign with more than 100 replies, the first run starts from the newest ones.

Back to the [README](../README.md).
