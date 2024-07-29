import base64
import copy
import datetime
import logging
from io import BytesIO

import qrcode
from django.conf import settings
from django.db import transaction, DatabaseError
from django.db.models import Q, F

from customadmin.models import GlobalConfig
from customadmin.service import get_global_configs
from vip.base_service import MemberTimeClock
from vip.models import Pay, TokensHistory, generate_trade_no, Member, MemberUsageLog
from vip.pay.wxpay import native_pay, weixin_notify, pay_status, h5_pay
from vip.serializers import MemberInfoSerializer, ExchangeQuerySerializer, TradesQuerySerializer, \
    TokensHistoryListFormatSerializer

logger = logging.getLogger(__name__)


def generate_pay_qrcode(user_id, out_trade_no, description, amount):
    code, msg, data = native_pay(out_trade_no, description, amount)
    if code == 200 and data and data.get('code_url'):
        code_url = data.get('code_url')
        image = qrcode.make(code_url).get_image()
        buffered = BytesIO()
        image.save(buffered, format="png")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        pay_data = {
            "out_trade_no": out_trade_no,
            "user_id": user_id,
            "amount": amount,
            "description": description,
            "url": code_url,
            'trade_type': Pay.TradeType.NATIVE,
            "appid": settings.WEIXIN_PAY_APPID,
            "mchid": settings.WEIXIN_PAY_MCHID,
            "trade_state": Pay.TradeState.NOTPAY
        }
        Pay.objects.create(**pay_data)
        return {"image": "data:image/png;base64," + img_str, "code_url": code_url, "out_trade_no": out_trade_no}
    else:
        return False


def generate_pay_h5_url(user_id, out_trade_no, description, amount, client_ip):
    code, msg, data = h5_pay(out_trade_no, description, amount, client_ip)
    if code == 200 and data and data.get('h5_url'):
        h5_url = data.get('h5_url')
        pay_data = {
            "out_trade_no": out_trade_no,
            "user_id": user_id,
            "amount": amount,
            "description": description,
            "url": h5_url,
            'trade_type': Pay.TradeType.H5,
            "appid": settings.WEIXIN_PAY_APPID,
            "mchid": settings.WEIXIN_PAY_MCHID,
            "trade_state": Pay.TradeState.NOTPAY
        }
        Pay.objects.create(**pay_data)
        return {"h5_url": h5_url, "out_trade_no": out_trade_no}
    else:
        return False


def pay_notify(request):
    data = weixin_notify(request)
    if data:
        out_trade_no = data['out_trade_no']
        pay = Pay.objects.filter(out_trade_no=out_trade_no).first()
        if not pay:
            logger.error(f"pay notify error, out_trade_no: {out_trade_no} not fund in pay")
            return False
        success_time = datetime.datetime.strptime(data['success_time'][:19], '%Y-%m-%dT%H:%M:%S')
        pay.amount = data['amount'].get('total')
        pay.transaction_id = data['transaction_id']
        pay.transaction_id = data['transaction_id']
        pay.trade_type = data['trade_type']
        pay.trade_state = data['trade_state']
        pay.trade_state_desc = data['trade_state_desc']
        pay.bank_type = data['bank_type']
        pay.attach = data['attach']
        pay.success_time = success_time
        pay.payer = data['payer'] | data['amount']
        pay.trade_state_desc = data['trade_state_desc']
        history_data = {
            "user_id": pay.user_id,
            # "trade_no": generate_trade_no(),
            "title": pay.description,
            "amount": int(pay.amount * settings.EXCHANGE_RATE_CNY2TOKENS / 100),
            "pay_amount": pay.amount,
            "type": TokensHistory.Type.WXPAY,
            "out_trade_no": pay.out_trade_no,
            "start_date": success_time,
            "end_date": None,
            # "status": TokensHistory.Status.HAS_BALANCE,
        }
        create_date = copy.deepcopy(history_data)
        create_date['status'] = TokensHistory.Status.COMPLETED
        create_date['trade_no'] = generate_trade_no()
        # add recode to TokensHistory
        TokensHistory.objects.update_or_create(
            defaults=history_data, create_defaults=create_date,
            out_trade_no=pay.out_trade_no, type=TokensHistory.Type.WXPAY
        )
        member = Member.objects.filter(user_id=pay.user_id).first()
        if not member:
            member = Member.objects.create(user_id=pay.user_id)
        member.update_amount()
        pay.save()
        return True
    return False


