import datetime
import logging
from random import sample
from string import digits

from django.db import models, connection
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


def my_custom_sql(sql, params=None, ret_dict=True):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        if ret_dict:
            return dict_fetchall(cursor)
        rows = cursor.fetchall()
    return rows


def dict_fetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# 会员信息：member
class Member(models.Model):

    class Type(models.TextChoices):
        FREE = 'member_free', _('member_free')
        STANDARD = 'member_standard', _('member_standard')
        PREMIUM = 'member_premium', _('member_premium')
        VIP = 'vip', _('vip')

    user = models.ForeignKey(
        'user.MyUser', unique=True, db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    amount = models.IntegerField(default=0)
    standard_start_date = models.DateField(null=True)
    standard_end_date = models.DateField(null=True)
    standard_remain_days = models.IntegerField(null=True)
    premium_start_date = models.DateField(null=True)
    premium_end_date = models.DateField(null=True)
    premium_remain_days = models.IntegerField(null=True)
    is_vip = models.BooleanField(default=False, db_default=False)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)
    del_flag = models.BooleanField(default=False, db_default=False)

    def update_amount(self):
        sql = f"""
                SELECT SUM(amount) as amount
                FROM tokens_history
                WHERE user_id = '{self.user_id}'
                AND status != 0
        """
        rest = my_custom_sql(sql)
        if rest and self.amount != rest[0]['amount']:
            self.amount = rest[0]['amount']
            self.save()
        else:
            logger.error('update_amount error sql: {sql}')
        return self

    @staticmethod
    def get_no_member_users():
        sql = f"""
        SELECT my_user.id as user_id FROM my_user left join member on member.user_id=my_user.id
        WHERE member.user_id is null
        """
        rest = my_custom_sql(sql)
        return [i['user_id'] for i in rest]

    @staticmethod
    def get_members_by_admin(user_id=None, email=None, phone=None, page_size=10, page_num=1):
        select_sql = """select m.id,m.user_id,u.email,u.phone,u.date_joined,m.amount,
    m.standard_end_date,m.premium_end_date,m.is_vip"""
        from_sql = """ from member m left join my_user u on m.user_id=u.id where 1=1 """
        where = ''
        if user_id or email or phone:
            where += ' and ('
        or_sql = ''
        if user_id:
            or_sql += f"{'or' if or_sql else ''} m.user_id = '{user_id}'"
        if email:
            or_sql += f" {'or' if or_sql else ''} u.email = '{email}'"
        if phone:
            or_sql += f" {'or' if or_sql else ''} u.phone = '{phone}'"
        if where:
            where += f"{or_sql})"
        count_sql = f"select count(1) as count {from_sql} {where}"
        count_rest = my_custom_sql(count_sql)
        limit_sql = f" limit {page_size} offset {(page_num - 1) * page_size}"
        rest = my_custom_sql(f"{select_sql} {from_sql} {where} {limit_sql}")
        return {'total': count_rest[0]['count'], 'list': rest}

    def get_member_type(self, today=None):
        if not today:
            today = datetime.date.today()
        if self.is_vip:
            member_type = self.Type.VIP
        elif self.premium_end_date and self.premium_end_date > today:
            member_type = self.Type.PREMIUM
        elif self.standard_end_date and self.standard_end_date > today:
            member_type = self.Type.STANDARD
        else:
            member_type = self.Type.FREE
        return member_type

    class Meta:
        db_table = 'member'
        verbose_name = 'member'


