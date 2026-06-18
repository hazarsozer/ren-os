from __future__ import annotations

import os
from pathlib import Path

from ..sandbox import eval_sandbox


def test_sandbox_redirects_and_restores():
    before = dict(os.environ)
    with eval_sandbox() as sb:
        assert Path(sb.wiki_root).is_dir()
        assert sb.env["SF_WIKI_ROOT"] == str(sb.wiki_root)
        assert sb.env["CLAUDE_PLUGIN_DATA"] == str(sb.plugin_data)
        tmp = sb.wiki_root
    assert not Path(tmp).exists()           # torn down
    assert dict(os.environ) == before        # process env untouched


def test_sandbox_env_is_a_copy_not_global_mutation():
    with eval_sandbox() as sb:
        assert "SF_WIKI_ROOT" not in os.environ or os.environ.get("SF_WIKI_ROOT") != sb.env["SF_WIKI_ROOT"]