def pay_trade_state(out_trade_no, pay: Pay = None):
    if not pay:
        pay = Pay.objects.filter(out_trade_no=out_trade_no).first()
    if not pay:
        return None
    data = {
        "id": pay.id,
        "out_trade_no": pay.out_trade_no,
        "user_id": pay.user_id,
        "amount": pay.amount,
        "description": pay.description,
        "trade_state": pay.trade_state,
        "success_time": pay.success_time.strftime('%Y-%m-%d %H:%M:%S') if pay.success_time else None,
    }
    if pay.trade_state not in [Pay.TradeState.SUCCESS, Pay.TradeState.CLOSED]:
        status_info = pay_status(out_trade_no, transaction_id=pay.transaction_id)
        if status_info:
            status = status_info['trade_state']
            if status in [Pay.TradeState.SUCCESS, Pay.TradeState.CLOSED]:
                pay.trade_state = status_info['trade_state']
                pay.trade_state_desc = status_info['trade_state_desc']
                if status_info.get('success_time'):
                    pay.success_time = status_info['success_time']
                pay.save()
            data['trade_state'] = status_info['trade_state']
            if status_info.get('success_time'):
                data['success_time'] = pay.success_time.strftime('%Y-%m-%d %H:%M:%S')
    return data


def get_member_info(user_id):
    """
    member  账户信息
        余额
        账户类型 剩余天数
        问题使用量
        文件解析量
    :param user_id:
    :return:
    """
    clock_time = MemberTimeClock.get_member_time_clock(user_id)
    if clock_time:
        today = clock_time.date()
    else:
        today = datetime.date.today()
    member = Member.objects.filter(user_id=user_id).first()
    config = get_global_configs([
        GlobalConfig.ConfigType.MEMBER_FREE,
        GlobalConfig.ConfigType.MEMBER_STANDARD,
        GlobalConfig.ConfigType.MEMBER_PREMIUM,
        GlobalConfig.ConfigType.VIP,
    ])
    chat_static_day = MemberUsageLog.static_by_day(user_id, MemberUsageLog.UType.CHAT, today=today)
    embedding_static_monty = MemberUsageLog.static_by_month(user_id, MemberUsageLog.UType.EMBEDDING, today=today)
    if not member:
        config_limits = [
            c for c in config if c['config_type'] == GlobalConfig.ConfigType.MEMBER_FREE
                                 and c['sub_type'] == GlobalConfig.SubType.LIMIT
        ]
        config_limit = config_limits[0]['value'] if config_limits else None
        info = {
            "amount": 0,
            "member_type": Member.Type.FREE,
            "expire_days": None,
            "chat_used_day": chat_static_day,
            "limit_chat_daily": config_limit['limit_chat_daily'] if config_limit else None,
            "embedding_used_month": embedding_static_monty,
            "limit_embedding_monthly": config_limit['limit_embedding_monthly'] if config_limit else None,
        }
        data = MemberInfoSerializer(info).data
    else:
        member_type = member.get_member_type(today)
        expire_days = None
        if member_type == Member.Type.PREMIUM:
            expire_days = (member.premium_end_date - today).days + 1
        elif member_type == Member.Type.STANDARD:
            expire_days = (member.standard_end_date - today).days + 1
        config_limits = [
            c for c in config if c['config_type'] == member_type and c['sub_type'] == GlobalConfig.SubType.LIMIT]
        config_limit = config_limits[0]['value'] if config_limits else None
        info = {
            "amount": member.amount,
            "member_type": member_type,
            "expire_days": expire_days,
            "chat_used_day": chat_static_day,
            "limit_chat_daily": config_limit.get('limit_chat_daily') if config_limit else None,
            "embedding_used_month": embedding_static_monty,
            "limit_embedding_monthly": config_limit.get('limit_embedding_monthly') if config_limit else None,
        }
        data = MemberInfoSerializer(info).data
    return data


def tokens_expire_list(user_id):
    histories = TokensHistory.objects.filter(
        user_id=user_id, end_date__gte=datetime.date.today(), status__gt=TokensHistory.Status.DELETE,
        type__in=[TokensHistory.Type.SUBSCRIBED_BOT, TokensHistory.Type.INVITE_REGISTER,
                  TokensHistory.Type.NEW_USER_AWARD, TokensHistory.Type.DURATION_AWARD]
    ).all()
    data = []
    if histories:
        for history in histories:
            temp = {
                'id': history.id,
                'amount': history.amount - history.used,
                'end_date': history.end_date
            }
            if temp['amount'] > 0:
                data.append(temp)
    return data


