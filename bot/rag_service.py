import datetime
import json
import logging

import requests
from django.conf import settings

from chat.models import Question, Conversation

logger = logging.getLogger(__name__)

RAG_HOST = settings.RAG_HOST
RAG_API_KEY = settings.RAG_API_KEY


class Bot:
    @staticmethod
    def create(
        user_id,
        prompt=None,
        preset_questions=None,
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
        resp = requests.get(url, headers={'X-API-KEY': RAG_API_KEY}, verify=False, timeout=60)
        logger.info(f'url: {url}, response: {resp}')
        if resp.status_code == 200:
            resp = resp.json()
        else:
            raise Exception(f'rag list error: {resp.status_code}, {resp.text}')
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
        resp = requests.post(url, json=post_data, headers={'X-API-KEY': RAG_API_KEY}, verify=False, timeout=600)
        logger.debug(f'search post_data: {post_data}')
        if resp.status_code == 200:
            resp = resp.json()
        else:
            raise Exception(f'rag search error: {resp.status_code}, {resp.text}')
        logger.info(f'url: {url}, response.len: {len(resp)}')
        return resp


class Conversations:
    @staticmethod
    def create(user_id, agent_id=None, paper_ids=None, public_collection_ids=None):
        url = RAG_HOST + '/api/v1/conversations'
        post_data = {
            'user_id': user_id,
            'agent_id': agent_id,
            'paper_ids': paper_ids,
            'public_collection_ids': public_collection_ids,
        }
        resp = requests.post(url, json=post_data, headers={'X-API-KEY': RAG_API_KEY}, verify=False, timeout=600)
        logger.debug(f'conversations create post_data: {post_data}')
        if resp.status_code == 200:
            resp = resp.json()
        else:
            raise Exception(f'rag search error: {resp.status_code}, {resp.text}')
        logger.info(f'url: {url}, response.len: {len(resp)}')
        return resp

    @staticmethod
    def update(conversation_id, agent_id, paper_ids=None, public_collection_ids=None):
        url = RAG_HOST + '/api/v1/conversations/' + conversation_id
        post_data = {
            'agent_id': agent_id,
            'paper_ids': paper_ids,
            'public_collection_ids': public_collection_ids,
        }
        resp = requests.put(url, json=post_data, headers={'X-API-KEY': RAG_API_KEY}, verify=False, timeout=600)
        logger.debug(f'update post_data: {post_data}')
        if resp.status_code == 200:
            resp = resp.json()
        else:
            raise Exception(f'rag search error: {resp.status_code}, {resp.text}')
        logger.info(f'url: {url}, response.len: {len(resp)}')
        return resp

    @staticmethod
    def generate_conversation_title(question, answer):
        url = RAG_HOST + '/api/v1/titles/conversation'
        post_data = {
            'question': question,
            'answer': answer,
        }
        resp = requests.post(url, json=post_data, headers={'X-API-KEY': RAG_API_KEY}, verify=False, timeout=20)
        logger.debug(f'generate_conversation_title post_data: {post_data}')
        if resp.status_code == 200:
            resp = resp.json()
        else:
            raise Exception(f'rag generate_conversation_title error: {resp.status_code}, {resp.text}')
        logger.info(f'url: {url}, response.len: {len(resp)}')
        return resp.get('title', f"未命名-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")

    @staticmethod
    def query(user_id, conversation_id, content, streaming=True, response_format='events'):
        def _format_stream_line(_stream, _line_data):
            _event = _line_data.get('event')
            if _event == 'tool_start':
                _stream['tool_start']['name'] = _line_data.get('name')
                _stream['input'] = _line_data.get('input')
            elif _event == 'tool_end':
                _stream['tool_end']['name'] = _line_data.get('name')
                _stream['output'] = eval(_line_data['output']) if _line_data.get('output') else None
            elif _event == 'model_statistics':
                _stream['model_statistics']['name'] = _line_data.get('name')
                _stream['run_id'] = _line_data.get('run_id')
                _stream['statistics'] = _line_data.get('statistics')
                _stream['metadata'] = _line_data.get('metadata')
            elif _event == 'on_error':
                _stream['on_error'] = _line_data.get('error')
            elif _event == 'model_stream':
                _stream['model_stream']['name'] = _line_data.get('name')
                _stream['chunk'].append(_line_data.get('chunk'))
            return _stream

        url = RAG_HOST + '/api/v1/query/conversation'
        post_data = {
            'content': content,
            'conversation_id': conversation_id,
            'user_id': user_id,
            # 'streaming': streaming,
            # 'response_format': response_format
        }
        resp = requests.post(url, json=post_data, headers={'X-API-KEY': RAG_API_KEY}, verify=False, timeout=30,
                             stream=True)
        logger.debug(f'query post_data: {post_data}')
        stream = {
            "input": {},
            "output": [],
            "run_id": None,
            "tool_start": {"name": None, "input": None, },
            "tool_end": {"name": None, "output": None, },
            "model_statistics": {"name": None, "statistics": None, "metadata": None, },
            "on_error": {},
            "model_stream": {"name": None, "chunk": None, },
            "metadata": {},
            "statistics": {},
            "chunk": []
        }
        question = None
        try:
            for line in resp.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    logger.debug(f'query line: {line}')
                    line_data = json.loads(line.strip("data: "))
                    if line_data and line_data.get('event'):
                        stream = _format_stream_line(stream, line_data)
                        if line_data['event'] == 'tool_end':
                            line_data['output'] = stream['output']
                        yield json.dumps(line_data) + '\n'
            question = Question.objects.create(
                conversation_id=conversation_id,
                content=content,
                stream=stream,
                input_tokens=stream.get('statistics', {}).get('input_tokens', 0),
                output_tokens=stream.get('statistics', {}).get('output_tokens', 0),
                answer=''.join(stream['chunk'])
            )
        except requests.exceptions.ChunkedEncodingError as chunked_error:
            logger.error(f'query chunked_error: {chunked_error}')
            yield json.dumps({'event': 'on_error', 'error': 'rag query/conversation service error, try again later',
                              'detail': str(chunked_error)})
        except requests.exceptions.ConnectionError as connection_error:
            logger.error(f'query connection_error: {connection_error}')
            yield json.dumps({'event': 'on_error', 'error': 'rag query/conversation service error, try again later',
                              'detail': str(connection_error)})
        yield json.dumps({
            'event': 'conversation', 'id': conversation_id, 'question_id': question.id if question else None
        })
        # todo update conversation.last_used_at
        conversation = Conversation.objects.get(pk=conversation_id)
        conversation.last_used_at = datetime.datetime.now()
        if not conversation.is_named:
            conversation.title = Conversations.generate_conversation_title(content, ''.join(stream['chunk']))
            conversation.is_named = True
        conversation.save()
