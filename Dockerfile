#FROM harbor.aiforgovernance.com/ai/ubuntu:20.04
FROM python:3.12

ADD core/deploy/sources.list /etc/apt/sources.list

ENV ROOT_DIR=/opt/app \
    PIP_CACHE_DIR=/.cache

RUN set -eux \
    && apt-get update && apt-get  -y upgrade \
    && apt-get install -y  \
#      gcc build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev  \
#      libgdbm-compat-dev libreadline-dev libffi-dev libsqlite3-dev libbz2-dev tk-dev uuid-dev \
#      mysql-client libmysqlclient-dev \
      vim git wget

RUN mkdir -p $ROOT_DIR
WORKDIR $ROOT_DIR

COPY core/deploy/requirements.txt ./

RUN python -m pip install --no-cache-dir --upgrade pip pip-tools
RUN python -m pip install --no-cache-dir -r requirements.txt


COPY . .


# 执行命令行,启动django服务
#CMD ["python3", "manage.py", "runserver", "0.0.0.0:8000"]
ENTRYPOINT ["./run.sh"]
