from pathlib import Path
import functools
from typing import Union

from joblib import Memory
import psutil

from cachecache.CONFIG import default_cache_path


class Cacher:
    """
    Class embedding a decorator to cache any function at 'cache_path' ("~/.cachecache" by default).
    The decorated function can alter the caching behaviour at run time with the following arguments:
        - again: bool, whether to recompute and overwrite the cached results
             (if False, loads from cache if found in cache)
        - cache_results: bool, whether to cache the results
                         (if False, does not attempt to load form cache either)
        - cache_path: None|str, set alternative cache directory at run time

    *** Usage ***

        from cachecache import cache, Cacher

        # for caching at the default "~/.cachecache",
        # with a default maximum cache size of "all available space minus 5GB"
        @cache
        def my_cached_function(*args,
                               again = False,
                               cache_results = True,
                               cache_path = None):
            '''
            Arguments that will alter @Cacher() caching behaviour at run time:
            - again: bool, whether to recompute and overwrite the cached results
                     (if False, loads from cache if found in cache)
            - cache_results: bool, whether to cache the results
                             (if False, does not attempt to load form cache either)
            - cache_path: None|str, set alternative path to cache directory at run time
            '''
            
            # complex operations involving args...
            results = ...
    
            return results

        # for caching at "my/custom/caching/path",
        # with a maximum cache size of 10 GB
        # behind the scenes, "cache" is simply defined as "cache = Cacher()"
        @Cacher("my/custom/caching/path", 10e9)
        def my_cached_function(...

        # a custom cache can also be instantiated once for several functions
        cacher = Cacher("my/custom/caching/path", 10e9)

        @cacher
        def foo1(x):
            return x ** 2

        @cacher
        def foo2(x):
            return x / 10

        # Use your function
        result = my_cached_function(arg) # potentially slow

        # This time the results will reloaded from cache
        result = my_cached_function(arg) # always fast

        # Optionally, we can ask the function to recompute the results,
        # which proves very useful if the results depend on data that can change on disk
        # (this information is not available in the arguments of the function!)
        result = my_cached_function(arg, again=True)

        # Optionally, we can adjust the caching directory at run time
        result = my_cached_function(arg, cache_path="somewhere/else")

    Note: initializing a cacher has potentially non-neglectible overhead,
    so it is better practice to instanciate a single cacher to use across functions
    rather than resorting to using the 'cache_path' argument at run time,
    especially for functions that are intented to be called many times.
    
 
    *** Arguments ***
        - cache_path: directory to cache the results of functions decorated with cacher = Cacher().
        - caching_memory_allocation: int, max size of cache in bytes.

    *** Returns ***
        - cacher: the caching decorator.
    """

    def __init__(self,
                 cache_path: Union[str, Path] = default_cache_path,
                 caching_memory_allocation: Union[int, None] = None
                ):
        self.global_cache_memory = initiate_joblib_cache(cache_path,
                                                         caching_memory_allocation)
        self.input_caching_memory_allocation = caching_memory_allocation

    def __repr__(self):
        path = self.global_cache_memory.__repr__().split('=')[-1][:-1]
        memo = round(self.global_cache_memory.caching_memory_allocation*1e-9, 3)
        return ("Instance of Cacher from the cachecache package, \n"
                f"caching data at {path} unless specified with 'cache_path' at run time by the decorated function, \n"
                f"with a maximum allocation of {memo}GB.")

    def __call__(self, func):
        return self._decorator(func)

    def _decorator(self, func_to_cache):
        """
        Decorator to cache any function at cache_path,
        with a memory allocation of caching_memory_allocation.
        
        Importantly, the cache behaviour can be altered by
        the following optional function arguments at run time:
            - again: bool, whether to recompute and overwrite the cached results
                     (if False, loads from cache if found in cache)
            - cache_results: bool, whether to cache the computed results
                             (if False, does not attempt to load form cache either)
            - cache_path: None|str, set alternative path to cache directory at run time
        """
        assert callable(func_to_cache), f'{func_to_cache} is not callable!'
        
        @functools.wraps(func_to_cache)
        def cached_func(*args, **kwargs):
            
            # preformat kwargs
            arguments_to_ignore = [k for k in ["again",
                                               "cache_results",
                                               "cache_path"]
                                   if k in kwargs]
            cache_results = kwargs.pop('cache_results', True)
            again = kwargs.pop('again', False)
            cache_path = kwargs.pop('cache_path', None)
            
            # If cache_results is False,
            # return the function unaltered
            if not cache_results:
                return func_to_cache(*args, **kwargs)
    
            # Cache the function,
            # eventually at the passed directory cache_path
            if cache_path is None:
                cache_memory = self.global_cache_memory
            else:
                # no way to customize the allocated cache memory for cache initialized at function run time
                cache_memory = initiate_joblib_cache(cache_path,
                                                     caching_memory_allocation=None)
    
            func_to_cache_cached = cache_memory.cache(func_to_cache,
                                                      ignore=arguments_to_ignore)
    
            # Reload or recompute results
            mem = func_to_cache_cached.call_and_shelve(*args, **kwargs)
            
            # If again is True, clear the cache to enforce recomputing the results
            if again:
                mem.clear()
    
            # Reload results (or recompute them if again was True)
            mem = func_to_cache_cached.call_and_shelve(*args, **kwargs)
            results = mem.get()
    
            return results
    
        return cached_func


def initiate_joblib_cache(path: int,
                          caching_memory_allocation: Union[int, None] = None):
    """
    Initialize joblib cache Memory object at 'path',
    with a size limit of caching_memory_allocation bytes.
    - path: str, path to cachinf directory
    - caching_memory_allocation: int, allocated memory for cache in bytes
    """
    # Format and process path
    path = Path(path).expanduser()
    if not path.parent.exists():
        error = (f"WARNING you attempted to cache your results at {str(path)}, "
                  "but the parent directory doesn't exist! Change your target cache, "
                 f"or create {str(path.parent)}.")
        raise ValueError(error)
    path.mkdir(exist_ok=True)

    # Instanciate joblib memory object
    memory = Memory(path, verbose=0)

    # Limit cache size
    free_memory_bytes = psutil.disk_usage(path).free
    if caching_memory_allocation is None:
        caching_memory_allocation = int(free_memory_bytes - 1e9)
        
    if free_memory_bytes * 1e-9 < 5:
        print((f"WARNING less than 5GB free at {str(path)} - "
                "caching will quickly fill up the remaining space "
                "(allowed all available space minus 1GB "
               f"(i.e. {caching_memory_allocation*1e-9}GB))."))

    memory.caching_memory_allocation = caching_memory_allocation
    memory.reduce_size(bytes_limit=caching_memory_allocation)

    return memory