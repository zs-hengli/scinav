import datetime
import logging
import uuid

import certifi
import requests
from django.conf import settings
from requests import RequestException

logger = logging.getLogger(__name__)

RAG_HOST = settings.RAG_HOST
RAG_API_KEY = settings.RAG_API_KEY


def rag_requests(url, json=None, method='POST', headers=None, timeout=20, stream=None, raise_for_status=True):
    if headers is None:
        headers = {}
    request_id = settings.REQUEST_ID[:24] + str(uuid.uuid4())[24:] if settings.REQUEST_ID else str(uuid.uuid4())
    logger.info(f'url: {url}, request_id: {request_id}, json: {json}')
    headers.update({'X-API-KEY': RAG_API_KEY, 'X-REQUEST-ID': request_id})
    try:
        if method == 'POST':
            resp = requests.post(
                url, json=json, headers=headers, verify=certifi.where(), timeout=timeout, stream=stream)
        elif method == 'GET':
            resp = requests.get(url, headers=headers, verify=certifi.where(), timeout=timeout)
        elif method == 'DELETE':
            resp = requests.delete(url, headers=headers, verify=certifi.where(), timeout=timeout)
        elif method == 'PUT':
            resp = requests.put(url, json=json, headers=headers, verify=certifi.where(), timeout=timeout)
        else:
            raise RequestException(f"unknown method: {method}")
    except Exception as e:
        logger.error(e)
        raise RequestException(f"{url}, {e}")
    if raise_for_status:
        resp.raise_for_status()  # 自动处理非200响应
    return resp


