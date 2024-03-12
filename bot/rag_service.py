import json
import logging
import requests

from django.conf import settings
from django.core.cache import cache

from core.utils.common import str_hash

logger = logging.getLogger(__name__)

RAG_HOST = settings.RAG_HOST
RAG_API_KEY = settings.RAG_API_KEY


class Bot:
    @staticmethod
    def create(
        user_id,
        prompt,
        preset_questions,
        type='OpenAPIFunctionsAgent',
        # llm=None,
        # tools=None,
        paper_ids=None,
        public_collection_ids=None
    ):
        url = RAG_HOST + '/api/v1/agents'
        post_data = {
            'user_id': user_id,
            'type': type,
        }
        if preset_questions: post_data['preset_questions'] = preset_questions
        if prompt: post_data['prompt'] = prompt
        if paper_ids: post_data['paper_ids'] = paper_ids
        if public_collection_ids: post_data['public_collection_ids'] = public_collection_ids
        logger.debug(f'post_data:{post_data}')
        resp = requests.post(url, json=post_data, headers={'X-API-KEY': RAG_API_KEY}).json()
        logger.info(f'url: {url}, post: {post_data}, response: {resp}')
        return resp

    @staticmethod
    def delete(agent_id):
        url = RAG_HOST + '/api/v1/agents/' + agent_id
        resp = requests.delete(url, headers={'X-API-KEY': RAG_API_KEY}, verify=False)
        logger.info(f'url: {url}, response: {resp}')
        return resp


class Collection:
    @staticmethod
    def list():
        """
        [{"id":"arxiv","name":"arXiv","total":10,"update_time":"2024-03-09T10:20:18"}]
        :return:
        """
        url = RAG_HOST + '/api/v1/public-collections'
        resp = requests.get(url, headers={'X-API-KEY': RAG_API_KEY}, verify=False).json()
        logger.info(f'url: {url}, response: {resp}')
        return resp


class Document:
    @staticmethod
    def search(user_id, content, search_type='embedding', limit=1000, filter_conditions=None):
        url = RAG_HOST + '/api/v1/papers/search'
        post_data = {
            'user_id': user_id,
            'content': content,
            'type': search_type,
            'limit': limit
        }
        if filter_conditions: post_data['filter_conditions'] = filter_conditions
        resp = requests.post(url, json=post_data, headers={'X-API-KEY': RAG_API_KEY}, verify=False).json()
        logger.info(f'url: {url}, response: {resp}')
        return resp