import datetime

from django.db import transaction, DatabaseError

from customadmin.models import GlobalConfig
from vip.models import Member, generate_trade_no, TokensHistory
from vip.serializers import MemberInfoSerializer


def tokens_award(user_id, award_type, amount=None, bot_id=None):
    # todo 细化赠币规则
    try:
        with (transaction.atomic()):
            member = Member.objects.filter(user_id=user_id).first()
            if not member:
                member = Member.objects.create(user_id=user_id)
            # 获取amount
            if not amount:
                # 新用户登录
                # 邀请新用户
                pass
            member.amount += amount
            member.save()
            history_data = {
                'user_id': user_id,
                'trade_no': generate_trade_no(),
                'title': f"award {award_type}",
                'amount': amount,
                'type': award_type,
                'start_date': datetime.date.today(),
                'end_date': datetime.date.today() + datetime.timedelta(days=60),
                'status': TokensHistory.Status.COMPLETED,
            }
            if bot_id:
                history_data['out_trade_no'] = bot_id
            TokensHistory.objects.create(**history_data)
    except DatabaseError:
        return False
    pass


def register_award_amount(member: Member):
    # 新用户奖励
    config = GlobalConfig.get_award(['register_award'])
    register_config = config.get('register_award') if config else {}
    return register_config.get('per') if register_config.get('per') else 0


def invite_register_amount(member: Member):
    # 新用户奖励
    config = GlobalConfig.get_award(['invite_register'])
    register_config = config.get('invite_register') if config else {}
    count = TokensHistory.objects.filter(
        user_id=member.user_id, type=TokensHistory.Type.INVITE_REGISTER, status__gt=TokensHistory.Status.DELETE).count()
    if register_config.get('limit') and count >= int(register_config.get('limit')):
        return 0
    return int(register_config['per']) if register_config.get('per') else 0