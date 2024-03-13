import datetime
import logging

from bot.models import Bot, BotCollection, BotSubscribe, HotBot
from bot.rag_service import Bot as RagBot
from bot.serializers import (BotDetailSerializer, BotListAllSerializer,
                             HotBotListSerializer)
from collection.models import Collection, CollectionDocument
from core.utils.exceptions import InternalServerError
from document.models import Document
from document.serializers import DocumentListSerializer

logger = logging.getLogger(__name__)


# 创建专题
def bot_create(body):
    data = {
        'user_id': body['user_id'],
        'author': body['author'],
        'title': body['title'],
        'description': body['description'],
        'prompt': body.get('prompt_spec', None),
        'questions': body['questions'],
        # 'llm': body['llm'],
        # 'tools': body['tools'],
        'cover_url': body['cover_url'],
        'type': body['type'],
    }
    if data['prompt']:
        data['prompt'] = {
            'type': 'SystemPrompt',
            "spec": {
                "system_prompt": data['prompt'],
            }
        }
    collections = Collection.objects.filter(id__in=body['collections']).all()
    public_collection_ids = [c.id for c in collections if c.type == c.TypeChoices.PUBLIC]
    rag_ret = RagBot.create(
        data['user_id'],
        data['prompt'],
        data['questions'],
        paper_ids=_collections_doc_ids(collections),
        public_collection_ids=public_collection_ids,
    )
    if rag_ret.get('id'):
        data['extension'] = rag_ret
        data['agent_id'] = rag_ret['id']
        data['prompt'] = rag_ret['spec']['prompt']
        bot = Bot.objects.create(**data)
        # save BotCollection
        for c in collections:
            bot_c_data = {
                'bot_id': bot.id,
                'collection_id': c.id,
                'collection_type': c.type
            }
            BotCollection.objects.create(**bot_c_data)
    else:
        raise InternalServerError('RAG create bot failed')
    return BotDetailSerializer(bot).data


def _collections_doc_ids(collections: list[Collection]):
    cids = [c.id for c in collections if c.type == c.TypeChoices.PERSONAL]
    documents = Document.objects.filter(collection_id__in=cids).all()
    return [
        {'collection_id': doc.collection_id,
         'collection_type': Collection.TypeChoices.PERSONAL,
         'doc_id': doc.doc_id
         } for doc in documents
    ]


# 修改专题
def bot_update(bot_id, body):
    bot: Bot = Bot.objects.get(pk=bot_id)
    data = {'user_id': body['user_id']}
    if body.get('author') and bot.author != body['author']:
        data['author'] = body['author']
        bot.author = body['author']
    if body.get('title') and bot.title != body['title']:
        data['title'] = body['title']
        bot.title = body['title']
    if body.get('description') and bot.description != body['description']:
        data['description'] = body['description']
        bot.description = body['description']
    if body.get('questions') and bot.questions != body['questions']:
        data['questions'] = body['questions']
        bot.questions = body['questions']
    if body.get('cover_url') and bot.cover_url != body['cover_url']:
        data['cover_url'] = body['cover_url']
        bot.cover_url = body['cover_url']
    if body.get('prompt_spec') and bot.prompt['spec']['system_prompt'] != body.get('prompt_spec'):
        data['prompt_spec'] = body['prompt_spec']
        bot.prompt['spec']['system_prompt'] = body.get('prompt_spec')
    logger.debug(f'bot_update data: {data}')
    collections = BotCollection.objects.filter(bot=bot, del_flag=False).all()
    collection_ids = [bc.collection_id for bc in collections]
    collections_change = False
    if body.get('collections') and set(collection_ids) != set(body['collections']):
        collections_change = True

    need_recreate_filed = ['questions', 'prompt_spec']
    if set(need_recreate_filed) & set(data.keys()) or collections_change:
        _recreate_bot(bot, collection_ids, data)
    bot.save()
    return BotDetailSerializer(bot).data


def _recreate_bot(bot: Bot, collection_ids, data):
    RagBot.delete(bot.agent_id)
    collections = Collection.objects.filter(id__in=collection_ids).all()
    public_collection_ids = [c.id for c in collections if c.type == c.TypeChoices.PUBLIC]
    rag_ret = RagBot.create(
        data['user_id'],
        bot.prompt,
        bot.questions,
        paper_ids=_collections_doc_ids(collections),
        public_collection_ids=public_collection_ids,
    )
    if rag_ret.get('id'):
        bot.extension = rag_ret
        bot.agent_id = rag_ret['id']
        BotCollection.objects.filter(bot_id=bot.id).update(del_flag=True)
        # save BotCollection
        for c in collections:
            bc_data = {
                'bot_id': bot.id,
                'collection_id': c.id,
                'collection_type': c.type,
                'del_flag': False,
            }
            BotCollection.objects.update_or_create(
                bc_data, bot_id=bc_data['bot_id'], collection_id=bc_data['collection_id'])
    else:
        raise InternalServerError('RAG create bot failed')


