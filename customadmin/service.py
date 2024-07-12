from customadmin.models import GlobalConfig
from customadmin.serializers import GlobalConfigDetailSerializer


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
