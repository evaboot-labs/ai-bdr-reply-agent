"""Builds n8n/ai-bdr-reply-agent.json. Run: python3 n8n/build_workflow.py

Two entry points in one workflow:

1. Sort: every hour, the workflow reads the new replies of your Instantly campaign, lets Claude sort each one
   and draft the answer from your playbook, checks the drafts like bdr.py check, and adds one row per
   reply to the Replies tab. Nothing is sent.
2. Send: every 15 minutes, it sends the rows you marked "yes" in the Send column as replies in the same
   thread, sets the lead's interest status, blocks unsubscribes, and writes the time in the Sent column.
"""
import json
import uuid
from pathlib import Path

ANTHROPIC_CRED = {"anthropicApi": {"id": "", "name": "Anthropic"}}
SHEETS_CRED = {"googleSheetsOAuth2Api": {"id": "", "name": "Google Sheets account"}}
INSTANTLY_CRED = {"httpHeaderAuth": {"id": "", "name": "Instantly API key"}}
MODEL = "claude-sonnet-5-5"

PLAYBOOK = """What we sell: Evaboot exports Sales Navigator searches to clean lists with verified emails, and can send each week's new people straight to the CRM.
Booking link: https://cal.com/your-team/20min
Pricing page: https://evaboot.com/pricing
Prices you may quote: none. For any price question, answer with the pricing page.
Never state a number, a customer name or a feature that is not in this playbook."""

nodes, connections = [], {}


def node(name, type_, version, params, pos, creds=None, **extra):
    n = {"parameters": params, "id": str(uuid.uuid4()), "name": name, "type": type_,
         "typeVersion": version, "position": pos, **extra}
    if creds:
        n["credentials"] = creds
    nodes.append(n)


def link(a, b, kind="main", out=0):
    connections.setdefault(a, {}).setdefault(kind, [])
    while len(connections[a][kind]) <= out:
        connections[a][kind].append([])
    connections[a][kind][out].append({"node": b, "type": kind, "index": 0})


def code(name, js, pos, **extra):
    node(name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos, **extra)


def sheet(name, op, url_expr, pos, executeOnce=False, **params):
    p = {"operation": op,
         "documentId": {"__rl": True, "mode": "url", "value": url_expr},
         "sheetName": {"__rl": True, "mode": "url", "value": url_expr}, "options": {}, **params}
    extra = {"alwaysOutputData": True} if op == "read" else {}
    if executeOnce:
        extra["executeOnce"] = True
    node(name, "n8n-nodes-base.googleSheets", 4.7, p, pos, SHEETS_CRED, **extra)


def settings(name, pos):
    node(name, "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
        {"id": str(uuid.uuid4()), "name": k, "type": "string", "value": v} for k, v in [
            ("instantly_campaign_id", "PASTE_THE_INSTANTLY_CAMPAIGN_ID"),
            ("replies_tab_url", "PASTE_THE_REPLIES_TAB_URL_WITH_GID"),
            ("playbook", PLAYBOOK),
        ]]}, "includeOtherFields": True, "options": {}}, pos)


def instantly(name, method, url, body, pos, **extra):
    p = {"method": method, "url": url, "authentication": "genericCredentialType",
         "genericAuthType": "httpHeaderAuth", "options": {}}
    if body:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    node(name, "n8n-nodes-base.httpRequest", 4.2, p, pos, INSTANTLY_CRED, **extra)


