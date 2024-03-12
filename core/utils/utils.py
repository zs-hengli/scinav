import uuid
from random import sample
from string import ascii_letters, digits


def generate_id(uuid_type=1, namespace=uuid.NAMESPACE_DNS, name='name'):
    if uuid_type == 3:
        return str(uuid.uuid3(namespace, name))
    if uuid_type == 4:
        return str(uuid.uuid4())
    if uuid_type == 5:
        return str(uuid.uuid5(namespace, name))
    return str(uuid.uuid1())


def random_str(str_len=8):
    return ''.join(sample(ascii_letters + digits, str_len))


def random_digits_str(str_len=10):
    my_digits = digits
    while len(my_digits) <= str_len:
        my_digits *= 10
    return ''.join(sample(my_digits, str_len))


def get_ms(time):
    """
    time.time()
    get millisecond of now in string of length 3
    """
    a = str(int(time * 1000) % 1000)
    if len(a) == 1:
        return '00' + a
    if len(a) == 2:
        return '0' + a
    return a
