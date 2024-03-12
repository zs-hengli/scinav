import datetime

from django.conf import settings
from minio import Minio, S3Error

from core.utils.exceptions import InternalServerError, ValidationError


def static_upload(bucket, business_type, direct_file_name, file_path=None, file_data: bytes = None, file_size=None):
    """
    上传文件
    :param bucket: 桶名称
    :param business_type: 模块类型
    :param direct_file_name: 上传到minio的目标文件名称
    :param file_path: 文件目录 不包括文件名
    :param file_data: 文件bytes
    :param file_size: 文件长度
    :return:
    """
    if not file_path and not file_data:
        raise ValidationError('文件地址和文件内容不能同时为空')
    client = MinioClient()
    date_str = datetime.datetime.now().strftime('%Y%m')
    direct_path = f"{business_type}/{date_str}/{direct_file_name}"
    if file_path:
        client.file_upload(file_path, bucket, direct_path)
    else:
        client.stream_upload(file_data, bucket, direct_path, file_size)
    return {'direct_path': direct_path, 'url': f'http://{settings.MINIO_HOST}/{bucket}/{direct_path}'}


class MinioClient:
    client = None

    def __init__(self):
        # 设置Minio服务器连接信息
        self.client = Minio(
            settings.MINIO_HOST,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False
        )

    def file_upload(self, source_path, bucket, direct_path):
        """
        上传本地文件 到Minio服务器
        :param source_path: 本地文件路径
        :param bucket: 存储桶名称
        :param direct_path: 对象名称
        :return:
        """
        try:
            self.client.fput_object(
                bucket,  # 存储桶名称
                direct_path,  # 对象名称
                source_path  # 本地文件路径
            )
        except S3Error as e:
            raise InternalServerError(f"上传文件出错: {e}")

    def stream_upload(self, data: bytes, bucket, direct_path, file_size):
        """
        上传文件对象 到Minio服务器
        :param data:  文件对象
        :param bucket: 存储桶名称
        :param direct_path: 对象名称
        :param file_size: 文件长度
        :return:
        """
        try:
            self.client.put_object(
                bucket,  # 存储桶名称
                direct_path,  # 对象名称
                data,  # 文件对象
                file_size,  # 文件大小
            )
        except S3Error as e:
            raise InternalServerError(f"上传文件出错: {e}")


if __name__ == '__main__':
    # 设置Minio服务器连接信息
    my_client = Minio(
        "minio.model-hubs.cn",
        access_key="minio",
        secret_key="minio123",
        secure=False
    )

    # 上传文件到Minio服务器
    try:
        # 上传本地文件
        my_client.fput_object(
            "tmp",  # 存储桶名称
            "tt/tmp001.log",  # 对象名称
            "/Users/liheng/java_error_in_idea_11224.log"  # 本地文件路径
        )

        # 上传文件对象
        # data = b"Hello, world!"
        # my_client.put_object(
        #     "my-bucket",  # 存储桶名称
        #     "my-object",  # 对象名称
        #     data,  # 文件对象
        #     len(data)  # 文件大小
        # )
    except S3Error as e:
        print("上传文件出错: {}".format(e))

    # 下载文件从Minio服务器
    # try:
    #     # 下载文件到本地
    #     my_client.fget_object(
    #         "my-bucket",  # 存储桶名称
    #         "my-object",  # 对象名称
    #         "/path/to/local/file"  # 本地文件路径
    #     )
    #
    #     # 下载文件对象
    #     data = my_client.get_object(
    #         "my-bucket",  # 存储桶名称
    #         "my-object"  # 对象名称
    #     )
    #     print(data.data.decode("utf-8"))
    # except S3Error as e:
    #     print("下载文件出错: {}".format(e))
