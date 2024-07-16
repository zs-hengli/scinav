import datetime
import logging
import traceback

from django.db import transaction, DatabaseError
from django.db.models import Q

from customadmin.models import GlobalConfig
from document.models import bulk_insert_ignore_duplicates
from vip.models import Member, generate_trade_no, TokensHistory

logger = logging.getLogger(__name__)


def tokens_award(user_id, award_type, amount=None, bot_id=None, period_of_validity=None):
    # todo 细化赠币规则
    try:
        with (transaction.atomic()):
            member = Member.objects.filter(user_id=user_id).first()
            if not member:
                member = Member.objects.create(user_id=user_id)
            # 获取amount
            if not amount:
                amount, period_of_validity = get_award_amount(award_type, member)
            end_date = (
                datetime.date.today() + datetime.timedelta(days=period_of_validity)
                if period_of_validity else None
            )
            history_data = {
                'user_id': user_id,
                'trade_no': generate_trade_no(),
                'title': f"award {award_type}",
                'amount': amount,
                'type': award_type,
                'start_date': datetime.date.today(),
                'end_date': end_date,
                'status': TokensHistory.Status.COMPLETED,
            }
            if bot_id:
                if TokensHistory.objects.filter(
                    type=award_type, out_trade_no=bot_id, user_id=user_id, status__gt=TokensHistory.Status.DELETE
                ).exists():
                    return True
                history_data['out_trade_no'] = bot_id
            TokensHistory.objects.create(**history_data)
            member.update_amount()
    except DatabaseError as e:
        logger.error(f'tokens award error, {e}, \n' + traceback.format_exc())
        return False
    pass


def get_award_amount(award_type, member: Member = None):
    amount, period_of_validity = 0, None
    g_config = GlobalConfig.get_award([award_type])
    config = g_config.get(award_type) if g_config else {}
    if award_type in [TokensHistory.Type.NEW_USER_AWARD, TokensHistory.Type.DURATION_AWARD]:
        amount = config.get('per') if config.get('per') else 0
    elif award_type in [TokensHistory.Type.INVITE_REGISTER, TokensHistory.Type.SUBSCRIBED_BOT]:
        count = TokensHistory.objects.filter(
            user_id=member.user_id, type=award_type,
            status__gt=TokensHistory.Status.DELETE).count()
        if config and config.get('limit') and count >= int(config.get('limit')):
            amount = 0
        else:
            amount = int(config['per']) if config.get('per') else 0
    if config.get('period_of_validity'):
        period_of_validity = config.get('period_of_validity')
    return amount, period_of_validity


def daily_member_status():
    # 每日任务 更新会员状态
    # 昨天到期的用户
    yesterday = datetime.date.today() + datetime.timedelta(days=-1)
    filter_query = Q(end_date=yesterday, status=TokensHistory.Status.IN_PROGRESS)
    histories = TokensHistory.objects.filter(filter_query).order_by('end_date')
    logger.info(f'daily member status, {histories.count()} record to update')
    update_data = []
    for history in histories:
        u_histories = TokensHistory.objects.filter(
            user_id=history.user_id, status=TokensHistory.Status.FREEZING).order_by('start_date')
        member = Member.objects.filter(user_id=history.user_id).first()
        if member.is_vip:
            continue
        # update member standard_remain_days
        if member.premium_end_date == yesterday and member.standard_remain_days:
            member.standard_end_date = yesterday + datetime.timedelta(days=member.standard_remain_days)
            member.standard_remain_days = 0
            member.save()
        # update histories
        history.status = TokensHistory.Status.COMPLETED
        update_data.append(history)
        if same_level_freezing := [h for h in u_histories if h.type == history.type]:
            same_level_freezing[0].status = TokensHistory.Status.IN_PROGRESS
            update_data.append(same_level_freezing[0])
        elif freezing_histories := [h for h in u_histories if h.freezing_date]:
            freezing_history = freezing_histories[0]
            freezing_remain_days = (freezing_history.end_date - freezing_history.freezing_date).days + 1
            new_days = (
                (yesterday + datetime.timedelta(days=freezing_remain_days)) - freezing_history.end_date
            ).days
            for u_history in u_histories:
                if u_history.freezing_date:
                    u_history.freezing_date = None
                    u_history.status = TokensHistory.Status.IN_PROGRESS
                else:
                    u_history.start_date += datetime.timedelta(days=new_days)
                u_history.end_date += datetime.timedelta(days=new_days)
                update_data.append(u_history)
        else:
            u_history = u_histories.first()
            u_history.status = TokensHistory.Status.IN_PROGRESS
            update_data.append(u_history)
        update_fileds = ['status', 'start_date', 'end_date', 'freezing_date', 'updated_at']
        TokensHistory.objects.bulk_update(update_data, update_fileds)


def daily_duration_award():
    """
    每日任务 赠送会员时长
    :return:
    """
    today = datetime.date.today()
    configs = GlobalConfig.get_award([GlobalConfig.SubType.DURATION])
    if not configs.get(GlobalConfig.SubType.DURATION) or not configs[GlobalConfig.SubType.DURATION].get('duration'):
        return
    config = configs[GlobalConfig.SubType.DURATION]
    duration = config.get('duration')
    amount = config.get('per')
    period_of_validity = config.get('period_of_validity')
    # 没有Member记录的用户赠送代币
    no_member_users = Member.get_no_member_users()
    member_dicts, history_objs = [], []
    if no_member_users:
        for user_id in no_member_users:
            member_dicts.append({
                'user_id': user_id, 'amount': amount,
                'created_at': datetime.datetime.now(),
                'updated_at': datetime.datetime.now()
            })
    # 上次赠送时间超过duration的用户赠送代币
    user_ids = TokensHistory.get_need_duration_award_user(duration)
    award_users = list(set(no_member_users + user_ids))
    if award_users:
        for user_id in award_users:
            history_objs.append(TokensHistory(
                user_id=user_id,
                trade_no=generate_trade_no(),
                title=f"duration award {duration}",
                amount=amount,
                type=TokensHistory.Type.DURATION_AWARD,
                start_date=today,
                end_date=today + datetime.timedelta(days=period_of_validity - 1),
                status=TokensHistory.Status.COMPLETED,
            ))
    try:
        with (transaction.atomic()):
            if member_dicts:
                bulk_insert_ignore_duplicates(Member, member_dicts)
            TokensHistory.objects.bulk_create(history_objs)
            members = Member.objects.filter(user_id__in=award_users)
            for member in members:
                member.update_amount()
    except DatabaseError as e:
        logger.error(f'daily_duration_award error, {e}, \n' + traceback.format_exc())

    # 代币过期处理
    if histories := TokensHistory.get_expire_history():
        history_objs = []
        for history in histories:
            history_objs.append(TokensHistory(
                user_id=history['user_id'],
                trade_no=generate_trade_no(),
                out_trade_no=history['trade_no'],
                title=f"duration award {duration}",
                amount=-history['amount'],
                type=TokensHistory.Type.EXPIRATION,
                status=TokensHistory.Status.COMPLETED,
            ))

        TokensHistory.objects.bulk_create(history_objs)
        members = Member.objects.filter(user_id__in=[h['user_id'] for h in histories])
        for member in members:
            member.update_amount()
