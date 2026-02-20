import os
import yaml
import pytest
from annal.config import AnnalConfig, ProjectConfig


def test_load_config_creates_default_when_missing(tmp_config_path):
    config = AnnalConfig.load(tmp_config_path)
    assert config.data_dir is not None
    assert config.projects == {}


def test_load_config_reads_existing(tmp_config_path):
    raw = {
        "data_dir": "/tmp/annal_test",
        "projects": {
            "myproject": {
                "watch_paths": ["/home/user/myproject"],
                "watch_patterns": ["**/*.md"],
                "watch_exclude": ["node_modules/**"],
            }
        },
    }
    os.makedirs(os.path.dirname(tmp_config_path), exist_ok=True)
    with open(tmp_config_path, "w") as f:
        yaml.dump(raw, f)

    config = AnnalConfig.load(tmp_config_path)
    assert config.data_dir == "/tmp/annal_test"
    assert "myproject" in config.projects
    assert config.projects["myproject"].watch_paths == ["/home/user/myproject"]


def test_save_config(tmp_config_path):
    config = AnnalConfig(
        config_path=tmp_config_path,
        data_dir="/tmp/test_data",
        projects={
            "testproj": ProjectConfig(
                watch_paths=["/home/user/testproj"],
            )
        },
    )
    config.save()

    with open(tmp_config_path) as f:
        raw = yaml.safe_load(f)
    assert raw["data_dir"] == "/tmp/test_data"
    assert "testproj" in raw["projects"]


def test_add_project(tmp_config_path):
    config = AnnalConfig.load(tmp_config_path)
    config.add_project("newproj", watch_paths=["/home/user/newproj"])
    assert "newproj" in config.projects
    assert config.projects["newproj"].watch_patterns == [
        "**/*.md", "**/*.yaml", "**/*.toml", "**/*.json"
    ]


def test_get_project_raises_for_unknown(tmp_config_path):
    config = AnnalConfig.load(tmp_config_path)
    with pytest.raises(KeyError):
        config.get_project("nonexistent")


def test_load_config_with_port(tmp_config_path):
    raw = {
        "data_dir": "/tmp/annal_test",
        "port": 9300,
        "projects": {},
    }
    os.makedirs(os.path.dirname(tmp_config_path), exist_ok=True)
    with open(tmp_config_path, "w") as f:
        yaml.dump(raw, f)

    config = AnnalConfig.load(tmp_config_path)
    assert config.port == 9300


def test_load_config_default_port(tmp_config_path):
    config = AnnalConfig.load(tmp_config_path)
    assert config.port == 9200


def test_add_project_with_custom_patterns(tmp_config_path):
    config = AnnalConfig.load(tmp_config_path)
    config.add_project(
        "custom",
        watch_paths=["/home/user/custom"],
        watch_patterns=["**/*.py"],
        watch_exclude=["**/test/**"],
    )
    proj = config.projects["custom"]
    assert proj.watch_patterns == ["**/*.py"]
    assert proj.watch_exclude == ["**/test/**"]


def test_add_project_updates_existing_patterns(tmp_config_path):
    config = AnnalConfig.load(tmp_config_path)
    config.add_project("proj", watch_paths=["/tmp/proj"])
    # Defaults should be applied on creation
    from annal.config import DEFAULT_WATCH_EXCLUDE
    assert config.projects["proj"].watch_exclude == list(DEFAULT_WATCH_EXCLUDE)

    # Now update just the excludes
    config.add_project("proj", watch_exclude=["**/custom_vendor/**"])
    assert config.projects["proj"].watch_exclude == ["**/custom_vendor/**"]
    # watch_paths should be unchanged
    assert config.projects["proj"].watch_paths == ["/tmp/proj"]
