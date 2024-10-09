from pathlib import Path
import functools
from typing import Union, Optional

from joblib import Memory
import psutil
import inspect

from cachecache.CONFIG import default_cache_path
from cachecache.utils import is_writable


def make_arg_kwargs_dic(func, args, kwargs):
    """
    Make a dictionnary storing boths args and kwargs of func.

    Adds args as a pair of key/values to the kwargs dictionnary:
    - one pair where key = arg_name, and value = arg,
    - one pair where key = arg_name + "_arg_index", and value = arg_index in args

    Arguments:
        - func: function
        - args: list of arguments from func
        - kwargs: dict of keyword arguments from func

    Returns:
        - args_kwargs: dictionnary holding boths args and kwargs.
    """

    # Get function signature
    sig = inspect.signature(func)

    # Identify all positional and keyword arguments
    arg_kwarg_names = [param.name for param in sig.parameters.values()]
    wrong_kwargs = [name for name in kwargs.keys() if name not in arg_kwarg_names]
    assert (
        len(wrong_kwargs) == 0
    ), f"{func.__name__}() got >=1 unexpected keyword argument(s): {wrong_kwargs}"

    # Add arguments PASSED as positional arguments, in args
    # (they can be defined either as positional or keyword arguments!)
    args_kwargs = {}
    for i, value in enumerate(args):
        name = arg_kwarg_names[i]
        args_kwargs[name] = value
        args_kwargs[name + "_arg_index"] = i

    # Add arguments PASSED as keyword arguments, in kwargs
    # (they can be defined either as positional or keyword arguments!)
    args_kwargs = {**args_kwargs, **kwargs}

    # Add keyword arguments NOT PASSED, with default values
    for name, param in sig.parameters.items():
        if (name not in args_kwargs) and \
           (param.default is not inspect.Parameter.empty):
            args_kwargs[name] = param.default

    return args_kwargs


class Cacher:
    """
    Class embedding a decorator to cache any function at 'cache_path' ("~/.cachecache" by default).
    
    The decorated function can alter the caching behaviour at run time with the following arguments:
        - again: bool, whether to recompute and overwrite the cached results
             (if False, loads from cache if found in cache)
        - cache_results: bool, whether to cache the results
                         (if False, does not attempt to load form cache either)
        - cache_path: None|str, set alternative cache directory at run time

    *** Arguments ***
        - cache_path: directory to cache the results of functions decorated with cacher = Cacher().
        - caching_memory_allocation: int, max size of cache in bytes.

    *** Returns ***
        - cacher: the caching decorator.

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
    """

    def __init__(
        self,
        cache_path: Union[str, Path] = default_cache_path,
        caching_memory_allocation: Union[int, None] = None,
    ):
        self.global_cache_memory = self.instanciate_joblib_cache(
            cache_path, caching_memory_allocation
        )
        self.input_caching_memory_allocation = caching_memory_allocation

    def __repr__(self):
        path = self.global_cache_memory.__repr__().split("=")[-1][:-1]
        memo = round(self.global_cache_memory.caching_memory_allocation * 1e-9, 3)
        return (
            "Instance of Cacher from the cachecache package, \n"
            f"caching data at {path} unless specified with 'cache_path' at run time by the decorated function, \n"
            f"with a maximum allocation of {memo}GB."
        )

    def __call__(self, func):
        "Calling cacher returns the decorated (cached) function."
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
        assert callable(func_to_cache), f"{func_to_cache} is not callable!"

        # Guarantees persistent cache directory across ipython sessions
        # for functions defined inside ipython sessions (e.g. jupyter notebook)
        if '__main__' in func_to_cache.__module__:
            func_to_cache.__module__ = 'cachecache_persistent'

        @functools.wraps(func_to_cache)
        def cached_func(*args, **kwargs):

            # Pull arguments that alter caching behavior
            cache_results = kwargs.get("cache_results", True)
            again = kwargs.get("again", False)
            cache_path = kwargs.get("cache_path", None)

            # If cache_results is False, return the function unaltered
            if not cache_results:
                return func_to_cache(*args, **kwargs)

            # Define cache, global or custom
            if cache_path is None:
                cache_memory = self.global_cache_memory
            else:
                # no way to customize the allocated cache memory for cache initialized at function run time
                cache_memory = self.instanciate_joblib_cache(
                    cache_path, caching_memory_allocation=None
                )
            
            # If path not writable, cache_memory will be None
            # so return the function unaltered
            if cache_memory is None:
                return func_to_cache(*args, **kwargs)

            # Cache function, ignoring arguments that alter caching behavior
            # only if they exist in the function signature
            arg_kwargs = make_arg_kwargs_dic(func_to_cache, args, kwargs)
            arguments_to_ignore = [
                k for k in ["again", "cache_results", "cache_path"] if k in arg_kwargs
            ]
            func_to_cache_cached = cache_memory.cache(
                func_to_cache, ignore=arguments_to_ignore
            )

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

    def instanciate_joblib_cache(
        self,
        path: int,
        caching_memory_allocation: Union[int, None] = None
    ):
        """
        Initialize joblib cache Memory object at 'path',
        with a size limit of caching_memory_allocation bytes.
        - path: str, path to cachinf directory
        - caching_memory_allocation: int, allocated memory for cache in bytes

        If 'path' is not writable: returns None
        """
        # Format and process path
        path = Path(path).expanduser()
        if not path.parent.exists():
            error = (
                f"WARNING you attempted to cache your results at {str(path)}, "
                "but the parent directory doesn't exist! Change your target cache, "
                f"or create {str(path.parent)}."
            )
            raise ValueError(error)
        
        if not is_writable(path, required_space_mb = 10):
            print((f"\n\nPath '{path}' not writable - caching by cachecache will be skipped. "
                    "\nPossible causes: permission error; <10MB left on device.\n\n"))
            return None

        path.mkdir(exist_ok=True)

        # Instanciate joblib memory object
        memory = Memory(path, verbose=0)

        # Limit cache size
        free_memory_bytes = psutil.disk_usage(str(path)).free
        if caching_memory_allocation is None:
            caching_memory_allocation = int(free_memory_bytes - 1e9)

        if free_memory_bytes * 1e-9 < 5:
            print(
                (
                    f"WARNING less than 5GB free at {str(path)} - "
                    "caching will quickly fill up the remaining space "
                    "(allowed all available space minus 1GB "
                    f"(i.e. {caching_memory_allocation*1e-9}GB))."
                )
            )

        memory.caching_memory_allocation = caching_memory_allocation
        memory.reduce_size(bytes_limit=caching_memory_allocation)

        return memory


