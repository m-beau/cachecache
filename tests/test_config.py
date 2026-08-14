from cachecache.CONFIG import default_cache_path


def test_default_cache_path():
    assert default_cache_path == "~/.cachecache"
