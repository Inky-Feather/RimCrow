from pathlib import Path


def test_codemirror_manual_chunk_keeps_runtime_dependencies_together():
    config_text = Path("frontend/vite.config.js").read_text(encoding="utf-8")

    for package_name in ("style-mod", "w3c-keyname", "crelt", "@marijn/find-cluster-break"):
        assert f"/node_modules/{package_name}/" in config_text
