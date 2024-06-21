import inspect
from typing import Union, Any
import os
from collections.abc import Iterable


def is_valid_file_path(path: str):
    try:
        is_file = os.path.isfile(path)
        return is_file
    except:
        return False


def get_function_parameters_as_dict(
        func: callable,
        exclude_param_names: Union[list, str] = None,
        exclude_param_types: Union[list, Any] = None,
        func_args: Union[list, tuple] = None,
        func_kwargs: dict = None
):
    """
    Get the parameters of a function as a dict
    :param func: the function to get the parameters from
    :param exclude_param_names: the names of the parameters to exclude
    :param exclude_param_types: the types of the parameters to exclude
    :param func_args: the arguments of the function at runtime
    :param func_kwargs: the keyword arguments of the function at runtime
    :return: a dict with the parameters as key and the value as value
    """
    if isinstance(exclude_param_names, str):
        exclude_param_names = [exclude_param_names]
    if not isinstance(exclude_param_types, list):
        exclude_param_types = [exclude_param_types]
    exclude_param_names = [p.lower() for p in exclude_param_names]

    named_func_params = [
        p for p in inspect.signature(func).parameters.values()
        if p.annotation not in exclude_param_types
        and p.name.lower() not in exclude_param_names
    ]
    # fill params in order of kwargs
    params = {}
    for i, arg in enumerate(func_args):
        params[named_func_params[i].name] = arg
    # add the kwargs
    params.update(func_kwargs)
    return params


def flatten_list(xs):
    for x in xs:
        if isinstance(x, Iterable) and not isinstance(x, (str, bytes)):
            yield from flatten_list(x)
        else:
            yield x