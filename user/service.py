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