NEW_JS = r"""
// The replies not in the Replies tab yet, oldest first, with the quoted original removed.
const seen = new Set($('Replies so far').all().map(r => String(r.json['Id'] || '')).filter(Boolean));
const QUOTE = /^(On .{5,200}wrote:|Le .{5,200}a écrit|-{2,} ?Original Message|From: .+@|>)/m;
const text = e => {
  const t = (e.body && (e.body.text || String(e.body.html || '').replace(/<[^>]+>/g, ' '))) || e.content_preview || '';
  const m = t.match(QUOTE);
  return (m ? t.slice(0, m.index) : t).split(/\s+/).join(' ').trim();
};
const replies = ($('Get the replies').first().json.items || [])
  .filter(e => !seen.has(e.id))
  .map(e => ({ id: e.id, lead: e.lead || e.from_address_email, subject: e.subject || '', text: text(e),
               received: e.timestamp_email, eaccount: e.eaccount || String(e.to_address_email_list || '').split(',')[0] }))
  .sort((a, b) => String(a.received).localeCompare(String(b.received)));
if (!replies.length) return [];
return [{ json: { replies } }];
"""

CHECK_JS = r"""
// Same rules as bdr.py check. A reply whose verdict breaks a rule gets a row with the problem and no draft,
// so it is never sent by mistake.
const CATS = { interested: [true, 1], question: [true, null], not_now: [true, null], referral: [true, -2],
               objection: [true, null], not_interested: [true, -1], unsubscribe: [false, -1],
               out_of_office: [false, 0], other: [false, null] };
const playbook = $('Sort settings').first().json.playbook;
const link = (playbook.match(/Booking link: (\S+)/) || [])[1];
const verdicts = Object.fromEntries(($json.output.replies || []).map(v => [v.id, v]));
const settings = $('Sort settings').first().json;
return $('New replies').first().json.replies.map(r => {
  const v = verdicts[r.id] || {};
  const cat = v.category, draft = String(v.draft || '').trim(), n = draft ? draft.split(/\s+/).length : 0;
  const problems = [];
  if (!CATS[cat]) problems.push('no category');
  else {
    if (CATS[cat][0] && !draft) problems.push(`a ${cat} reply needs a draft`);
    if (!CATS[cat][0] && draft) problems.push(`no draft for ${cat}`);
    if (draft && (n < 15 || n > 120)) problems.push(`draft is ${n} words`);
    if (!v.reason || String(v.reason).split(/\s+/).length > 25) problems.push('reason missing or over 25 words');
    for (const p of draft.match(/[$€£]\s?\d[\d,.]*|\d[\d,.]*\s?(?:USD|EUR|credits?)/g) || [])
      if (!playbook.replace(/ /g, '').includes(p.replace(/ /g, ''))) problems.push(`quotes ${p}, not in the playbook`);
    if (cat === 'interested' && link && !draft.includes(link)) problems.push('no booking link');
    if (cat === 'not_now' && !/^\d{4}-\d{2}-\d{2}$/.test(String(v.follow_up_on || ''))) problems.push('no follow-up date');
    if (cat === 'referral' && !v.referred_role) problems.push('no referred role');
    if (link && link.includes('your-team')) problems.push('the playbook still has the example booking link');
  }
  return { json: {
    'Received': r.received, 'Id': r.id, 'Lead': r.lead, 'They wrote': r.text.slice(0, 1000),
    'Category': cat || '', 'Reason': v.reason || '', 'Draft': problems.length ? '' : draft,
    'Follow up on': v.follow_up_on || '', 'Referred': v.referred_role || v.referred_name || '',
    'Check': problems.join('; ') || 'ok', 'Send': '', 'Sent': '',
    'Subject': /^re:/i.test(r.subject) ? r.subject : 'Re: ' + r.subject, 'Mailbox': r.eaccount,
    'Campaign': settings.instantly_campaign_id,
  } };
});
"""

TO_SEND_JS = r"""
// Rows to act on, never sent yet and passed the check: a "yes" in Send with a draft, and every unsubscribe
// (blocked without approval, so the address never gets another email).
const INTEREST = { interested: 1, referral: -2, not_interested: -1, unsubscribe: -1, out_of_office: 0 };
return $input.all().map(i => i.json)
  .filter(r => r.Id && !String(r.Sent || '').trim())
  .filter(r => r.Check === 'ok')
  .filter(r => r.Category === 'unsubscribe' ||
               (String(r.Send || '').trim().toLowerCase() === 'yes' && String(r.Draft || '').trim()))
  .map(r => ({ json: { ...r, action: r.Category === 'unsubscribe' ? 'block' : 'reply',
                       interest: INTEREST[r.Category] ?? null } }));
"""

