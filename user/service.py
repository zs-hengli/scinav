from user.models import MyUser


def save_auth_user_info(user_info):
    info = {
        'id': user_info['sub'],
        'username': user_info['name'] if user_info['name'] else user_info['sub'],
        'nickname': user_info['nickname'],
        'avatar': user_info['picture'],
        'email': user_info['email'],
        'phone': user_info['phone_number'],
        'updated_at': user_info['updated_at'],
        'is_staff': 1
    }
    user, _ = MyUser.objects.update_or_create(
        defaults=info,
        id=info['id']
    )
    return user


def sync_user_info(user: MyUser, user_info):
    if user.id == user_info['id'] and user.register_source != user_info.get('registerSource'):
        user.register_source = user_info['registerSource']
        user.save()
    return user