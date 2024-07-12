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
from vip.models import Pay, TokensHistory, generate_trade_no, Member, MemberUsageLog
from vip.pay.wxpay import native_pay, weixin_notify, pay_status
from vip.serializers import MemberInfoSerializer, ExchangeQuerySerializer, TokensHistoryListSerializer, \
    TradesQuerySerializer

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
            "code_url": code_url,
            "appid": settings.WEIXIN_PAY_APPID,
            "mchid": settings.WEIXIN_PAY_MCHID,
            "trade_state": Pay.TradeState.NOTPAY
        }
        Pay.objects.create(**pay_data)
        return {"image": "data:image/png;base64," + img_str, "code_url": code_url, "out_trade_no": out_trade_no}
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
            "start_date":success_time,
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
    data = {
        "id": pay.id,
        "out_trade_no": pay.out_trade_no,
        "user_id": pay.user_id,
        "amount": pay.amount,
        "description": pay.description,
        "trade_state": pay.trade_state,
        "success_time": pay.success_time.strftime('%Y-%m-%d %H:%M:%S'),
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
    member = Member.objects.filter(user_id=user_id).first()
    config = get_global_configs([
        GlobalConfig.ConfigType.MEMBER_FREE,
        GlobalConfig.ConfigType.MEMBER_STANDARD,
        GlobalConfig.ConfigType.MEMBER_PREMIUM,
    ])
    chat_static_day = MemberUsageLog.static_by_day(user_id, MemberUsageLog.UType.CHAT)
    embedding_static_monty = MemberUsageLog.static_by_month(user_id, MemberUsageLog.UType.EMBEDDING)
    if not member:
        config_limits = [
            c for c in config if c['config_type'] == GlobalConfig.ConfigType.MEMBER_FREE
            and c['sub_type'] == GlobalConfig.SubType.LIMIT
        ]
        config_limit = config_limits[0]['value'] if config_limits else None
        info = {
            "amount": 0,
            "member_type": MemberInfoSerializer.Type.FREE,
            "expire_days": None,
            "chat_used_day": chat_static_day,
            "limit_chat_daily": config_limit['limit_chat_daily'] if config_limit else None,
            "embedding_used_month": embedding_static_monty,
            "limit_embedding_monthly": config_limit['limit_embedding_monthly'] if config_limit else None,
        }
        data = MemberInfoSerializer(info).data
    else:
        member_type = MemberInfoSerializer.get_member_type(member)
        if member_type == MemberInfoSerializer.Type.VIP:
            info = {
                "amount": member.amount,
                "member_type": member_type,
            }
        else:
            expire_days = None
            if member_type == MemberInfoSerializer.Type.PREMIUM:
                expire_days = (member.premium_end_date - datetime.date.today()).days + 1
            elif member_type == MemberInfoSerializer.Type.STANDARD:
                expire_days = (member.standard_end_date - datetime.date.today()).days + 1
            config_limits = [
                c for c in config if c['config_type'] == member_type and c['sub_type'] == GlobalConfig.SubType.LIMIT]
            config_limit = config_limits[0]['value'] if config_limits else None
            info = {
                "amount": member.amount,
                "member_type": member_type,
                "expire_days": expire_days,
                "chat_used_day": chat_static_day[0].get('count'),
                "limit_chat_daily": config_limit['limit_chat_daily'] if config_limit else None,
                "embedding_used_month": embedding_static_monty[0].get('count'),
                "limit_embedding_monthly": config_limit['limit_embedding_monthly'] if config_limit else None,
            }
        data = MemberInfoSerializer(info).data
    return data


def tokens_expire_list(user_id):
    histories = TokensHistory.objects.filter(
        user_id=user_id, end_date__gte=datetime.date.today(), status__gt=TokensHistory.Status.DELETE,
        type__in=[TokensHistory.Type.SUBSCRIBED_BOT, TokensHistory.Type.INVITE_REGISTER,
                  TokensHistory.Type.REGISTER_AWARD, TokensHistory.Type.MONTHLY_AWARD]
    ).all()
    data = []
    if histories:
        for history in histories:
            temp = {
                'id': history.id,
                'amount': history.amount - history.used,
                'end_date': history.end_date
            }
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


def _consume_tokens(user_id, member, member_type, duration, amount):
    filter_query = Q(
        user_id=user_id,
        type__in=[
            TokensHistory.Type.WXPAY, TokensHistory.Type.SUBSCRIBED_BOT, TokensHistory.Type.INVITE_REGISTER,
            TokensHistory.Type.REGISTER_AWARD, TokensHistory.Type.MONTHLY_AWARD
        ],
        status__gt=TokensHistory.Status.DELETE,
        amount__gt=F('used')
    )
    member = member.update_amount()
    histories = TokensHistory.objects.filter(filter_query).order_by('end_date', 'created_at')
    try:
        need_amount = amount
        with (transaction.atomic()):
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
            member, freezing_standard_days = _get_member_data(member, member_type, duration)
            member.save()

            in_progress_history = TokensHistory.objects.filter(
                user_id=user_id,
                status=TokensHistory.Status.IN_PROGRESS
            ).first()
            end_date = (
                member.standard_end_date
                if member_type == MemberInfoSerializer.Type.STANDARD else member.premium_end_date
            )
            start_date = end_date - datetime.timedelta(days=duration - 1)
            new_history_status = _get_new_exchange_history_status(in_progress_history, member_type)
            if in_progress_history and new_history_status == TokensHistory.Status.IN_PROGRESS:
                in_progress_history.status = TokensHistory.Status.FREEZING
                in_progress_history.save()
            history_data = {
                'user_id': user_id,
                'trade_no': generate_trade_no(),
                'title': f"exchange {member_type} {duration} days",
                'amount': -amount,
                'type': _tokens_history_type(member_type, duration),
                'start_date': start_date,
                'end_date': end_date,
                'status': new_history_status
            }
            TokensHistory.objects.create(**history_data)
    except DatabaseError:
        return False
    return member


def _tokens_history_type(member_type, duration):
    if member_type == MemberInfoSerializer.Type.STANDARD:
        if duration == ExchangeQuerySerializer.Duration.THIRTY:
            return TokensHistory.Type.EXCHANGE_STANDARD_30
        elif duration == ExchangeQuerySerializer.Duration.NINETY:
            return TokensHistory.Type.EXCHANGE_STANDARD_90
        else:
            return TokensHistory.Type.EXCHANGE_STANDARD_360
    elif member_type == MemberInfoSerializer.Type.PREMIUM:
        if duration == ExchangeQuerySerializer.Duration.NINETY:
            return TokensHistory.Type.EXCHANGE_PREMIUM_30
        elif duration == ExchangeQuerySerializer.Duration.NINETY:
            return TokensHistory.Type.EXCHANGE_PREMIUM_90
        else:
            return TokensHistory.Type.EXCHANGE_PREMIUM_360
    else:
        return None


def _get_member_data(member, member_type, duration):
    freezing_standard_days = 0
    if member_type == MemberInfoSerializer.Type.STANDARD:
        if not member.standard_start_date:
            member.standard_start_date = datetime.date.today()
        if not member.standard_end_date:
            member.standard_end_date = datetime.date.today() + datetime.timedelta(days=duration - 1)
        else:
            member.standard_end_date = member.standard_end_date + datetime.timedelta(days=duration)
    else:
        if not member.premium_start_date:
            member.premium_start_date = datetime.date.today()
        if not member.premium_end_date:
            member.premium_end_date = datetime.date.today() + datetime.timedelta(days=duration - 1)
        else:
            member.premium_end_date = member.premium_end_date + datetime.timedelta(days=duration)

        if (
            member.standard_end_date and member.standard_end_date > datetime.date.today()
            and not member.standard_remain_days
        ):
            member.standard_remain_days = (member.standard_end_date - datetime.date.today()).days + 1
            freezing_standard_days = member.standard_remain_days
    return member, freezing_standard_days


def _get_new_exchange_history_status(in_progress_history, member_type):
    if not in_progress_history:
        return TokensHistory.Status.IN_PROGRESS
    elif in_progress_history.type in [
        TokensHistory.Type.EXCHANGE_STANDARD_30, TokensHistory.Type.EXCHANGE_STANDARD_90,
        TokensHistory.Type.EXCHANGE_STANDARD_360
    ] :
        if member_type == MemberInfoSerializer.Type.STANDARD:
            return TokensHistory.Status.FREEZING
        else:
            return TokensHistory.Status.IN_PROGRESS
    else:
         return TokensHistory.Status.FREEZING


def tokens_history_list(user_id, status, page_size, page_num):
    status_map = {
        TradesQuerySerializer.Status.COMPLETED: TokensHistory.Status.COMPLETED,
        TradesQuerySerializer.Status.IN_PROGRESS: TokensHistory.Status.IN_PROGRESS,
        TradesQuerySerializer.Status.FREEZING: TokensHistory.Status.FREEZING
    }
    status_tag = status_map.get(status, None)
    filter_query = Q(user_id=user_id, status__gt=TokensHistory.Status.DELETE)
    if status_tag:
        filter_query &= Q(status=status_tag)
    elif status == TradesQuerySerializer.Status.VALID:
        filter_query &= Q(status__in=[TokensHistory.Status.IN_PROGRESS, TokensHistory.Status.FREEZING])
    histories = TokensHistory.objects.filter(filter_query).order_by('-created_at')
    total = histories.count()
    histories = histories[(page_num - 1) * page_size:page_num * page_size]
    return total, histories


