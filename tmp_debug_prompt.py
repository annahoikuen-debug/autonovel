from src.agents.specialists.consistency_auditor import ConsistencyAuditor, CONSISTENCY_SYSTEM_PROMPT, CONSISTENCY_USER_PROMPT
from src.agents.specialists.anchors import get_anchor_preset

ctx = {
    'draft_text': '昨日の戦いで死んだはずの仲間が朝ごはんを食べていた。今日はいい天気だ。',
    'world_bible_snapshot': {'characters': [{'name': '仲間', 'status': 'deceased', 'alive': False}]},
}

auditor = ConsistencyAuditor()
bible = ctx.get('world_bible_snapshot') or {}
bible_summary = auditor._summarize_bible(bible)
print('Bible summary:', bible_summary)

draft = ctx.get('draft_text', '')
prompt = CONSISTENCY_USER_PROMPT.format(
    bible_summary=bible_summary or '特になし',
    draft_text=draft,
)

anchor_preset = get_anchor_preset('consistency')
if anchor_preset:
    anchor_text = anchor_preset.format_for_prompt()
    prompt = f'{prompt}\n\n{anchor_text}'

instruction_suffix = '\n\n必ず以下のJSON形式のみを出力してください'
prompt += instruction_suffix

print('=== PROMPT ===')
print(prompt[:3000])
print('...')
print()
print('=== KEYWORDS IN PROMPT ===')
for kw in ['Consistency', '矛盾', '死亡キャラクター', '論理破綻', '再登場', '論理矛盾', '一貫性']:
    if kw in prompt:
        print(f'FOUND: {kw}')
    else:
        print(f'MISSING: {kw}')