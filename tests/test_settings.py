import tomllib

from penguin_companion.settings import DEFAULTS, TEMPLATE, State, load_config, merge


def test_template_is_valid_and_matches_defaults():
    parsed = tomllib.loads(TEMPLATE)
    assert merge(DEFAULTS, parsed) == DEFAULTS


def test_first_run_writes_the_template(tmp_path):
    path = tmp_path / "config.toml"
    config, error = load_config(path)
    assert error is None and path.read_text() == TEMPLATE and config["size"] == 120


def test_user_values_merge_over_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('size = 90\n[heads_up]\nbattery_low = 30\n[ai.brains.mine]\ntype = "command"\ncommand = ["x"]\n')
    config, _ = load_config(path)
    assert config["size"] == 90 and config["heads_up"]["battery_low"] == 30
    assert config["heads_up"]["disk_full_percent"] == 90 and config["ai"]["brains"]["mine"]["command"] == ["x"]


def test_broken_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("size = = 3\n")
    config, error = load_config(path)
    assert config == DEFAULTS and "config.toml" in error


def test_state_round_trip(tmp_path):
    state = State.load(tmp_path / "s" / "state.json")
    assert state.get("name") is None
    state.set("name", "Sparky")
    state.save()
    assert State.load(tmp_path / "s" / "state.json").get("name") == "Sparky"
