import datetime
import logging
import traceback

from django.conf import settings
from django.core.cache import cache
from django.db import transaction, DatabaseError
from django.db.models import Q

from core.utils.date import SHA_TZ
from customadmin.models import GlobalConfig
from document.models import bulk_insert_ignore_duplicates
from vip.models import Member, generate_trade_no, TokensHistory, Pay

logger = logging.getLogger(__name__)


def tokens_award(
    user_id, award_type, amount=None, bot_id=None, period_of_validity=None, admin_id=None, new_user_id=None
):
    # todo 细化赠币规则
    try:
        with (transaction.atomic()):
            member = Member.objects.filter(user_id=user_id).first()
            if not member:
                member = Member.objects.create(user_id=user_id)
            # 获取amount
            if not amount:
                amount, period_of_validity = get_award_amount(award_type, member)
                if not amount:
                    return True
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
            if admin_id:
                history_data['give_user_id'] = admin_id
            if new_user_id:
                history_data['out_trade_no'] = new_user_id
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


# def daily_member_status():
#     # 每日任务 更新会员状态
#     # 昨天到期的用户
#     today = datetime.date.today()
#     yesterday = datetime.date.today() + datetime.timedelta(days=-1)
#     filter_query = Q(end_date__lte=yesterday, status=TokensHistory.Status.IN_PROGRESS)
#     histories = TokensHistory.objects.filter(filter_query).order_by('end_date')
#     logger.info(f'daily member status, {histories.count()} record to update')
#     update_history_data = []
#     for history in histories:
#         u_histories = TokensHistory.objects.filter(
#             user_id=history.user_id, status=TokensHistory.Status.FREEZING).order_by('start_date', 'id')
#         member = Member.objects.filter(user_id=history.user_id).first()
#         if member.is_vip:
#             continue
#         # update member standard_remain_days
#         if member.premium_end_date <= yesterday and member.standard_remain_days:
#             member.standard_end_date = member.premium_end_date + datetime.timedelta(days=member.standard_remain_days)
#             member.standard_remain_days = 0
#             member.save()
#         # update histories
#         history.status = TokensHistory.Status.COMPLETED
#         update_history_data.append(history)
#         if same_level_freezing := [h for h in u_histories.all() if h.type == history.type]:
#             same_level_freezing[0].status = TokensHistory.Status.IN_PROGRESS
#             update_history_data.append(same_level_freezing[0])
#         elif freezing_histories := [h for h in u_histories.all() if h.freezing_date]:
#             freezing_history = freezing_histories[0]
#             freezing_remain_days = (freezing_history.end_date - freezing_history.freezing_date).days + 1
#             new_days = (
#                 (history.end_date + datetime.timedelta(days=freezing_remain_days)) - freezing_history.end_date
#             ).days
#             for u_history in u_histories.all():
#                 if u_history.id == freezing_history.id:
#                     u_history.freezing_date = None
#                     u_history.status = TokensHistory.Status.IN_PROGRESS
#                 else:
#                     u_history.start_date += datetime.timedelta(days=new_days - 1)
#                 u_history.end_date += datetime.timedelta(days=new_days - 1)
#                 update_history_data.append(u_history)
#         else:
#             if in_progress_history := u_histories.first():
#                 in_progress_history.status = TokensHistory.Status.IN_PROGRESS
#                 update_history_data.append(in_progress_history)
#         update_fileds = ['status', 'start_date', 'end_date', 'freezing_date', 'updated_at']
#         if update_history_data:
#             TokensHistory.objects.bulk_update(update_history_data, update_fileds)


def daily_duration_award():
    """
    每日任务 赠送会员代币并清理过期代币
    :return:
    """
    today = datetime.date.today()
    configs = GlobalConfig.get_award([GlobalConfig.SubType.DURATION])
    config = configs[GlobalConfig.SubType.DURATION]
    if config and config.get('duration'):
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
                title=f"{history['title']} expire",
                amount=-history['amount'],
                type=TokensHistory.Type.EXPIRATION,
                status=TokensHistory.Status.COMPLETED,
            ))

        TokensHistory.objects.bulk_create(history_objs)
        members = Member.objects.filter(user_id__in=[h['user_id'] for h in histories])
        for member in members:
            member.update_amount()