# 代币充值和使用记录 tokens_history
class TokensHistory(models.Model):
    class Type(models.TextChoices):
        WXPAY = 'wxpay', _('wxpay')
        EXCHANGE_STANDARD_30 = 'exchange_standard_30', _('exchange_standard_30')
        EXCHANGE_STANDARD_90 = 'exchange_standard_90', _('exchange_standard_90')
        EXCHANGE_STANDARD_360 = 'exchange_standard_360', _('exchange_standard_360')
        EXCHANGE_PREMIUM_30 = 'exchange_premium_30', _('exchange_premium_30')
        EXCHANGE_PREMIUM_90 = 'exchange_premium_90', _('exchange_premium_90')
        EXCHANGE_PREMIUM_360 = 'exchange_premium_360', _('exchange_premium_360')
        SUBSCRIBED_BOT = 'subscribed_bot', _('subscribed_bot')
        INVITE_REGISTER = 'invite_register', _('invite_register')
        DURATION_AWARD = 'duration_award', _('duration_award')
        NEW_USER_AWARD = 'new_user_award', _('new_user_award')  # todo 新用户奖励 包括注册 一次性奖励 固定周期奖励
        EXPIRATION = 'expiration', _('expiration')

    class Status(models.IntegerChoices):
        DELETE = 0, _('delete'),
        COMPLETED = 2, _('completed')
        IN_PROGRESS = 3, _('in_progress')
        FREEZING = 4, _('freezing')

    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    trade_no = models.CharField(max_length=128)
    title = models.CharField(max_length=256, null=True, default=None, db_default=None)
    amount = models.IntegerField(default=0, db_default=0)
    pay_amount = models.IntegerField(default=0, db_default=0)
    used = models.IntegerField(default=0, db_default=0)
    type = models.CharField(max_length=128, null=True, default=None, db_default=None, choices=Type)
    out_trade_no = models.CharField(max_length=128, null=True, default=None, db_default=None)
    start_date = models.DateField(null=True, default=None, db_default=None)
    freezing_date = models.DateField(null=True, default=None, db_default=None)
    end_date = models.DateField(null=True, default=None, db_default=None)
    give_user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='give_user_id',
        related_name='give_user')
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)
    status = models.IntegerField(null=True, default=None, db_default=None, choices=Status)

    @staticmethod
    def get_expire_history(users_clock=None):
        where_sql = []
        if users_clock:
            for user_id, clock_time in users_clock.items():
                where_sql.append(f"(h1.user_id = '{user_id}' and h1.end_date < '{clock_time}')")
        else:
            where_sql.append('h1.end_date < current_timestamp::date')

        sql = f"""SELECT h1.* FROM tokens_history h1 
left join tokens_history h2 on h1.trade_no = h2.out_trade_no
where h1.type = 'duration_award' AND h2.id is null
        """
        sql += ' and (' + ' or '.join(where_sql) + ')'
        rest = my_custom_sql(sql)
        return rest

    @staticmethod
    def get_need_duration_award_user(duration):
        rest = my_custom_sql(f"""select user_id from (
select user_id, max(start_date) m_start_date
from tokens_history where type='duration_award' or type='new_user_award' group by user_id
union all
select m.user_id, h.start_date m_start_date 
from member m LEFT JOIN tokens_history h on m.user_id=h.user_id and h.type='duration_award'
where  h.id is null) t
where (CURRENT_TIMESTAMP - INTERVAL '{duration - 1} day')::date > m_start_date or m_start_date is null
        """)
        return [i['user_id'] for i in rest]

    @staticmethod
    def get_histories_by_admin(user_id=None, email=None, phone=None, trade_no=None, types=None,
                               page_size=10, page_num=1):
        select_sql = """select h.*,u.email,u.phone,u.date_joined"""
        from_sql = """ from tokens_history h left join my_user u on h.user_id=u.id where 1=1 """
        where = ''
        if user_id or email or phone or trade_no:
            where += ' and ('
        or_sql = ''
        if user_id:
            where += f"{'or' if or_sql else ''} h.user_id = '{user_id}'"
        if email:
            where += f"{'or' if or_sql else ''} u.email = '{email}'"
        if phone:
            where += f"{'or' if or_sql else ''} u.phone = '{phone}'"
        if trade_no:
            where += f"{'or' if or_sql else ''} h.trade_no = '{trade_no}'"
        if where:
            where += f"{or_sql})"
        if types:
            if isinstance(types, list):
                types = "'" + "','".join(types) + "'"
            where += f" and h.type in ({types})"

        count_sql = f"select count(1) as count {from_sql} {where}"
        count_rest = my_custom_sql(count_sql)
        limit_sql = f" limit {page_size} offset {(page_num - 1) * page_size}"
        rest = my_custom_sql(f"{select_sql} {from_sql} {where} {limit_sql}")
        return {'total': count_rest[0]['count'], 'list': rest}

    @staticmethod
    def histories_with_member_info(history_ids):
        if not history_ids:
            return []
        else:
            history_ids = ','.join(map(str, history_ids))
        sql = f"""select h.*, m.standard_end_date,m.premium_end_date,m.is_vip,m.amount as member_amount
from tokens_history h  left join member m on h.user_id=m.user_id
where h.id in ({history_ids}) order by h.id"""
        rest = my_custom_sql(sql)
        return rest

    class Meta:
        db_table = 'tokens_history'
        verbose_name = 'tokens history'