JUDGE_SYSTEM = """You are a BDR who answers the replies to an outbound email campaign. For each reply in the JSON, sort it into one category and draft the answer, following the playbook below. Use only the facts in the playbook; never invent a price, a customer, a feature or a date.

Return {replies: [{id, category, reason, draft, follow_up_on, referred_role}]}:
- category: interested, question, not_now, referral, objection, not_interested, unsubscribe, out_of_office or other.
- reason: one line under 25 words, from the reply itself.
- draft: plain text, 15 to 120 words, "Hi <first name>," then the answer, signed with a first name only. Empty for unsubscribe, out_of_office and other.
  - interested: thanks and the booking link, nothing else.
  - question: answer from the playbook only, then offer a call; if the playbook has no answer, say a colleague will reply.
  - not_now: thank them and say when you will check back.
  - referral: thank them and ask for a short intro to the person they named.
  - objection: acknowledge it, one difference from the playbook, no pressure.
  - not_interested: one polite line, no pitch.
- follow_up_on: for not_now only, YYYY-MM-DD: the date they gave, or 90 days after the reply.
- referred_role: for referral only, the role or name they pointed to.
- Never guess anyone's gender: no he, she, him or her. Use the first name or "they".

Playbook:
{{ $('Sort settings').first().json.playbook }}"""

# 1. Sort
node("Every hour", "n8n-nodes-base.scheduleTrigger", 1.2, {"rule": {"interval": [
    {"field": "cronExpression", "expression": "0 * * * *"}]}}, [0, 0])
settings("Sort settings", [220, 0])
instantly("Get the replies", "GET", "=https://api.instantly.ai/api/v2/emails?campaign_id="
          "{{ $json.instantly_campaign_id }}&email_type=received&limit=100", None, [440, 0])
sheet("Replies so far", "read", "={{ $('Sort settings').first().json.replies_tab_url }}", [660, 0], executeOnce=True)
code("New replies", NEW_JS, [880, 0], executeOnce=True)
node("Sort and draft", "@n8n/n8n-nodes-langchain.agent", 2.2, {
    "promptType": "define", "hasOutputParser": True,
    "text": "={{ JSON.stringify($json.replies.map(r => ({ id: r.id, from: r.lead, subject: r.subject, "
            "received: r.received, reply: r.text }))) }}",
    "options": {"systemMessage": "=" + JUDGE_SYSTEM, "maxIterations": 3},
}, [1100, 0], retryOnFail=True, maxTries=3, waitBetweenTries=2000)
node("Claude", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.3, {
    "model": {"__rl": True, "mode": "list", "value": MODEL, "cachedResultName": MODEL},
    "options": {"maxTokensToSample": 6000},
}, [1060, 200], ANTHROPIC_CRED)
node("Verdicts", "@n8n/n8n-nodes-langchain.outputParserStructured", 1.3, {
    "schemaType": "manual",
    "inputSchema": json.dumps({"type": "object", "required": ["replies"], "properties": {"replies": {
        "type": "array", "items": {"type": "object", "required": ["id", "category", "reason"], "properties": {
            "id": {"type": "string"}, "category": {"type": "string"}, "reason": {"type": "string"},
            "draft": {"type": "string"}, "follow_up_on": {"type": "string"},
            "referred_role": {"type": "string"}}}}}}, indent=2),
}, [1220, 200])
code("Check the drafts", CHECK_JS, [1440, 0])
sheet("Add to Replies", "append", "={{ $('Sort settings').first().json.replies_tab_url }}", [1660, 0],
      columns={"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []})
nodes[-1]["parameters"]["options"] = {"useAppend": True}

# 2. Send
node("Every 15 minutes", "n8n-nodes-base.scheduleTrigger", 1.2, {"rule": {"interval": [
    {"field": "minutes", "minutesInterval": 15}]}}, [0, 420])
settings("Send settings", [220, 420])
sheet("Replies", "read", "={{ $('Send settings').first().json.replies_tab_url }}", [440, 420])
code("Approved or unsubscribe", TO_SEND_JS, [660, 420])
instantly("Reply or block", "POST",
          "={{ $json.action === 'block' ? 'https://api.instantly.ai/api/v2/block-lists-entries' "
          ": 'https://api.instantly.ai/api/v2/emails/reply' }}",
          # Instantly drops the line breaks of a text body, so the draft also goes as HTML paragraphs.
          "={{ JSON.stringify($json.action === 'block' ? { bl_value: $json.Lead } : { eaccount: $json.Mailbox, "
          "reply_to_uuid: $json.Id, subject: $json.Subject, body: { text: $json.Draft, html: String($json.Draft).trim()"
          ".split(/\\n\\s*\\n/).map(p => '<p>' + p.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')"
          ".replace(/\\n/g, '<br>') + '</p>').join('') } }) }}", [880, 420],
          onError="continueErrorOutput")
node("Has an interest status?", "n8n-nodes-base.if", 2.2, {"conditions": {
    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
    "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $('Approved or unsubscribe').item.json.interest }}",
                    "rightValue": "", "operator": {"type": "number", "operation": "exists", "singleValue": True}}],
    "combinator": "and"}, "options": {}}, [1100, 420])
