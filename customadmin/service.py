import datetime
import json
import logging
import re
import traceback

from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.contenttypes.models import ContentType
from django.db import transaction, DatabaseError

from core.utils.common import check_uuid4_str, check_email_str
from customadmin.models import GlobalConfig
from customadmin.serializers import GlobalConfigDetailSerializer, MembersListSerializer, \
    TokensHistoryAdminListSerializer
from vip.base_service import tokens_award
from vip.models import Member, TokensHistory

logger = logging.getLogger(__name__)


def get_global_configs(config_types):
    configs = GlobalConfig.objects.filter(
        config_type__in=config_types, del_flag=False).order_by('config_type', 'sub_type').all()
    data = GlobalConfigDetailSerializer(configs, many=True).data
    return data


def set_global_configs(user_id, configs):
    for config in configs:
        config_type = config.get('config_type')
        sub_type = config.get('sub_type')
        value = config.get('value')
        name = config.get('name', '')

        config_obj = GlobalConfig.objects.filter(config_type=config_type, sub_type=sub_type, del_flag=False).first()
        if config_obj:
            if value:
                config_obj.value = value
            if name:
                config_obj.name = name
            config_obj.save()
        else:
            data = {
                'name': name,
                'config_type': config_type,
                'sub_type': sub_type,
                'value': value,
                'order': 0,
                'updated_by': user_id
            }
            GlobalConfig.objects.create(**data)


def get_members(keyword, page_size=10, page_num=1):
    user_id, email, phone = None, None, None
    if keyword:
        # user_id  66583f7945fb8a982a4d6f0a  af35a6ea-d9db-442c-8fd1-88a69846424e
        if check_uuid4_str(keyword) or re.search('^[a-f0-9]{24}$', keyword):
            user_id = keyword
        if check_email_str(keyword):
            email = keyword
        if re.search(r'^(?:\+\d{1,2}\s?)?1[3-9]\d{9}$', keyword):
            phone = keyword
    members_info = Member.get_members_by_admin(
        user_id=user_id, email=email, phone=phone, page_size=page_size, page_num=page_num)
    members_info['list'] = MembersListSerializer(members_info['list'], many=True).data
    return members_info


def members_admin_award(member, amount, period_of_validity, admin_id):
    if tokens_award(
        user_id=member.user_id,
        award_type='new_user_award',
        amount=amount,
        period_of_validity=period_of_validity,
        admin_id=admin_id,
    ):
        return True
    return False


def update_member_vip(member: Member, admin_id, is_vip:bool = True):
    member_type = member.get_member_type()
    member.is_vip = is_vip
    today = datetime.date.today()
    update_history_data = []
    if is_vip:
        if member_type in [Member.Type.STANDARD, Member.Type.PREMIUM]:
            # update member
            if member_type == Member.Type.STANDARD:
                member.standard_remain_days = (member.standard_end_date - datetime.date.today()).days + 1
            else:
                member.premium_remain_days = (member.premium_end_date - datetime.date.today()).days + 1
            member.save()
            # update tokens_history
            in_progress_history = TokensHistory.objects.filter(
                user_id=member.user_id, status=TokensHistory.Status.IN_PROGRESS).first()
            in_progress_history.status = TokensHistory.Status.FREEZING
            in_progress_history.freezing_date = today
            update_history_data.append(in_progress_history)
    else:
        u_histories = []
        if member.premium_remain_days:
            member.premium_end_date = today + datetime.timedelta(days=member.premium_remain_days - 1)
            member.premium_remain_days = 0
            u_histories = TokensHistory.objects.filter(
                user_id=member.user_id,
                status=TokensHistory.Status.FREEZING,
                type__in=[TokensHistory.Type.EXCHANGE_PREMIUM_30, TokensHistory.Type.EXCHANGE_PREMIUM_90,
                          TokensHistory.Type.EXCHANGE_PREMIUM_360],
            ).order_by('start_date', 'id').all()
        elif member.standard_remain_days:
            member.standard_end_date = today + datetime.timedelta(days=member.standard_remain_days - 1)
            member.standard_remain_days = 0
            u_histories = TokensHistory.objects.filter(
                user_id=member.user_id,
                status=TokensHistory.Status.FREEZING,
                type__in=[TokensHistory.Type.EXCHANGE_STANDARD_30, TokensHistory.Type.EXCHANGE_STANDARD_90,
                          TokensHistory.Type.EXCHANGE_STANDARD_360],
            ).order_by('start_date', 'id').all()
        if freezing_histories := [h for h in u_histories if h.freezing_date]:
            freezing_history = freezing_histories[0]
            freezing_remain_days = (freezing_history.end_date - freezing_history.freezing_date).days + 1
            new_days = (
                (datetime.date.today() + datetime.timedelta(days=freezing_remain_days)) - freezing_history.end_date
            ).days
            for u_history in u_histories:
                if u_history.id == freezing_history.id:
                    u_history.freezing_date = None
                    u_history.status = TokensHistory.Status.IN_PROGRESS
                else:
                    u_history.start_date += datetime.timedelta(days=new_days - 1)
                u_history.end_date += datetime.timedelta(days=new_days - 1)
                update_history_data.append(u_history)
        elif histories := [h for h in u_histories]:
            in_progress_history = histories[0]
            in_progress_history.status = TokensHistory.Status.IN_PROGRESS
            update_history_data.append(in_progress_history)
    try:
        with (transaction.atomic()):
            if update_history_data:
                TokensHistory.objects.bulk_update(
                    update_history_data, ['start_date', 'end_date', 'freezing_date', 'status'])
            member.save()
            LogEntry(
                user_id=admin_id,
                action_flag=CHANGE,
                object_id=member.id,
                object_repr=f'member id({member.id}), user({member.user_id}) set vip to {is_vip}',
                change_message=json.dumps({"is_vip": is_vip, "id": member.id, "user_id": member.user_id}),
                content_type_id=ContentType.objects.get_for_model(Member).id,
            ).save()
    except DatabaseError as e:
        logger.error(f'tokens award error, {e}, \n' + traceback.format_exc())
        return False
    return True


def get_trades(keyword, page_size=10, page_num=1):
    user_id, email, phone, trade_no = None, None, None, None
    if keyword:
        # user_id  66583f7945fb8a982a4d6f0a  af35a6ea-d9db-442c-8fd1-88a69846424e
        if check_uuid4_str(keyword) or re.search('^[a-f0-9]{24}$', keyword):
            user_id = keyword
        if check_email_str(keyword):
            email = keyword
        if re.search(r'^(?:\+\d{1,2}\s?)?1[3-9]\d{9}$', keyword):
            phone = keyword
        if re.search(r'^\d{20}$', keyword):
            trade_no = keyword
    histories_info = TokensHistory.get_histories_by_admin(
        user_id=user_id, email=email, phone=phone, trade_no=trade_no, page_size=page_size, page_num=page_num)
    histories_info['list'] = TokensHistoryAdminListSerializer(histories_info['list'], many=True).data
    return histories_info