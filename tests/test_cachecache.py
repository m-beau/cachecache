import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

from cachecache.cachecache import make_arg_kwargs_dic, Cacher, cache, distributed_cacher


# ---------- make_arg_kwargs_dic ----------

class TestMakeArgKwargsDic:

    def test_args_only(self):
        def func(a, b):
            pass
        result = make_arg_kwargs_dic(func, (1, 2), {})
        assert result["a"] == 1
        assert result["b"] == 2
        assert result["a_arg_index"] == 0
        assert result["b_arg_index"] == 1

    def test_kwargs_only(self):
        def func(a, b):
            pass
        result = make_arg_kwargs_dic(func, (), {"a": 1, "b": 2})
        assert result["a"] == 1
        assert result["b"] == 2
        assert "a_arg_index" not in result

    def test_mixed_args_kwargs(self):
        def func(a, b, c):
            pass
        result = make_arg_kwargs_dic(func, (10,), {"b": 20, "c": 30})
        assert result["a"] == 10
        assert result["b"] == 20
        assert result["c"] == 30

    def test_defaults_filled(self):
        def func(a, b=42):
            pass
        result = make_arg_kwargs_dic(func, (1,), {})
        assert result["a"] == 1
        assert result["b"] == 42

    def test_unexpected_kwarg_raises(self):
        def func(a):
            pass
        with pytest.raises(AssertionError, match="unexpected keyword argument"):
            make_arg_kwargs_dic(func, (), {"a": 1, "bad": 2})

    def test_var_keyword_allows_extra(self):
        def func(a, **kwargs):
            pass
        result = make_arg_kwargs_dic(func, (), {"a": 1, "extra": 2})
        assert result["a"] == 1
        assert result["extra"] == 2


# ---------- Cacher ----------

class TestCacher:

    def test_init_default(self, tmp_path):
        cacher = Cacher(tmp_path)
        assert cacher.global_cache_memory is not None

    def test_init_with_allocation(self, tmp_path):
        cacher = Cacher(tmp_path, caching_memory_allocation=int(1e9))
        assert cacher.global_cache_memory.caching_memory_allocation == int(1e9)

    def test_repr(self, tmp_path):
        cacher = Cacher(tmp_path, caching_memory_allocation=int(1e9))
        r = repr(cacher)
        assert "Cacher" in r
        assert "1.0GB" in r

    def test_decorator_basic(self, tmp_path):
        cacher = Cacher(tmp_path)

        @cacher
        def add(a, b):
            return a + b

        assert add(2, 3) == 5
        # Second call should load from cache
        assert add(2, 3) == 5

    def test_again_recomputes(self, tmp_path):
        cacher = Cacher(tmp_path)
        call_count = 0

        @cacher
        def counter(x):
            nonlocal call_count
            call_count += 1
            return x

        counter(1)
        assert call_count == 1
        counter(1)
        assert call_count == 1  # cached
        counter(1, again=True)
        assert call_count == 2  # recomputed

    def test_cache_results_false(self, tmp_path):
        cacher = Cacher(tmp_path)
        call_count = 0

        @cacher
        def counter(x):
            nonlocal call_count
            call_count += 1
            return x

        counter(1, cache_results=False)
        assert call_count == 1
        counter(1, cache_results=False)
        assert call_count == 2  # not cached

    def test_cache_path_override(self, tmp_path):
        cacher = Cacher(tmp_path / "global")
        alt_path = tmp_path / "alt"

        @cacher
        def add(a, b):
            return a + b

        result = add(1, 2, cache_path=str(alt_path))
        assert result == 3
        # Verify alt cache dir was created
        assert alt_path.exists()

    def test_explicit_cache_args_in_signature(self, tmp_path):
        cacher = Cacher(tmp_path)

        @cacher
        def func(x, again=False, cache_results=True, cache_path=None):
            return (x, again, cache_path)

        result = func(10, again=True)
        assert result[0] == 10
        assert result[1] is True

    def test_not_callable_raises(self, tmp_path):
        cacher = Cacher(tmp_path)
        with pytest.raises(AssertionError, match="not callable"):
            cacher._decorator("not a function")

    def test_main_module_override(self, tmp_path):
        cacher = Cacher(tmp_path)

        def func(x):
            return x
        func.__module__ = "__main__"
        decorated = cacher(func)
        # After decoration, the module should have been changed
        assert func.__module__ == "cachecache_persistent"

    def test_instanciate_nonexistent_parent_raises(self, tmp_path):
        with pytest.raises(ValueError, match="parent directory doesn't exist"):
            Cacher(tmp_path / "no_parent" / "no_child")

    def test_instanciate_not_writable_returns_none(self, tmp_path):
        with patch("cachecache.cachecache.is_writable", return_value=False):
            cacher = Cacher.__new__(Cacher)
            result = cacher.instanciate_joblib_cache(tmp_path, None)
            assert result is None

    def test_multiple_functions_same_cacher(self, tmp_path):
        cacher = Cacher(tmp_path)

        @cacher
        def square(x):
            return x ** 2

        @cacher
        def double(x):
            return x * 2

        assert square(3) == 9
        assert double(3) == 6

    def test_Cacher_direct_call_syntax(self, tmp_path):
        @Cacher(tmp_path)
        def add(a, b):
            return a + b

        assert add(3, 4) == 7


