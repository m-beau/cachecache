[![PyPI version](https://badge.fury.io/py/cachecache.svg)](https://badge.fury.io/py/cachecache)
[![License: GPLv3](https://img.shields.io/badge/license-GPLv3-blue)](https://opensource.org/license/gpl-3-0)
[![Downloads](https://static.pepy.tech/badge/cachecache)](https://pepy.tech/project/cachecache)

# cachecache: Python function decorator for runtime-configurable caching.</h1> <img src="https://raw.githubusercontent.com/m-beau/cachecache/master/images/cachecache.png" width="150" title="Neuropyxels" alt="Neuropixels" align="right" vspace = "50">

A Python package that provides a simple way to cache function results while allowing to dynamically configure caching behavior at each function call.

By "caching behavior" reconfigurable at each function call, we mean:
1) Whether to recompute results and overwrite the cache, which is useful for functions whose results rely on data loaded internally (therefore hidden from the function arguments, thus from the cache hash) and that can change on disk;
2) Whether to cache the results, which is useful for functions who may need caching in context A (e.g. frontend recurrent use) but not context B (e.g. backend unique use);
3) Where to save the cached results, which is useful for functions that return voluminous data, as this allows to distribute their cache across several locations given different arguments.

## Features

- 1-liner caching with a decorator: @cache
- Caching behavior can be customized on the fly for specific function calls, by passing the following arguments to the cached functions:
    - 🔄 `again=True`: recompute and overwrite cached results on-demand
    - ⏸️ `cache_results=False`: disable caching for specific function calls, for instance if the computed result would take too much room on disk.
    - 📁 `cache_path='different/caching/path'`: use custom cache locations for specific function calls
- Built on joblib's [Memory](https://joblib.readthedocs.io/en/latest/generated/joblib.Memory.html) class.

## Installation

You can install `cachecache` using pip:

```bash
pip install cachecache
```

## Usage

Here's a basic example of how to use `cachecache`:

```python
from cachecache import cache, Cacher
```

Cache using the default "~/.cachecache" directory and default maximum cache size:
```python
@cache # behind the scenes, "cache" is simply defined as "cache = Cacher()"
def my_cached_function(*args, again=False, cache_results=True, cache_path=None):
    # complex operations involving args...
    results = ...
    return results

result = my_cached_function(arg)  # potentially slow
result = my_cached_function(arg)  # always fast (results loaded from cache)
```

Cache using a custom directory and maximum cache size:
```python
cacher = Cacher("my/custom/caching/path", 10e9) # size in bytes - 10GB
@cacher
def my_cached_function(...):
    ...
```

Recompute results and overwrite cache:
```python
result = my_cached_function(arg, again=True)
```
This proves useful if the results depend on data that can change on disk (this information is not present in the arguments of the function, so the cacher does not know about it!).

Adjust caching directory at runtime
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

If you have any questions, issues, or feature requests, please [open an issue](https://github.com/m-beau/cachecache/issues) so that everybody can benefit from your experience! This package is actively maintained.
