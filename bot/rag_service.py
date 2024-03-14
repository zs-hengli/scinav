import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

RAG_HOST = settings.RAG_HOST
RAG_API_KEY = settings.RAG_API_KEY


class Bot:
    @staticmethod
    def create(
        user_id,
        prompt,
        preset_questions,
        # llm=None,
        # tools=None,
        paper_ids=None,
        public_collection_ids=None
    ):
        url = RAG_HOST + '/api/v1/agents'
        post_data = {
            'user_id': user_id,
            # 'type': type,
        }
        if preset_questions: post_data['preset_questions'] = preset_questions
        if prompt and prompt['spec']['system_prompt']: post_data['prompt'] = prompt
        if paper_ids: post_data['paper_ids'] = paper_ids
        if public_collection_ids: post_data['public_collection_ids'] = public_collection_ids
        logger.debug(f'create post_data: {post_data}')
        resp = requests.post(url, json=post_data, headers={'X-API-KEY': RAG_API_KEY}, timeout=60).json()
        logger.info(f'url: {url}, post: {post_data}, response: {resp}')
        return resp

    @staticmethod
    def delete(agent_id):
        url = RAG_HOST + '/api/v1/agents/' + agent_id
        resp = requests.delete(url, headers={'X-API-KEY': RAG_API_KEY}, verify=False, timeout=60)
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
        resp = requests.get(url, headers={'X-API-KEY': RAG_API_KEY}, verify=False, timeout=60).json()
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
        resp = requests.post(url, json=post_data, headers={'X-API-KEY': RAG_API_KEY}, verify=False, timeout=600).json()
        logger.debug(f'search post_data: {post_data}')
        logger.info(f'url: {url}, response.len: {len(resp)}')
        return resp
