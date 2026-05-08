"""
Claude AI Coaching Enhancement
================================
Replaces generic hardcoded coaching text with personalised AI-generated
feedback based on the actual measured angles and the player's profile.

Requires the ANTHROPIC_API_KEY environment variable.
Falls back gracefully to existing hardcoded text if the key is absent or
the API call fails for any reason.
"""

import os
import json

# ── System prompt — cached on first API call ──────────────────────────────
_SYSTEM_PROMPT = """\
You are an expert cricket coach with 20+ years of experience coaching all age groups.
You will receive AI-detected biomechanical issues for a cricket player, complete with
exact measurements (angles in degrees, percentages of body width, etc.).

Generate concise, personalised, age-appropriate coaching feedback for each issue.

STRICT RULES:
- Reference the EXACT measurements given (e.g. "your knee is at 138° — 17° below ideal")
- Keep language simple and positive for the player's age group
- what_wrong  : 1 sentence — what the measurement means physically
- why_matters : 1 sentence — the cricket-specific consequence for this player
- how_to_fix  : 1 concrete technique cue (no vague "practise more")
- drill       : 1 named drill + brief description (10–20 words max)

Return ONLY a valid JSON array. No markdown, no extra text.
Format: [{"name": "...", "what_wrong": "...", "why_matters": "...", "how_to_fix": "...", "drill": "..."}]
"""


def enhance_with_claude(checkpoints, mode, handedness, age_group):
    """
    Use Claude (claude-haiku-4-5) to personalise coaching feedback.

    Parameters
    ----------
    checkpoints : list of dicts  (from analyze_batting / analyze_bowling)
    mode        : 'batting' | 'bowling'
    handedness  : 'right'   | 'left'
    age_group   : 'under10' | 'under15' | 'under18' | 'adult'

    Returns
    -------
    The same checkpoints list — fix/improve issues have enhanced text fields.
    All changes are in-place AND the list is returned for chaining.
    """
    api_key = os.getenv('ANTHROPIC_API_KEY', '').strip()
    if not api_key:
        return checkpoints          # no key → use existing hardcoded text

    issues = [cp for cp in checkpoints if cp['status'] in ('fix', 'improve')]
    if not issues:
        return checkpoints          # nothing to enhance

    age_labels = {
        'under10': 'under-10 (age 8–10)',
        'under15': 'under-15 (age 11–14)',
        'under18': 'under-18 (age 15–17)',
        'adult':   'adult (18+)',
    }
    age_label = age_labels.get(age_group, age_group)

    issues_text = '\n'.join(
        f"- {cp['name']}: {cp.get('canvas_label') or cp['message']}"
        for cp in issues
    )

    user_msg = (
        f"Player profile: {handedness}-handed {mode}r, {age_label}\n\n"
        f"Detected issues (with measurements):\n{issues_text}\n\n"
        f"Return personalised feedback JSON for each issue listed above."
    )

    try:
        import anthropic   # imported lazily so missing package doesn't break startup
        client = anthropic.Anthropic(api_key=api_key)

        response = client.messages.create(
            model='claude-haiku-4-5',
            max_tokens=1400,
            system=[
                {
                    'type': 'text',
                    'text': _SYSTEM_PROMPT,
                    'cache_control': {'type': 'ephemeral'},  # prompt caching
                }
            ],
            messages=[{'role': 'user', 'content': user_msg}],
        )

        raw = response.content[0].text.strip()

        # Strip markdown fences if model wrapped the JSON
        if raw.startswith('```'):
            parts = raw.split('```')
            raw   = parts[1].lstrip('json').strip() if len(parts) > 1 else raw

        ai_items = json.loads(raw)
        ai_map   = {item['name']: item for item in ai_items}

        for cp in checkpoints:
            if cp['name'] in ai_map:
                ai = ai_map[cp['name']]
                cp['what_wrong']  = ai.get('what_wrong',  cp.get('what_wrong',  ''))
                cp['why_matters'] = ai.get('why_matters', cp.get('why_matters', ''))
                cp['how_to_fix']  = ai.get('how_to_fix',  cp.get('how_to_fix',  ''))
                cp['drill']       = ai.get('drill',        cp.get('drill',       ''))
                cp['ai_enhanced'] = True   # flag so template can show a badge

        print(f'[Claude coaching] Enhanced {len(ai_map)} issue(s) for {age_label} {mode}r.')

    except Exception as exc:
        print(f'[Claude coaching] Skipped — {exc}')

    return checkpoints