# 付款记录 pay
class Pay(models.Model):
    class TradeState(models.TextChoices):
        SUCCESS = 'SUCCESS', _('SUCCESS'),
        NOTPAY = 'NOTPAY', _('NOTPAY'),
        CLOSED = 'CLOSED', _('CLOSED'),
        REFUND = 'REFUND', _('REFUND')

    class TradeType(models.TextChoices):
        NATIVE = 'NATIVE', _('NATIVE'),
        JSAPI = 'JSAPI', _('JSAPI'),
        H5 = 'H5', _('H5')

    user = models.ForeignKey(
        'user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True, db_column='user_id')
    amount = models.IntegerField(default=0, db_default=0)
    appid = models.CharField(max_length=128, null=True, default=None, db_default=None)
    mchid = models.CharField(max_length=128, null=True, default=None, db_default=None)
    description = models.CharField(max_length=128, null=True, default=None, db_default=None)
    url = models.CharField(max_length=128, null=True, default=None, db_default=None)
    out_trade_no = models.CharField(max_length=128, null=True, default=None, db_default=None)
    transaction_id = models.CharField(max_length=128, null=True, default=None, db_default=None)
    trade_type = models.CharField(max_length=128, null=True, default=None, db_default=None)
    trade_state = models.CharField(max_length=128, null=True, default=None, db_default=None, choices=TradeState)
    trade_state_desc = models.CharField(max_length=128, null=True, default=None, db_default=None)
    bank_type = models.CharField(max_length=128, null=True, default=None, db_default=None)
    attach = models.CharField(max_length=128, null=True, default=None, db_default=None)
    success_time = models.DateTimeField(null=True, default=None, db_default=None)
    payer = models.JSONField(null=True, default=None, db_default=None)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=True, auto_now_add=True)
    del_flag = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'pay'
        verbose_name = 'pay'


class MemberUsageLog(models.Model):
    """
    会员使用记录
    CONVERSATION obj_id1: conversation_id obj_id2:question_id
    UPLOAD_PAPER obj_id1: document_library_id
    """

    class UType(models.IntegerChoices):
        # CONVERSATION = 2
        CHAT = 2
        EMBEDDING = 3
        # UPLOAD_PAPER = 3

    class Status(models.IntegerChoices):
        UNKNOWN = 0
        SUCCESS = 1
        FAILED = 2

    user = models.ForeignKey('user.MyUser', db_constraint=False, on_delete=models.DO_NOTHING, null=True)
    openapi_key = models.ForeignKey(
        'openapi.OpenapiKey', db_constraint=False, on_delete=models.DO_NOTHING, null=True
    )
    model = models.CharField(max_length=256, null=True, default=None, db_default=None)
    type = models.IntegerField(choices=UType, db_index=True)
    obj_id1 = models.CharField(null=True, db_index=True, max_length=40, default=None, db_default=None)
    obj_id2 = models.CharField(null=True, db_index=True, max_length=40, default=None, db_default=None)
    obj_id3 = models.BigIntegerField(null=True, db_index=True, default=None, db_default=None)
    status = models.IntegerField(choices=Status, default=Status.UNKNOWN, db_default=Status.UNKNOWN)
    updated_at = models.DateTimeField(null=True, auto_now=True)
    created_at = models.DateTimeField(null=False, db_index=True, auto_now_add=True)

    @staticmethod
    def static_by_month(user_id, utype):
        sql = (f"select count(*) from member_usage_log where type={utype} and user_id='{user_id}'"
               f" and status in ({MemberUsageLog.Status.SUCCESS}, {MemberUsageLog.Status.UNKNOWN})"
               f" and created_at>=to_timestamp(substring(to_char(now(),'yyyy-MM-dd hh24:MI:ss') FROM 1 FOR 10"
               f"),'yyyy-MM-dd') - interval '30 day'")
        # logger.debug(f'ddddddddd static_by_month sql: {sql}')
        static = my_custom_sql(sql)
        return static[0].get('count', 0) if static else 0

    @staticmethod
    def static_by_day(user_id, utype):
        sql = ("select count(*) as count from member_usage_log"
               f" where type={utype} and user_id='{user_id}' and created_at>=current_date "
               f" and status in ({MemberUsageLog.Status.SUCCESS}, {MemberUsageLog.Status.UNKNOWN})")
        # logger.debug(f'dddddddddd static_by_day sql: {sql}')
        static = my_custom_sql(sql)
        return static[0].get('count', 0) if static else 0

    class Meta:
        db_table = 'member_usage_log'
        verbose_name = 'member usage log'


def generate_trade_no():
    now = datetime.datetime.now()
    trade_no = (now.strftime('%Y%m%d%H%M%S%f'))[:16] + ''.join(sample(digits, 4))
    return trade_no
