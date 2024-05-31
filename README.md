# cachecache: supercharge your Python functions with flexible, runtime-configurable caching! 🚀

[![PyPI version](https://badge.fury.io/py/cachecache.svg)](https://badge.fury.io/py/cachecache)
[![License: MIT](https://img.shields.io/badge/license-GPLv3-blue)](https://opensource.org/license/gpl-3-0)

A Python package that provides a simple and customizable way to cache function results and alter caching behavior at runtime.

## Features

- Effortless 1-liner caching with a decorator: @cache
- Caching behavior can be customized on the fly for specific function calls, by passing the following arguments to the cached functions:
    - 🔄 "again=True": recompute and overwrite cached results on-demand
    - ⏸️ "cache_results=False": disable caching for specific function calls, for instance if the computed result would take too much room on disk.
    - 📁 "cache_path='different/caching/path' ": use custom cache locations for specific function calls
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

Cache using a custom directory and maximum cache size of 10GB:
```python
@Cacher("my/custom/caching/path", 10e9) # size in bytes
def my_cached_function(...):
    ...
```

Use a single cacher for multiple functions:
```python
cacher = Cacher("my/custom/caching/path", 10e9)

@cacher
def foo1(x):
    return x ** 2

@cacher
def foo2(x):
    return x / 10
```

Recompute results and overwrite cache:
```python
result = my_cached_function(arg, again=True)
```
This proves very useful if the results depend on data that can change on disk (this information is not present in the arguments of the function, so the cacher does not know about it!)

Adjust caching directory at runtime
```python
result = my_cached_function(arg, cache_path="somewhere/else")
```
This proves very useful if you need to distribute the cached results of a function across several disks! For instance, it is possible to create a wrapper around Cacher that exploits this capability to cache data in a place specified by any argument, such as `datapath`:

```python
global_cacher = Cacher('~/.global_cache')

def distributed_cacher(func):
    """
    Decorator to cache functions using their 'datapath' argument
    at 'datapath/.local_cache'.
    """
    
    @functools.wraps(func)
    def locally_cached_func(*args, **kwargs):

        # replace the cache_path argument
        # with 'datapath/.local_cache'
        if 'datapath' in kwargs:
            if isinstance(kwargs['datapath'], Union[str, Path]):
                cache_path = Path(kwargs['datapath']) / '.local_cache'
                kwargs['cache_path'] = cache_path

        # the default cache is at '~/.global_cache' and only instantiated once as global_cacher,
        # but if a function has the datapath parameter,
        # the cache will instead be redirected to 'datapath/.local_cache'
        cached_func = global_cacher(func) # same as decorating func with @global_npyx_cacher
        results = cached_func(*args, **kwargs)

        return results

    return locally_cached_func
```

## License

This project is licensed under the terms of the [GNU GENERAL PUBLIC LICENSE](https://opensource.org/license/gpl-3-0). You may copy, distribute and modify the software as long as you track changes/dates in source files. Any modifications to or software including (via compiler) GPL-licensed code must also be made available under the GPL along with build & install instructions.

## Support

If you have any questions, issues, or feature requests, please [open an issue](https://github.com/m-beau/cachecache/issues) so that everybody can benefit from your experience! This package is actively maintained.