import json
import zipfile

import pytest

from scripts.prepare_delivery import prepare, source_files


def test_materials_are_pending_and_source_archive_excludes_runtime(tmp_path):
    output=prepare(tmp_path/'kit')
    photos=list((output/'photo-records').glob('*.json'))
    assert len(photos)==10
    for path in photos:
        record=json.loads(path.read_text(encoding='utf-8'))
        assert record['status']=='pending' and record['inventory_truth']==[]
        assert record['permission_to_upload'] is False
        assert record['evaluation']['identity_errors'] is None
    assert len(list((output/'cooking-records').glob('*.json')))==5
    assert len(list((output/'user-records').glob('*.json')))==5
    assert '未审核' in (output/'recipe-review.html').read_text(encoding='utf-8')
    with zipfile.ZipFile(output/'source-only.zip') as archive:
        paths=archive.namelist()
        assert 'Dockerfile' in paths and '.env.example' in paths
        assert 'frontend/package-lock.json' in paths and 'kitchen/data/recipes.json' in paths
        assert 'frontend/public/sw.js' in paths
        assert all(not p.startswith(('data/','artifacts/','.venv/','.tools/','evaluation/photos/')) for p in paths)
        assert '.env' not in paths and not any(p.endswith(('.db','.log','.docx')) for p in paths)
    with pytest.raises(FileExistsError): prepare(output)


def test_source_allowlist_never_collects_local_settings_or_installed_modules(tmp_path):
    (tmp_path/'frontend').mkdir()
    for relative in ['.env','frontend/.env','frontend/node_modules/secret.js','kitchen/__pycache__/cache.py','data/kitchen.db','evaluation/photos/private.json']:
        path=tmp_path/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('private')
    assert source_files(tmp_path)==[]
