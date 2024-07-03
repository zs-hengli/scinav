from __future__ import unicode_literals

import calendar
import copy
import hashlib
import logging
import random
import time
from datetime import datetime

import pytz
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)
url_validator = URLValidator()


def create_hash(hash_len=16):
    """This function generate 40 character long hash"""
    h = hashlib.sha512()
    h.update(str(time.time()).encode('utf-8'))
    return h.hexdigest()[0:hash_len]


def str_hash(original_str, hash_type='sha256'):
    all_type = ['md5', 'sha1', 'sha224', 'sha256', 'sha384', 'sha512',
                'blake2b', 'blake2s',
                'sha3_224', 'sha3_256', 'sha3_384', 'sha3_512',
                'shake_128', 'shake_256']
    if hash_type in all_type:
        return hashlib.new(hash_type, original_str.encode('utf-8')).hexdigest()
    return hashlib.sha256(original_str.encode('utf-8')).hexdigest()


def string_is_url(url):
    try:
        url_validator(url)
    except ValidationError:
        return False
    else:
        return True


def safe_float(v, default=0):
    if v != v:
        return default
    return v


def sample_query(q, sample_size):
    n = q.count()
    if n == 0:
        raise ValueError('Can\'t sample from empty query')
    ids = q.values_list('id', flat=True)
    random_ids = random.sample(list(ids), sample_size)
    return q.filter(id__in=random_ids)


def request_permissions_add(request, key, model_instance):
    """ Store accessible objects via permissions to request. It's used for access log.
    """
    request.permissions = {} if not hasattr(request, 'permissions') else request.permissions
    # this func could be called multiple times in one request, and this means there are multiple objects on page/api
    # do not save different values, just rewrite value to None
    if key not in request.permissions:
        request.permissions[key] = copy.deepcopy(model_instance)
    else:
        if request.permissions[key] is not None and request.permissions[key].id != model_instance.id:
            request.permissions[key] = None


def get_client_ip(request):
    """ Get IP address from django request

    :param request: django request
    :return: str with ip
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_attr_or_item(obj, key):
    if hasattr(obj, key):
        return getattr(obj, key)
    elif isinstance(obj, dict) and key in obj:
        return obj[key]
    else:
        raise KeyError(f"Can't get attribute or dict key '{key}' from {obj}")


def datetime_to_timestamp(dt):
    if dt.tzinfo:
        dt = dt.astimezone(pytz.UTC)
    return calendar.timegm(dt.timetuple())


def timestamp_now():
    return datetime_to_timestamp(datetime.utcnow())


def start_browser(ls_url, no_browser):
    import threading
    import webbrowser
    if no_browser:
        return

    browser_url = ls_url
    threading.Timer(2.5, lambda: webbrowser.open(browser_url)).start()
    logger.info(f'Start browser at URL:{browser_url}')


def load_func(func_string):
    """
    If the given setting is a string import notation,
    then perform the necessary import or imports.
    """
    if func_string is None:
        return None
    elif isinstance(func_string, str):
        return import_from_string(func_string)
    return func_string


def import_from_string(func_string):
    """
    Attempt to import a class from a string representation.
    """
    try:
        return import_string(func_string)
    except ImportError:
        msg = f"Could not import {func_string} from settings"
        raise ImportError(msg)


def batch(iterable, n=1):
    ln = len(iterable)
    for ndx in range(0, ln, n):
        yield iterable[ndx: min(ndx + n, ln)]


def round_floats(o):
    if isinstance(o, float):
        return round(o, 2)
    if isinstance(o, dict):
        return {k: round_floats(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [round_floats(x) for x in o]
    return o


def cmp_ignore_order(src=None, dst=None, sort_fun=None):
    """
    比较两个字典或者list是否相等。
    和原始比较方法的不同之处在于，对list类型先做排序，再进行比较。
    params:src dst 需要比较的两组数据
    params:sort_fun list类型做排序时，自定义的排序方法
    """
    if isinstance(src, dict) & isinstance(dst, dict):
        for key in dst:
            if key not in src:
                return False
        for key in src:
            if key in dst:
                if not cmp_ignore_order(src[key], dst[key], sort_fun):
                    return False
            else:
                return False
        return True
    elif isinstance(src, list) & isinstance(dst, list):
        if len(src) != len(dst):
            return False
        else:
            if sort_fun is not None:
                src.sort(key=sort_fun)
                dst.sort(key=sort_fun)
            for i in range(0, len(src)):
                if not cmp_ignore_order(src[i], dst[i], sort_fun):
                    return False
            return True
    else:
        return src == dst


def send_email(subject, content, to_emails, from_email=None):
    from django.core.mail import send_mail
    res = send_mail(subject, content, from_email, to_emails)
    if res:
        logger.info(f'Send email to {to_emails} success')
    else:
        logger.error(f'Send email to {to_emails} failed')
    return res


if __name__ == '__main__':
    from operator import itemgetter
    l1 = [{"read": False, "write": "100"}, {"write": "100", "read": False, 'id': 12}]
    l2 = [{"write": "100", "read": False}, {"read": False, "write": "100", 'id': 12}]
    print(l1, l2)
    print(cmp_ignore_order(l1, l2, sort_fun=itemgetter('write', 'read')))