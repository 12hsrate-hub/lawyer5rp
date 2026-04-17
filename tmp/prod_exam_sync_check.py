import sys
from pathlib import Path
repo_root = Path('/srv/lawyer5rp-deploy/repo').resolve()
for candidate in (repo_root, repo_root / 'web'):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)
from ogp_web.env import load_web_env
load_web_env()
from ogp_web.services.exam_sheet_service import fetch_exam_sheet_rows
from ogp_web.storage.exam_answers_store import get_default_exam_answers_store
rows = fetch_exam_sheet_rows(force_refresh=True)
store = get_default_exam_answers_store()
stats = store.import_rows(rows)
print({'rows': len(rows), **stats})