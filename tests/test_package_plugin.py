from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SCRIPT = PLUGIN_ROOT / "scripts" / "package_plugin.py"


def load_package_module():
    spec = importlib.util.spec_from_file_location("util_package_plugin", PACKAGE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_package_plugin_excludes_dist_artifacts(monkeypatch, tmp_path):
    module = load_package_module()
    output_path = tmp_path / "astrbot_plugin_util-test.zip"

    monkeypatch.setattr(
        module,
        "list_tracked_files",
        lambda: [
            Path("metadata.yaml"),
            Path("requirements.txt"),
            Path("dist/old.zip"),
        ],
    )

    module.package_plugin(output_path)

    with zipfile.ZipFile(output_path) as archive:
        names = set(archive.namelist())

    assert "astrbot_plugin_util/metadata.yaml" in names
    assert "astrbot_plugin_util/requirements.txt" in names
    assert "astrbot_plugin_util/dist/old.zip" not in names