def exchange_member(user_id, member_type, duration):
    member = Member.objects.filter(user_id=user_id).first()
    configs = get_global_configs([GlobalConfig.ConfigType.MEMBER_STANDARD, GlobalConfig.ConfigType.MEMBER_PREMIUM])
    configs = [c for c in configs if c['config_type'] == member_type and c['sub_type'] == GlobalConfig.SubType.EXCHANGE]
    config = configs[0]['value'] if configs else None
    if not config:
        return 100000, 'get config of member exchange', {}
    if duration == ExchangeQuerySerializer.Duration.THIRTY:
        amount = config['days_30']
    elif duration == ExchangeQuerySerializer.Duration.NINETY:
        amount = config['days_90']
    else:
        amount = config['days_360']
    if amount > member.amount or not member:
        return 160001, 'tokens not enough to exchange', {}
    if member := _consume_tokens(user_id, member, member_type, duration, amount):
        return 0, 'success', {}
    else:
        return 100000, 'system error try again later.', {}


def _consume_tokens(user_id, member, exchange_member_type, duration, amount):
    clock_time = MemberTimeClock.get_member_time_clock(user_id)
    if clock_time:
        today = clock_time.date()
    else:
        today = datetime.date.today()
    filter_query = Q(
        user_id=user_id,
        type__in=[
            TokensHistory.Type.WXPAY, TokensHistory.Type.SUBSCRIBED_BOT, TokensHistory.Type.INVITE_REGISTER,
            TokensHistory.Type.NEW_USER_AWARD, TokensHistory.Type.DURATION_AWARD
        ],
        status__gt=TokensHistory.Status.DELETE,
        amount__gt=F('used')
    )
    member = member.update_amount()
    histories = TokensHistory.objects.filter(filter_query).order_by('end_date', 'created_at')
    try:
        need_amount = amount
        with (transaction.atomic()):
            # update history consume tokens
            for history in histories:
                if history.amount - history.used >= need_amount:
                    history.used += need_amount
                    history.save()
                    break
                else:
                    need_amount -= history.amount - history.used
                    history.used = history.amount
                    history.save()
            # update member
            member.amount = max(0, member.amount - amount)
            member = _get_member_data(member, exchange_member_type, duration, today)
            member.save()

            in_progress_history = TokensHistory.objects.filter(
                user_id=user_id,
                status=TokensHistory.Status.IN_PROGRESS
            ).first()
            end_date = (
                member.standard_end_date
                if exchange_member_type == Member.Type.STANDARD else member.premium_end_date
            )
            start_date = end_date - datetime.timedelta(days=duration - 1)
            new_history_status = _get_new_exchange_history_status(in_progress_history, exchange_member_type)
            if in_progress_history and new_history_status == TokensHistory.Status.IN_PROGRESS:
                in_progress_history.status = TokensHistory.Status.FREEZING
                # in_progress_history.freezing_date = today
                in_progress_history.save()
            history_data = {
                'user_id': user_id,
                'trade_no': generate_trade_no(),
                'title': f"exchange {exchange_member_type} {duration} days",
                'amount': -amount,
                'type': _tokens_history_type(exchange_member_type, duration),
                'start_date': start_date,
                'end_date': end_date,
                'status': new_history_status
            }
            # 普通会员升级高级会员
            if (
                exchange_member_type == Member.Type.PREMIUM
                and member.standard_end_date
                and member.standard_end_date >= today
            ):
                standard_histories = TokensHistory.objects.filter(
                    user_id=user_id,
                    type__in=TokensHistory.TYPE_EXCHANGE_STANDARD,
                    end_date__gte=today,
                    status__gt=TokensHistory.Status.DELETE,
                ).all()
                for h in standard_histories:
                    if h.start_date >= today:
                        h.start_date += datetime.timedelta(days=duration)
                    h.end_date += datetime.timedelta(days=duration)
                    h.save()
            TokensHistory.objects.create(**history_data)
    except DatabaseError:
        return False
    return member