class Bot:
    @staticmethod
    def create(
        user_id,
        prompt=None,
        preset_questions=None,
        # llm=None,
        tools=None,
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
        if tools:
            new_tools = []
            for tool in tools:
                tmp = {
                    'type': 'OpenAPIToolset',
                    'spec': {
                        'name': tool['name'],
                        'url': tool['url'],
                        'openapi_json_path': tool['openapi_json_path'],
                        'authentication': tool['endpoints'],
                    }
                }
                new_tools.append(tmp)
            post_data['tools'] = new_tools
        resp = rag_requests(url, json=post_data, method='POST')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

    @staticmethod
    def delete(agent_id):
        url = RAG_HOST + '/api/v1/agents/' + agent_id
        resp = rag_requests(url, method='DELETE')
        logger.info(f'url: {url}, response: {resp.text}')
        return resp

    @staticmethod
    def openapi_tools(name, openapi_url, openapi_json_path, authentication):
        url = RAG_HOST + '/api/v1/agents/tools/openapi-tool'
        post_data = {
            'name': name,
            'url': openapi_url,
            'openapi_json_path': openapi_json_path,
            'authentication': authentication,
        }
        resp = rag_requests(url, json=post_data, method='POST', raise_for_status=False)
        logger.info(f'url: {url}, response: {resp.text}')
        if resp.status_code != 200:
            return False
        return True


class Collection:
    @staticmethod
    def list():
        """
        [{"id":"arxiv","name":"arXiv","total":10,"update_time":"2024-03-09T10:20:18"}]
        :return:
        """
        url = RAG_HOST + '/api/v1/public-collections'
        resp = rag_requests(url, method='GET')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp


class Document:
    @staticmethod
    def get(validation_data):
        vd = validation_data
        url = RAG_HOST + f"/api/v1/papers/{vd['collection_type']}/{vd['collection_id']}/{vd['doc_id']}"
        resp = rag_requests(url, method='GET')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

    @staticmethod
    def citations(collection_type, collection_id, doc_id):
        url = RAG_HOST + f"/api/v1/papers/{collection_type}/{collection_id}/{doc_id}/citations"
        resp = rag_requests(url, method='GET')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

    @staticmethod
    def references(collection_type, collection_id, doc_id):
        url = RAG_HOST + f"/api/v1/papers/{collection_type}/{collection_id}/{doc_id}/references"
        resp = rag_requests(url, method='GET')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

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
        resp = rag_requests(url, json=post_data, method='POST')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        logger.info(f'url: {url}, response.len: {len(resp)}')
        return resp

    @staticmethod
    def presigned_url(user_id, public_key, operation_type, filename=None, object_path=None):
        """
        return:
        {
            "presigned_url": "string",
            "object_path": "string",
            "expires_in": 0
        }
        """
        url = RAG_HOST + '/api/v1/papers/presigned-url'
        if operation_type == 'put_object':
            post_data = {
                'public_key': public_key,
                'user_id': user_id,
                'operation_type': operation_type,
                'filename': filename,
            }
        else:
            post_data = {
                'public_key': public_key,
                'user_id': user_id,
                'operation_type': operation_type,
                'object_path': object_path,
            }

        resp = rag_requests(url, json=post_data, method='POST')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

    @staticmethod
    def ingest_personal_paper(user_id, object_path):
        url = RAG_HOST + '/api/v1/papers/ingest-task/personal'
        post_data = {
            'user_id': user_id,
            'object_path': object_path
        }
        resp = rag_requests(url, json=post_data, method='POST')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

    @staticmethod
    def ingest_public_paper(user_id, collection_id, doc_id):
        url = RAG_HOST + '/api/v1/papers/ingest-task/public'
        post_data = {
            'user_id': user_id,
            'collection_id': collection_id,
            'doc_id': doc_id
        }
        resp = rag_requests(url, json=post_data, method='POST')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

    @staticmethod
    def get_ingest_task(task_id):
        url = RAG_HOST + f'/api/v1/papers/ingest-task/{task_id}'
        resp = rag_requests(url, method='GET')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

    @staticmethod
    def delete_personal_paper(collection_id, doc_id):
        url = RAG_HOST + f'/api/v1/papers/personal/{collection_id}/{doc_id}'
        resp = rag_requests(url, method='DELETE')
        logger.info(f'url: {url}, response: {resp.text}')
        return resp

    @staticmethod
    def cancel_ingest_task(task_id):
        url = RAG_HOST + f'/api/v1/papers/ingest-task/{task_id}'
        resp = rag_requests(url, method='PUT')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

    @staticmethod
    def complete_abstract(user_id, collection_id, doc_id):
        url = RAG_HOST + f'/api/v1/tasks/paper-abstract-completion'
        post_data = {
            'user_id': user_id,
            'collection_id': collection_id,
            'doc_id': doc_id
        }
        resp = rag_requests(url, json=post_data, method='POST')
        logger.info(f'url: {url}, post_data: {post_data}, response: {resp.text}')
        resp = resp.json()
        return resp



class Conversations:
    @staticmethod
    def create(
        user_id, conversation_id, agent_id=None, paper_ids=None, public_collection_ids=None,
        llm_name=None, history_messages=None
    ):
        url = RAG_HOST + '/api/v1/conversations'
        post_data = {
            'id': conversation_id,
            'user_id': user_id,
            'agent_id': agent_id,
            'paper_ids': paper_ids,
            'public_collection_ids': public_collection_ids,
            'llm_name': llm_name,
        }
        if history_messages:
            post_data['history_messages'] = history_messages
        resp = rag_requests(url, json=post_data, method='POST')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

    @staticmethod
    def update(conversation_id, agent_id, paper_ids=None, public_collection_ids=None, llm_name=None):
        url = RAG_HOST + '/api/v1/conversations/' + conversation_id
        post_data = {
            'agent_id': agent_id,
            'paper_ids': paper_ids,
            'public_collection_ids': public_collection_ids,
            'llm_name': llm_name,
        }
        resp = rag_requests(url, json=post_data, method='PUT')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

    @staticmethod
    def generate_conversation_title(question, answer):
        url = RAG_HOST + '/api/v1/titles/conversation'
        post_data = {
            'question': question,
            'answer': answer,
        }
        resp = rag_requests(url, json=post_data, method='POST', timeout=20)
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp.get('title')

    @staticmethod
    def generate_favorite_title(titles):
        titles = [title for title in titles if title]
        if not titles:
            logger.info(f'generate_favorite_title titles is empty')
            return f"未命名-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
        url = RAG_HOST + '/api/v1/titles/favorites'
        resp = rag_requests(url, json=titles, method='POST', timeout=20)
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp.get('title', f"未命名-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")

    @staticmethod
    def update_stream(stream, line_data):
        class EventTypes:
            TOOL_START = 'tool_start'
            TOOL_END = 'tool_end'
            MODEL_STATISTICS = 'model_statistics'
            ON_ERROR = 'on_error'
            MODEL_STREAM = 'model_stream'

        """更新stream字典"""
        event = line_data.get('event')
        if event == EventTypes.TOOL_START:
            stream[event]['name'] = line_data.get('name', '')
            stream['input'] = line_data.get('input', '')
        elif event == EventTypes.TOOL_END:
            stream[event]['name'] = line_data.get('name', '')
            stream['output'] = eval(line_data['output']) if line_data.get('output') else None
        elif event == EventTypes.MODEL_STATISTICS:
            stream[event]['name'] = line_data.get('name', '')
            stream['run_id'] = line_data.get('run_id', '')
            stream['statistics']['model_name'] = line_data.get('statistics', {}).get('model_name', '')
            stream['statistics']['input_tokens'] += line_data.get('statistics', {}).get('input_tokens', 0)
            stream['statistics']['output_tokens'] += line_data.get('statistics', {}).get('output_tokens', 0)
            stream['metadata'] = line_data.get('metadata', {})
        elif event == EventTypes.ON_ERROR:
            stream[event] = line_data.get('error', '')  # todo on_error 信息
        elif event == EventTypes.MODEL_STREAM:
            stream[event]['name'] = line_data.get('name', '')
            stream['chunk'].append(line_data.get('chunk', ''))  # Assuming 'chunk' is always a string here
        return stream

    @staticmethod
    def query_new(user_id, conversation_id, content,):
        url = RAG_HOST + '/api/v1/query/conversation'
        post_data = {
            'content': content,
            'conversation_id': conversation_id,
            'user_id': user_id,
            # 'streaming': streaming,
            # 'response_format': response_format
        }
        chat_timeout = settings.CHAT_TIMEOUT
        resp = rag_requests(url, json=post_data, method='POST', timeout=chat_timeout, stream=True)
        return resp


class Authors:

    @staticmethod
    def search_authors(name, limit=10):
        url = RAG_HOST + f'/api/v1/authors/search?name={name}&limit={limit}'
        resp = rag_requests(url, method='GET')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

    @staticmethod
    def get_author(author_id):
        url = RAG_HOST + f'/api/v1/authors/{author_id}'
        resp = rag_requests(url, method='GET')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp

    @staticmethod
    def get_author_papers(author_id):
        url = RAG_HOST + f'/api/v1/authors/{author_id}/papers'
        resp = rag_requests(url, method='GET')
        logger.info(f'url: {url}, response: {resp.text}')
        resp = resp.json()
        return resp