class MemberTimeClock:
    REDIS_KEY = 'scinav:time_clock:member'

    @classmethod
    def get_member_time_clock(cls, user_id: str = None) -> datetime.date | dict | bool:
        env = settings.ENV
        if env != 'dev':
            return False
        if clock_conf := cache.get(cls.REDIS_KEY):
            pass
        else:
            clock_conf = GlobalConfig.objects.filter(
                config_type=GlobalConfig.ConfigType.TIME_CLOCK, sub_type=GlobalConfig.SubType.MEMBER).first()
            cache.set(cls.REDIS_KEY, clock_conf, 60 * 60 * 24)
        if user_id:
            if clock_conf and clock_conf.value and clock_conf.value.get(user_id):
                clock_str = clock_conf.value[user_id]
                try:
                    if clock_time := datetime.datetime.strptime(clock_str, '%Y-%m-%d %H:%M:%S'):
                        return clock_time
                except:
                    logger.warning(f'get_member_time_clock error, {clock_str}, \n' + traceback.format_exc())
        else:
            if clock_conf and clock_conf.value:
                data = {}
                for user_id, clock_str in clock_conf.value.items():
                    data[user_id] = datetime.datetime.strptime(clock_str, '%Y-%m-%d %H:%M:%S')
                return data
        return False

    @classmethod
    def update_member_time_clock(cls, user_id: str, clock_time: datetime.datetime) -> (int, str):
        env = settings.ENV
        if env != 'dev':
            return 200000, 'environment not dev'

        clock_conf = GlobalConfig.objects.filter(
            config_type=GlobalConfig.ConfigType.TIME_CLOCK, sub_type=GlobalConfig.SubType.MEMBER).first()
        if clock_conf and clock_conf.value and clock_conf.value.get(user_id):
            clock_str = clock_conf.value[user_id]
            old_time = datetime.datetime.strptime(clock_str, '%Y-%m-%d %H:%M:%S')
            old_time_aware = old_time.astimezone(SHA_TZ)
            clock_time_aware = clock_time.astimezone(SHA_TZ)
            if old_time_aware > clock_time_aware:
                return 200001, f'clock time error, new time must greater than old time({old_time})'
        config_value = clock_conf.value if clock_conf and clock_conf.value else {}
        config_value[user_id] = clock_time.strftime('%Y-%m-%d %H:%M:%S')
        if clock_conf:
            clock_conf.value = config_value
            clock_conf.save()
        else:
            config_data = {
                'name': '会员相关测试时钟设置',
                'order': 0,
                'updated_by': 'system',
                'config_type': GlobalConfig.ConfigType.TIME_CLOCK,
                'sub_type': GlobalConfig.SubType.MEMBER,
                'value': config_value
            }
            clock_conf = GlobalConfig.objects.create(**config_data)
        cache.set(cls.REDIS_KEY, clock_conf, 60 * 60 * 24)
        return 0, 'success'

    @classmethod
    def init_member_time_clock(cls, user_id: str):
        env = settings.ENV
        if env != 'dev':
            return 200000, 'environment not dev'
        clock_conf = GlobalConfig.objects.filter(
            config_type=GlobalConfig.ConfigType.TIME_CLOCK, sub_type=GlobalConfig.SubType.MEMBER).first()

        if clock_conf and clock_conf.value and clock_conf.value.get(user_id):
            try:
                with (transaction.atomic()):
                    # del clock_conf.value[user_id]
                    del clock_conf.value[user_id]
                    clock_conf.save()
                    # del history_tokens record include exchange and expiration records
                    TokensHistory.objects.filter(
                        user_id=user_id,
                        type__in=[TokensHistory.Type.EXCHANGE_STANDARD_30, TokensHistory.Type.EXCHANGE_PREMIUM_90,
                                  TokensHistory.Type.EXCHANGE_STANDARD_360,
                                  TokensHistory.Type.EXCHANGE_PREMIUM_30, TokensHistory.Type.EXCHANGE_STANDARD_90,
                                  TokensHistory.Type.EXCHANGE_PREMIUM_360,
                                  TokensHistory.Type.EXPIRATION,
                                  ]).delete()
                    # update member record
                    member = Member.objects.filter(user_id=user_id).first()
                    member.standard_start_date = None
                    member.standard_end_date = None
                    member.standard_remain_days = 0
                    member.premium_start_date = None
                    member.premium_end_date = None
                    member.save()
                    member.update_amount()
            except DatabaseError as e:
                logger.error(f'init_member_time_clock user_id:{user_id} error, {e}, \n' + traceback.format_exc())
                return 200001, 'init member time clock error'
        cache.delete(cls.REDIS_KEY)
        cls.daily_expire_clock_duration_award(is_clock=False)
        return 0, 'success'

    @classmethod
    def daily_expire_clock_duration_award(cls, is_clock=True):
        """
        每日任务 赠送会员代币并清理过期代币 单独处理有 clock time 的用户
        :return:
        """
        users_clock = None
        if is_clock:
            clock_times = MemberTimeClock.get_member_time_clock()
            users_clock = {k: v.strftime('%Y-%m-%d') for k, v in clock_times.items()}
            if not users_clock:
                return True
        if histories := TokensHistory.get_expire_history(users_clock):
            history_objs = []
            for history in histories:
                history_objs.append(TokensHistory(
                    user_id=history['user_id'],
                    trade_no=generate_trade_no(),
                    out_trade_no=history['trade_no'],
                    title=f"{history['title']} expire",
                    amount=-history['amount'],
                    type=TokensHistory.Type.EXPIRATION,
                    status=TokensHistory.Status.COMPLETED,
                ))

            TokensHistory.objects.bulk_create(history_objs)
            members = Member.objects.filter(user_id__in=[h['user_id'] for h in histories])
            for member in members:
                member.update_amount()
        return True