# cachecache default global cache
cache = Cacher(default_cache_path)


def distributed_cacher(
    datapath_arg_name: str = "datapath",
    local_cache_path: str = ".local_cache",
    global_cache: Optional[Cacher] = None,
):
    """
    Decorator to cache the results of a function using a distributed caching strategy.

    The decorator caches the results of the decorated function at two levels:
    1. Global cache: The default global cache is stored at '~/.global_cache'.
    2. Local cache: If the decorated function has an argument specified by `datapath_arg_name`,
       the cache is redirected to '{datapath_arg_value}/{local_cache_path}'
       (by default, 'datapath/.local_cache').

    The global cache is instantiated only once, in the script where this decorator is defined,
    and shared across all decorated functions.
    The local cache is specific to each unique value of the `datapath_arg_name` argument.

    Behind the scenes, this works by swapping in the value of the specified argument (datapath_arg_name)
    instead of the 'cache_path' argument from Cacher (if 'cache_path' is also specified, it takes precedence over 'datapath').

    Arguments:
        - datapath_arg_name (str, optional): The name of the argument in the decorated function
            that specifies the datapath for the local cache. Defaults to 'datapath'.
        - local_cache_path (str, optional): The relative path to the local cache directory
            within the datapath. Defaults to '.local_cache' (and results cached at f'{datapath}/.local_cache').
        - global_cache (cachecache.Cacher instance, optional): The global cacher to use by default
            for cached functions without 'datapath_arg_name' (or when 'datapath_arg_name' is None).
            Defaults to a cache at '~/.cachecache' (default instance of Cacher()).

    Returns:
        - function: The decorated function with distributed caching enabled.

    Example:
        @distributed_cacher(datapath_arg_name='data_dir', local_cache_path='.cache')
        def my_func(data_dir, other_args): # data_dir can be an arg or a kwarg
            ...

        my_func('/path/to/data', other_args)
        # Results will be cached at '/path/to/data/.cache'

        my_func('/another/path/to/data', other_args)
        # Results will be cached at '/another/path/to/data/.cache'

        my_func(other_args)
        # Results will be cached at '~/.global_cache'
    """
    if global_cache is None:
        global_cache = cache

    def decorator(func):
        "Simple nested wrapper allowing to pass arguments to @distributed_cacher."

        @functools.wraps(func)
        def locally_cached_func(*args, **kwargs):

            arg_kwargs = make_arg_kwargs_dic(func, args, kwargs)

            # replace the cache_path argument
            # with f'{datapath_arg_name}/{local_cache_path}'
            if datapath_arg_name in arg_kwargs:
                datapath = arg_kwargs[datapath_arg_name]
                # if passed datapath is a sensible path
                if isinstance(datapath, (str, Path)):
                    new_cache_path = Path(datapath) / local_cache_path
                    # if 'cache_path' also passed to function,
                    # cache_path still prevails.
                    if "cache_path" in kwargs:
                        if kwargs["cache_path"] is None:
                            kwargs["cache_path"] = new_cache_path
                    else:
                        kwargs["cache_path"] = new_cache_path

            cached_func = global_cache(func)  # same as decorating func with @cache
            results = cached_func(*args, **kwargs)

            return results

        return locally_cached_func

    return decorator
