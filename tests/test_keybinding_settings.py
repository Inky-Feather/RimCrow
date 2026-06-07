from dataclasses import asdict

from backend.settings import UIConfig


def test_ui_config_keybindings_default_shape():
    config = UIConfig()

    assert config.keybindings == {
        "version": 1,
        "bindings": {},
        "disabledDefaults": {},
    }
    assert asdict(config)["keybindings"]["version"] == 1


def test_ui_config_keybindings_uses_independent_default_object():
    left = UIConfig()
    right = UIConfig()

    left.keybindings["bindings"]["mods.refresh"] = ["Ctrl+R"]

    assert right.keybindings["bindings"] == {}