instantly("Set interest status", "POST", "https://api.instantly.ai/api/v2/leads/update-interest-status",
          "={{ JSON.stringify({ lead_email: $('Approved or unsubscribe').item.json.Lead, "
          "interest_value: $('Approved or unsubscribe').item.json.interest, "
          "campaign_id: $('Approved or unsubscribe').item.json.Campaign }) }}", [1320, 340],
          onError="continueRegularOutput")
node("Done", "n8n-nodes-base.noOp", 1, {}, [1320, 520])
sheet("Mark as sent", "update", "={{ $('Send settings').first().json.replies_tab_url }}", [1540, 420],
      columns={"mappingMode": "defineBelow",
               "value": {"Id": "={{ $('Approved or unsubscribe').item.json.Id }}", "Sent": "={{ $now.toISO() }}"},
               "matchingColumns": ["Id"],
               "schema": [{"id": c, "displayName": c, "required": False, "defaultMatch": False, "display": True,
                           "type": "string", "canBeUsedToMatch": True} for c in ("Id", "Sent")]})

for a, b in [("Every hour", "Sort settings"), ("Sort settings", "Get the replies"), ("Get the replies", "Replies so far"),
             ("Replies so far", "New replies"), ("New replies", "Sort and draft"), ("Sort and draft", "Check the drafts"),
             ("Check the drafts", "Add to Replies"), ("Every 15 minutes", "Send settings"), ("Send settings", "Replies"),
             ("Replies", "Approved or unsubscribe"), ("Approved or unsubscribe", "Reply or block"),
             ("Reply or block", "Has an interest status?"), ("Set interest status", "Mark as sent"),
             ("Done", "Mark as sent")]:
    link(a, b)
link("Has an interest status?", "Set interest status", out=0)
link("Has an interest status?", "Done", out=1)
link("Claude", "Sort and draft", "ai_languageModel")
link("Verdicts", "Sort and draft", "ai_outputParser")

wf = {"name": "AI BDR reply agent (Instantly + Claude)", "nodes": nodes, "connections": connections,
      "settings": {"executionOrder": "v1"}, "pinData": {}, "active": False}
out = Path(__file__).with_name("ai-bdr-reply-agent.json")
out.write_text(json.dumps(wf, indent=2) + "\n")
print(out, len(nodes), "nodes")
