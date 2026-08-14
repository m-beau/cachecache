[![PyPI version](https://badge.fury.io/py/cachecache.svg)](https://badge.fury.io/py/cachecache)
[![Tests](https://github.com/m-beau/cachecache/actions/workflows/tests.yml/badge.svg)](https://github.com/m-beau/cachecache/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/m-beau/cachecache/branch/master/graph/badge.svg)](https://codecov.io/gh/m-beau/cachecache)
[![License: GPLv3](https://img.shields.io/badge/license-GPLv3-blue)](https://opensource.org/license/gpl-3-0)
[![Downloads](https://static.pepy.tech/badge/cachecache)](https://pepy.tech/project/cachecache)

# cachecache <img src="https://raw.githubusercontent.com/m-beau/cachecache/master/images/cachecache.png" width="150" title="cachecache" alt="cachecache" align="right" vspace = "50">

A simple decorator to cache the results of your Python functions on disk, built on [joblib.Memory](https://joblib.readthedocs.io/en/latest/generated/joblib.Memory.html).

```python
from cachecache import cache

@cache
def my_function(arg1, arg2, arg3, ...):
    ...  # expensive computation

result = my_function("some/path", [1,2,3], 4)  # potentially slow the first time
result = my_function("some/path", [1,2,3], 4)  # same inputs -> instant from now on
result = my_function("some/path", [1,2,3], 4, again=True)  # recompute and overwrite cache, useful if data at some/path changed
result = my_function("some/path", [1,2,3], 4, cache_path="path/to/dir/with/space") # cache to a different location
```

## Why cachecache over raw joblib?

We built cachecache to address joblib's `Memory` lack of user-friendliness, especially in interactive workflows:

- **It works across interactive sessions (e.g. Jupyter notebooks reloads).** joblib caching tends to break on functions defined inside notebooks, because the cache directory gets redefined every time you restart the kernel. With cachecache, your cache persists across sessions.
- **Caching behavior is configurable at function call time.** Every `@cache`-decorated function implicitly accepts extra arguments to alter how caching works, without any changes to the function signature:
    - `again=True` — recompute and overwrite a stale cache (useful when underlying data changed on disk, which the cache hash can't detect yet is very frequent in interactive data exploration)
    - `cache_results=False` — skip caching for a specific call (useful when the result would be too large to store)
    - `cache_path="other/path"` — cache to a different location (useful to distribute cache across disks)
- **Distributed caching.** Cache a function's results next to the data it operates on (e.g. at `datapath/.local_cache`), so the cache lives where the data lives, rather than in a single global cache (likely to overfill). Joblib does not support this use case, which is very common in data analysis workflows.

## Installation

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv pip install cachecache
```

Or from a local git clone:

```bash
git clone https://github.com/m-beau/cachecache.git
cd cachecache
uv pip install .
```

Using pip:

```bash
pip install cachecache
```

## Usage

```python
from cachecache import cache, Cacher
```

By default, results are cached in `~/.cachecache`:
```python
@cache # behind the scenes, "cache" is simply defined as "cache = Cacher()", which defaults to "~/.cachecache"
def my_cached_function(x, y):
    # complex operations...
    results = ...
    return results

result = my_cached_function(arg)  # potentially slow
result = my_cached_function(arg)  # always fast (results loaded from cache)
```

The caching control arguments `again`, `cache_results`, and `cache_path` are **automatically injected** to any decorated function — no need to declare them in the function signature:
```python
result = my_cached_function(arg, again=True)               # recompute and overwrite cache
result = my_cached_function(arg, cache_results=False)       # skip caching entirely
result = my_cached_function(arg, cache_path="other/path")   # use a different cache directory
```

If you prefer, you can still declare them explicitly when you define the function (e.g. if you want to implement custom behavior depending on these arguments):
```python
@cache
def my_cached_function(x, y, again=False, cache_results=True, cache_path=None):
    if again:
        print("Recomputing!")
    print(f"Caching path: {cache_path}")
    ...
```

Cache using a custom directory and maximum cache size:
```python
cacher = Cacher("my/custom/caching/path", 10e9) # size in bytes - 10GB
@cacher
def my_cached_function(...):
    ...
```
When the cache exceeds its size limit, the least recently accessed items are evicted first. By default (when no limit is specified), cachecache allows caching up to all available disk space minus 1 GB, and will print a warning when less than 5 GB remain at the cache location.

Recompute results and overwrite cache:
```python
result = my_cached_function(arg, again=True)
```
This proves useful if the results depend on data that can change on disk (this information is not present in the arguments of the function, so the cacher does not know about it!).

Adjust caching directory at runtime:
```python
result = my_cached_function(arg, cache_path="somewhere/else")
```
This proves useful if you need to distribute the cached results of a function across several disks.

cachecache also provides a way to create a `distributed_cacher` that will cache a function's results at a location specified by a custom argument (such as 'datapath'):
```python
from cachecache import Cacher, distributed_cacher

global_cacher = Cacher('~/.global_cache')

# Arguments of distributed_cacher:
# - datapath_arg_name (str, optional): The name of the argument in the decorated function
#     that specifies the datapath for the local cache. Defaults to 'datapath'.
# - local_cache_path (str, optional): The relative path to the local cache directory
#     within the datapath. Defaults to '.local_cache' (and results cached at f'{datapath}/.local_cache').
# - global_cache (cachecache.Cacher instance, optional): The global cacher to use by default
#     for cached functions without 'datapath_arg_name' (or when 'datapath_arg_name' is None).
#     Defaults to a cache at '~/.cachecache' (default instance of Cacher()).
dist_cacher = distributed_cacher(datapath_arg_name='datapath',
                                local_cache_path='.local_cache',
                                global_cache=global_cacher)

# You can then decorate a function as follow:
@dist_cacher
def my_distributed_cached_function(datapath, ...):
    """
    A function whose results will be cached at 'datapath/.local_cache'
    unless specified otherwise with the cache_path argument.

    Note: works with args and kwargs
    """
    ...
```
Behind the scenes, this works by swapping in the value of the specified argument (datapath_arg_name) instead of the 'cache_path' argument from Cacher (if 'cache_path' is also specified, it takes precedence over 'datapath').

Of course, you can use a single cacher for multiple functions:
```python
@cacher
def foo1(x):
    return x ** 2

@cacher
def foo2(x):
    return x / 10
```

And both of these syntaxes are possible:
```python
cacher = Cacher("my/custom/caching/path")
@cacher
def my_cached_function(...):
    ...

@Cacher("my/custom/caching/path")
def my_cached_function(...):
    ...
```

## License

This project is licensed under the terms of the [GNU General Public License v3.0](https://opensource.org/license/gpl-3-0). You may copy, distribute and modify the software as long as you track changes/dates in source files. Any modifications to or software including (via compiler) GPL-licensed code must also be made available under the GPL along with build & install instructions.

## Support

If you have any questions, issues, or feature requests, please [open an issue](https://github.com/m-beau/cachecache/issues) so that everybody can benefit from your experience! This package is actively maintained by Maxime Beau.
