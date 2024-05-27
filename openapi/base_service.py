from openapi.models import OpenapiLog


def record_openapi_log(user_id, openapi_key_id, api, status,
                       model=None, obj_id1=None, obj_id2=None, obj_id3=None):
    data = {
        'user_id': user_id,
        'openapi_key_id': openapi_key_id,
        'model': model,
        'api': api,
        'status': status,
        'obj_id1': obj_id1,
        'obj_id2': obj_id2,
        'obj_id3': obj_id3,
    }
    openapi_log = OpenapiLog.objects.create(**data)
    return openapi_log


def update_openapi_log_upload_status(task_id, status):
    openapi_log = OpenapiLog.objects.filter(obj_id1=task_id).first()
    if not openapi_log: return None
    openapi_log.status = status
    openapi_log.save()
    return openapi_log