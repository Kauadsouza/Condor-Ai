"""Behavior and security checks for the conversational desktop experience."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from condor.brain.ollama import chat_messages, responder_ollama
from condor.config import Config
from condor.memory.db import Memoria


class LocalStreamTests(unittest.IsolatedAsyncioTestCase):
    async def run_stream(self, events, tokens=None):
        captured = []
        def handler(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, text='\n'.join(json.dumps(event) for event in events))
        client_class = httpx.AsyncClient
        def client(**kwargs):
            return client_class(transport=httpx.MockTransport(handler), **kwargs)
        async def token(value):
            if tokens is not None:
                tokens.append(value)
        with patch('condor.brain.ollama.httpx.AsyncClient', side_effect=client):
            result = await responder_ollama(endpoint='http://127.0.0.1:11434/v1', model='test',
                instructions='identity', items=[{'role':'user','content':'hello'}], tools=[],
                max_tokens=80, context=8192, temperature=.5, on_token=token)
        return result, captured[0]

    async def test_tokens_are_streamed_and_context_is_bounded(self):
        tokens=[]
        result, request = await self.run_stream([
            {'message':{'content':'Oi '}}, {'message':{'content':'Kaua'}},
            {'done':True,'prompt_eval_count':20,'eval_count':2},
        ], tokens)
        self.assertEqual(tokens, ['Oi ', 'Kaua'])
        self.assertEqual(result.output_text, 'Oi Kaua')
        self.assertEqual(request['options']['num_ctx'],8192)
        self.assertTrue(request['stream'])
        self.assertEqual(result.usage.input_tokens,20)

    async def test_partial_stream_is_never_reported_as_complete(self):
        with self.assertRaisesRegex(RuntimeError,'interrompida'):
            await self.run_stream([{'message':{'content':'partial'}}])

    async def test_tool_calls_keep_arguments_and_result_order(self):
        result, _ = await self.run_stream([{'message':{'tool_calls':[{'function':{
            'name':'abrir','arguments':{'alvo':'https://example.com'}}}]},'done':True}])
        call=result.output[0].model_dump()
        messages=chat_messages('identity',[call, {'type':'function_call_output','call_id':call['call_id'],'output':'FALHOU: blocked'}])
        self.assertEqual(messages[-1],{'role':'tool','tool_name':'abrir','content':'FALHOU: blocked'})
        self.assertEqual(messages[-2]['tool_calls'][0]['function']['arguments'],{'alvo':'https://example.com'})

    async def test_remote_endpoint_is_rejected_before_network(self):
        with self.assertRaisesRegex(ValueError,'loopback'):
            await responder_ollama(endpoint='https://example.com',model='test',instructions='',
                items=[],tools=[],max_tokens=5,context=8192,temperature=.5)


class AssistantAPITests(unittest.TestCase):
    def test_voice_and_preferences_require_local_session_and_unlocked_owner(self):
        from fastapi.testclient import TestClient
        from condor.server import montar
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'CONDOR_HOME':directory}):
            app, session=montar(Config(escuta={'ativa':False}, visualizacao_movel={'ativa':False}))
            client=TestClient(app,base_url='http://127.0.0.1:7777')
            self.assertIn(client.post('/api/voice/synthesize',json={'texto':'hello'}).status_code,{401,403})
            token=(Path(directory)/'security'/'ui-token').read_text().strip()
            headers={'Origin':'http://127.0.0.1:7777','X-Condor-Client':'desktop-ui','X-Condor-Token':token}
            self.assertEqual(client.post('/api/session',headers=headers).status_code,200)
            client.headers['Origin']='http://127.0.0.1:7777'
            self.assertEqual(client.post('/api/voice/synthesize',json={'texto':'hello'}).status_code,423)
            self.assertEqual(client.post('/api/voice/transcribe?dispatch=false',content=b'audio').status_code,423)
            self.assertEqual(client.patch('/api/assistant/preferences',json={'keep_window_open':True}).status_code,423)
            self.assertEqual(client.post('/api/assistant/conversations').status_code,423)
            self.assertEqual(client.get('/api/conversa/arquivo').status_code,423)
            setup=client.post('/api/seguranca/configurar',json={'passphrase':'temporary-test-passphrase','owner':'Fixture'})
            self.assertEqual(setup.status_code,200,setup.text)
            snapshot=client.get('/api/assistant/status').json()
            self.assertTrue(snapshot['unlocked'])
            self.assertFalse(snapshot['iphone']['control'])
            self.assertNotIn('temporary-test-passphrase',json.dumps(snapshot))
            self.assertEqual(client.patch('/api/assistant/preferences',json={'keep_window_open':'false'}).status_code,400)
            self.assertEqual(client.patch('/api/assistant/preferences',json={'keep_window_open':True}).status_code,200)
            self.assertEqual(client.post('/api/voice/synthesize',json={'texto':''}).status_code,400)
            self.assertEqual(client.post('/api/voice/synthesize',json={'texto':'a'*8001}).status_code,400)
            self.assertEqual(client.post('/api/voice/synthesize',json={'texto':'test'}).status_code,503)
            with patch('condor.server.Conexoes.transmitir', new_callable=AsyncMock) as broadcast:
                self.assertEqual(client.post('/api/seguranca/bloquear',json={}).status_code,200)
                broadcast.assert_any_await({'tipo':'seguranca.bloqueado'})
            self.assertFalse(client.get('/api/assistant/status').json()['unlocked'])
            client.headers['Origin']='https://evil.example'
            self.assertEqual(client.get('/api/assistant/status').status_code,403)

    def test_new_conversation_preserves_old_messages_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            key=os.urandom(32); path=Path(directory)/'memory.enc'
            memory=Memoria(path);memory.inicializar();memory.unlock(key)
            memory.abrir_sessao();memory.salvar_turno('user','previous conversation')
            memory.arquivar_conversa()
            self.assertEqual(memory.historico(),[])
            self.assertEqual(len(memory.cloud_snapshot()['messages']),1)
            memory.salvar_turno('user','new conversation');memory.lock()
            reopened=Memoria(path);reopened.unlock(key)
            self.assertEqual(reopened.historico(),[{'role':'user','content':'new conversation'}])
            self.assertEqual(len(reopened.cloud_snapshot()['messages']),2)
            archive=reopened.arquivo_conversas(limite=1)
            self.assertEqual(archive[0]['conteudo'],'new conversation')
            self.assertEqual(reopened.arquivo_conversas(antes=archive[0]['id'])[0]['conteudo'],'previous conversation')
            reopened.lock()

if __name__=='__main__':
    unittest.main()
