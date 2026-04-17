import json
import sys
from pathlib import Path

repo_root = Path('/srv/lawyer5rp-deploy/repo').resolve()
for candidate in (repo_root, repo_root / 'web'):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

from ogp_web.schemas import SuggestPayload
from ogp_web.services.ai_service import suggest_text_details

cases_path = Path('/tmp/suggest_cases_ogp_5.json')
cases = json.loads(cases_path.read_text(encoding='utf-8'))
results = []

for index, case in enumerate(cases, start=1):
    payload = SuggestPayload(
        victim_name=str(case.get('victim_name', '') or ''),
        org=str(case.get('org', '') or ''),
        subject=str(case.get('subject', '') or ''),
        event_dt=str(case.get('event_dt', '') or ''),
        raw_desc=str(case.get('raw_desc', '') or ''),
        complaint_basis=str(case.get('complaint_basis', '') or ''),
        main_focus=str(case.get('main_focus', '') or ''),
    )
    result = suggest_text_details(payload, server_code='blackberry')
    results.append({
        'index': index,
        'case_id': str(case.get('case_id', '') or f'case_{index}'),
        'title': str(case.get('title', '') or ''),
        'text': result.text,
        'warnings': list(result.warnings),
        'guard_status': result.guard_status,
        'policy_mode': str(getattr(result, 'policy_mode', '') or ''),
        'policy_reason': str(getattr(result, 'policy_reason', '') or ''),
        'valid_triggers_count': int(getattr(result, 'valid_triggers_count', 0) or 0),
        'retrieval_context_mode': str(getattr(result, 'retrieval_context_mode', '') or ''),
        'retrieval_confidence': str(getattr(result, 'retrieval_confidence', '') or ''),
        'input_warning_codes': list(getattr(result, 'input_warning_codes', ()) or ()),
        'protected_terms': list(getattr(result, 'protected_terms', ()) or ()),
        'safe_fallback_used': bool(getattr(result, 'safe_fallback_used', False)),
        'remediation_retries': int(getattr(result, 'remediation_retries', 0) or 0),
    })

print(json.dumps(results, ensure_ascii=False))