# 删除专题
def bot_delete(bot_id):
    bot = Bot.objects.get(pk=bot_id)
    RagBot.delete(bot.agent_id)
    BotCollection.objects.filter(bot_id=bot.id).update(del_flag=True)
    bot.del_flag = True
    bot.save()
    return bot_id


# 专题详情
def bot_detail(user_id, bot_id):
    bot = Bot.objects.get(pk=bot_id)
    bot_data = BotDetailSerializer(bot).data
    if is_subscribed(user_id, bot):
        bot_data['subscribed'] = True
    else:
        bot_data['subscribed'] = False
    return bot_data


def is_subscribed(user_id, bot: Bot):
    # if bot.user_id == user_id:
    #     return True
    if BotSubscribe.objects.filter(user_id=user_id, bot=bot).exists():
        return True
    return False


# 专题文献列表
# bot collection list
def bot_docs(bot_id):
    ag_collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False).all()
    collections = [ag_c.collection for ag_c in ag_collections]
    collection_ids = [c.id for c in collections]
    c_documents = CollectionDocument.objects.filter(collection_id__in=collection_ids, del_flag=False).all()
    return DocumentListSerializer(c_documents, many=True).data


# 专题列表
def hot_bots():
    hot_bot = HotBot.objects.filter(del_flag=False).order_by('order_num').all()
    hot_bot_list_data = HotBotListSerializer(hot_bot, many=True).data
    return hot_bot_list_data


def bot_list_all(user_id, page_size=10, page_num=1):
    user_subscribe_bot = BotSubscribe.objects.filter(user_id=user_id, del_flag=False).all()
    us_bot_ids = [us_b.bot_id for us_b in user_subscribe_bot]
    query_set = Bot.objects.filter(type=Bot.TypeChoices.PUBLIC, del_flag=False).order_by('-pub_date')
    filter_count = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
    bots = query_set[start_num:(page_size * page_num)]
    bot_list_data = BotListAllSerializer(bots, many=True).data
    for index, b_data in enumerate(bot_list_data):
        bot_list_data[index]['subscribed'] = False
        if b_data['id'] in us_bot_ids:
            bot_list_data[index]['subscribed'] = True
    return {
        'list': bot_list_data,
        'total': filter_count
    }


def bot_list_subscribe(user_id, page_size=10, page_num=1):
    user_subscribe_bot = BotSubscribe.objects.filter(user_id=user_id, del_flag=False).all()
    bot_ids = [us_bot.bot_id for us_bot in user_subscribe_bot]
    query_set = Bot.objects.filter(id__in=bot_ids, del_flag=False).order_by('-pub_date')
    filter_count = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
    bots = query_set[start_num:(page_size * page_num)]

    bot_list_data = BotListAllSerializer(bots, many=True).data
    for index, b_data in enumerate(bot_list_data):
        bot_list_data[index]['subscribed'] = True
    return {
        'list': bot_list_data,
        'total': filter_count
    }


def bot_list_my(user_id, page_size=10, page_num=1):
    query_set = Bot.objects.filter(user_id=user_id, del_flag=False).order_by('-pub_date')
    filter_count = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
    bots = query_set[start_num:(page_size * page_num)]

    bot_list_data = BotListAllSerializer(bots, many=True).data
    for index, b_data in enumerate(bot_list_data):
        bot_list_data[index]['subscribed'] = True

    return {
        'list': bot_list_data,
        'total': filter_count
    }


# 专题订阅和取消订阅
def bot_subscribe(user_id, bot_id, action='subscribe'):
    # 订阅： 加个人文件库 创建同名收藏夹
    # 取消订阅 删除收藏夹
    # todo 收藏夹有调整 增加文献时修改订阅者的个人文件库
    data = {
        'user_id': user_id,
        'bot_id': bot_id,
        'del_flag': action != 'subscribe'
    }
    BotSubscribe.objects.update_or_create(data, user_id=user_id, bot_id=bot_id)


# 专题文献列表
def bot_documents(bot_id, page_size=10, page_num=1):
    bot_collections = BotCollection.objects.filter(bot_id=bot_id, del_flag=False)
    collections = [bc.collection for bc in bot_collections]
    collection_ids = [c.id for c in collections if c.type == c.TypeChoices.PERSONAL]
    query_set = CollectionDocument.objects.filter(collection_id__in=collection_ids).order_by('-updated_at')
    total = query_set.count()
    start_num = page_size * (page_num - 1)
    logger.debug(f"limit: [{start_num}: {page_size * page_num}]")
    c_docs = query_set[start_num:(page_size * page_num)] if total > start_num else []
    docs = [cd.document for cd in c_docs]

    docs_data = DocumentListSerializer(docs, many=True).data
    return {
        'list': docs_data,
        'total': total
    }


def bot_publish(bot_id, action=Bot.TypeChoices.PUBLIC):
    bot = Bot.objects.filter(pk=bot_id).first()
    if not bot:
        return -1, 'bot not exist'
    if action == Bot.TypeChoices.PUBLIC:
        bot.type = Bot.TypeChoices.PUBLIC
        bot.pub_date = datetime.datetime.now()
    else:
        bot.type = Bot.TypeChoices.PERSONAL
    bot.save()
    return 0, ''