def _tokens_history_type(member_type, duration):
    if member_type == Member.Type.STANDARD:
        if duration == ExchangeQuerySerializer.Duration.THIRTY:
            return TokensHistory.Type.EXCHANGE_STANDARD_30
        elif duration == ExchangeQuerySerializer.Duration.NINETY:
            return TokensHistory.Type.EXCHANGE_STANDARD_90
        else:
            return TokensHistory.Type.EXCHANGE_STANDARD_360
    elif member_type == Member.Type.PREMIUM:
        if duration == ExchangeQuerySerializer.Duration.THIRTY:
            return TokensHistory.Type.EXCHANGE_PREMIUM_30
        elif duration == ExchangeQuerySerializer.Duration.NINETY:
            return TokensHistory.Type.EXCHANGE_PREMIUM_90
        else:
            return TokensHistory.Type.EXCHANGE_PREMIUM_360
    else:
        return None


def _get_member_data(member, member_type, duration, today=None):
    if not today:
        today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    if member_type == Member.Type.STANDARD:
        if not member.standard_start_date:
            member.standard_start_date = today
        if not member.standard_end_date:
            member.standard_end_date = today + datetime.timedelta(days=duration - 1)
        else:
            member.standard_end_date = max(member.standard_end_date, yesterday) + datetime.timedelta(days=duration)
    else:
        if not member.premium_start_date:
            member.premium_start_date = today
        if not member.premium_end_date:
            member.premium_end_date = today + datetime.timedelta(days=duration - 1)
        else:
            member.premium_end_date = max(member.premium_end_date, yesterday) + datetime.timedelta(days=duration)
        # 已经是普通会员兑换高级会员
        if (
            member.standard_end_date and member.standard_end_date > today
            and not member.standard_remain_days
        ):
            # remain_days = (member.standard_end_date - today).days + 1
            # member.standard_end_date = member.standard_end_date + datetime.timedelta(days=remain_days)
            member.standard_end_date = member.standard_end_date + datetime.timedelta(days=duration)
    return member


def _get_new_exchange_history_status(in_progress_history, exchange_member_type):
    if not in_progress_history:
        return TokensHistory.Status.IN_PROGRESS
    elif in_progress_history.type in TokensHistory.TYPE_EXCHANGE_STANDARD:
        if exchange_member_type == Member.Type.STANDARD:
            return TokensHistory.Status.FREEZING
        else:
            return TokensHistory.Status.IN_PROGRESS
    else:
        return TokensHistory.Status.FREEZING


def tokens_history_list(user_id, status, page_size, page_num, today=None):
    filter_query = Q(user_id=user_id, status__gt=TokensHistory.Status.DELETE)
    if not today:
        today = datetime.date.today()
    member = Member.objects.filter(user_id=user_id).first()
    if status == TradesQuerySerializer.Status.COMPLETED:
        if member.is_vip:
            filter_query &= (
                (Q(end_date__lt=today) & ~Q(status=TokensHistory.Status.FREEZING))
                | Q(status=TokensHistory.Status.COMPLETED)
            )
        else:
            filter_query &= (Q(end_date__lt=today) | Q(status=TokensHistory.Status.COMPLETED))
    elif status == TradesQuerySerializer.Status.VALID:
        if member.is_vip:
            filter_query &= Q(status__in=[TokensHistory.Status.FREEZING, TokensHistory.Status.IN_PROGRESS])
        else:
            filter_query &= Q(end_date__gte=today, type__in=TokensHistory.TYPE_EXCHANGE)
    histories = TokensHistory.objects.filter(filter_query).order_by('id')
    total = histories.count()
    histories = histories[(page_num - 1) * page_size:page_num * page_size]
    return total, histories


def format_history_list(user_id, histories):
    clock_time = MemberTimeClock.get_member_time_clock(user_id=user_id)
    if clock_time:
        today = clock_time.date()
    else:
        today = datetime.date.today()
    history_ids = [h.id for h in histories]
    histories = TokensHistory.histories_with_member_info(history_ids)
    for h in histories:
        h = TokensHistoryListFormatSerializer.format_used_info(h, today)
        h = TokensHistoryListFormatSerializer.format_status(h, today)
    return TokensHistoryListFormatSerializer(histories, many=True).data


def tokens_history_clock(histories, today):
    for h in histories:
        if h.type in TokensHistory.TYPE_EXCHANGE_STANDARD:
            if h.start_date <= today:
                h.status = TokensHistory.Status.COMPLETED
                h.save()
            elif h.start_date > today:
                h.status = TokensHistory.Status.FREEZING