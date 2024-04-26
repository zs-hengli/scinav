from bot.models import Bot, BotCollection
from bot.rag_service import Bot as RagBot
from collection.models import Collection, CollectionDocument
from core.utils.exceptions import InternalServerError


def recreate_bot(bot: Bot, collections):
    RagBot.delete(bot.agent_id)
    public_collection_ids = [c.id for c in collections if c.type == c.TypeChoices.PUBLIC]
    rag_ret = RagBot.create(
        bot.user_id,
        bot.prompt,
        bot.questions,
        paper_ids=collections_doc_ids(collections),
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


def collections_doc_ids(collections: list[Collection]):
    _cids = [c.id for c in collections if c.type == c.TypeChoices.PERSONAL]
    c_docs = CollectionDocument.objects.filter(collection_id__in=_cids).all()
    return [{
        'collection_id': c_doc.document.collection_id,
        'collection_type': c_doc.document.collection_type,
        'doc_id': c_doc.document.doc_id} for c_doc in c_docs
    ]