# ---------- cache (default global instance) ----------

class TestGlobalCache:

    def test_cache_is_cacher_instance(self):
        assert isinstance(cache, Cacher)

    def test_cache_decorator_works(self, tmp_path):
        # Use a custom cacher to avoid polluting global cache
        from cachecache import Cacher as C
        cacher = C(tmp_path)

        @cacher
        def multiply(a, b):
            return a * b

        assert multiply(3, 4) == 12


# ---------- distributed_cacher ----------

class TestDistributedCacher:

    def test_basic_distributed(self, tmp_path):
        global_cache = Cacher(tmp_path / "global")
        dc = distributed_cacher(
            datapath_arg_name="datapath",
            local_cache_path=".local_cache",
            global_cache=global_cache,
        )

        @dc
        def process(datapath, x):
            return x * 2

        dp = tmp_path / "data"
        dp.mkdir()
        result = process(str(dp), 5)
        assert result == 10
        assert (dp / ".local_cache").exists()

    def test_distributed_falls_back_to_global(self, tmp_path):
        global_cache = Cacher(tmp_path / "global")
        dc = distributed_cacher(
            datapath_arg_name="datapath",
            global_cache=global_cache,
        )

        @dc
        def process(x):
            return x + 1

        assert process(10) == 11

    def test_distributed_cache_path_prevails(self, tmp_path):
        global_cache = Cacher(tmp_path / "global")
        dc = distributed_cacher(
            datapath_arg_name="datapath",
            global_cache=global_cache,
        )

        @dc
        def process(datapath, x):
            return x * 3

        dp = tmp_path / "data"
        dp.mkdir()
        override = tmp_path / "override"
        result = process(str(dp), 7, cache_path=str(override))
        assert result == 21
        assert override.exists()

    def test_distributed_datapath_as_kwarg(self, tmp_path):
        global_cache = Cacher(tmp_path / "global")
        dc = distributed_cacher(
            datapath_arg_name="datapath",
            local_cache_path=".cache",
            global_cache=global_cache,
        )

        @dc
        def process(datapath, x):
            return x ** 2

        dp = tmp_path / "data2"
        dp.mkdir()
        result = process(datapath=str(dp), x=4)
        assert result == 16

    def test_distributed_none_datapath_uses_global(self, tmp_path):
        global_cache = Cacher(tmp_path / "global")
        dc = distributed_cacher(
            datapath_arg_name="datapath",
            global_cache=global_cache,
        )

        @dc
        def process(datapath, x):
            return x - 1

        # Pass a non-path datapath (int), should fall back to global
        result = process(42, 10)
        assert result == 9

    def test_distributed_default_global_cache(self, tmp_path):
        """When global_cache is None, distributed_cacher uses the default `cache` instance."""
        dc = distributed_cacher(
            datapath_arg_name="dp",
        )

        @dc
        def process(x):
            return x + 100

        assert process(1) == 101

    def test_distributed_cache_path_none_kwarg(self, tmp_path):
        """When cache_path=None is explicitly passed, datapath should fill it."""
        global_cache = Cacher(tmp_path / "global")
        dc = distributed_cacher(
            datapath_arg_name="datapath",
            local_cache_path=".my_cache",
            global_cache=global_cache,
        )

        @dc
        def process(datapath, x):
            return x

        dp = tmp_path / "data3"
        dp.mkdir()
        result = process(str(dp), 99, cache_path=None)
        assert result == 99
        assert (dp / ".my_cache").exists()
