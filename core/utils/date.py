import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

SHA_TZ = timezone(
    timedelta(hours=8),
    name='Asia/Shanghai',
)

def utc_to_local(date, local_zone_hour=8, from_format='%Y-%m-%dT%H:%M:%SZ', to_format='%Y-%m-%d %H:%M:%S'):
    """
    utc 时区转其他时区
    :param date:  str类型或者 datetime类型 的时间
    :param local_zone_hour: 时区 8 表示+8区
    :param from_format: 如果date是str类型 表示它的时间格式
    :param to_format:  想要的时间格式
    :return: datetime 或者 str 类型
    """
    if isinstance(date, str):
        utc_date = datetime.strptime(date, from_format)
    else:
        utc_date = date

    tz_local = timezone(timedelta(hours=local_zone_hour))
    utc_date = utc_date.replace(tzinfo=timezone.utc)
    local_date = utc_date.astimezone(tz_local)
    logger.debug(f'utc_to_local, date:{date}, local_date:{local_date}')
    if to_format:
        return local_date.strftime(to_format)
    else:
        return local_date


def date_len(start, end, format='%Y-%m-%dT%H:%M:%SZ', unit='second'):
    """
    计算两个日期相差的时间
    :param start:
    :param end:
    :param format:
    :param unit:
    :return:
    """
    logger.debug(f"data_len start:{start}, end:{end}")
    if not start:
        return None
    if isinstance(start, str):
        start = datetime.strptime(start, format)
    if not end:
        end = datetime.utcnow().replace(tzinfo=timezone.utc)
    if isinstance(end, str):
        end = datetime.strptime(end, format)
    logger.debug(f"data_len start:{start}, {start.tzinfo}, end:{end}, {end.tzinfo}")
    if start.tzinfo is None and end.tzinfo == timezone.utc:
        start = start.replace(tzinfo=timezone.utc)
    interval = end - start
    if unit == 'second':
        return interval.seconds
    elif unit == 'day':
        return interval.days
    else:
        return None


def str2date(date_str, split_str='-'):
    """
    :param date_str: 2024; 2024-01; 2024-06-29
    :param split_str:
    :return 2024-01-01; 2024-01-01; 2024-06-29:
    """
    dates = date_str.split(' ')
    date = dates[0]
    split_list = date.split(split_str)
    ret_date = None
    if len(split_list) == 1:
        ret_date = datetime.strptime(date, '%Y').date()
    if len(split_list) == 2:
        ret_date = datetime.strptime(date, '%Y-%m').date()
    if len(split_list) == 3:
        ret_date = datetime.strptime(date, '%Y-%m-%d').date()
    return ret_date
