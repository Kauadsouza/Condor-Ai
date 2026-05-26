# Runtime Nativo — Fase 2 (Experimental)

Este módulo é o placeholder para uma implementação futura de inferência nativa,
sem dependência de llama-cpp-python ou qualquer biblioteca de terceiros para o loop de inferência.

## Objetivo

Implementar o loop de inferência transformers do zero, usando:

- `numpy` + `numba` para operações de tensor (matmul, softmax, RoPE, etc.)
- Parser próprio de arquivos GGUF (especificação: https://github.com/ggerganov/ggml/blob/master/docs/gguf.md)
- `cupy` para kernels CUDA se GPU disponível
- Quantização Q4_K_M implementada manualmente

## Interface esperada

Qualquer implementação aqui deve satisfazer `condor.runtime.base.InferenceEngine`:

```python
class NativeEngine:
    async def generate(self, messages, system_prompt=None, **kwargs) -> AsyncIterator[str]: ...
    async def embed(self, text: str) -> list[float]: ...
    def get_health(self) -> EngineHealth: ...
```

## Por que não implementar agora?

Implementar inferência transformer completa do zero (incluindo attention, KV cache,
RoPE embeddings, quantização) é um projeto de meses. A Fase 1 com llama-cpp-python
já resolve o problema com performance excelente.

Este módulo existe para documentar o caminho e manter a arquitetura aberta.

## Referências

- Especificação GGUF: https://github.com/ggerganov/ggml/blob/master/docs/gguf.md
- llama.cpp (referência de implementação): https://github.com/ggerganov/llama.cpp
- Implementação educacional: https://github.com/karpathy/llama2.c
