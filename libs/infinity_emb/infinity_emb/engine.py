from dataclasses import asdict
from typing import Optional, Set

from infinity_emb.args import EngineArgs

# prometheus
from infinity_emb.inference import (
    BatchHandler,
    select_model,
)
from infinity_emb.log_handler import logger
from infinity_emb.primitives import (
    ClassifyReturnType,
    EmbeddingReturnType,
    ModelCapabilites,
)


class AsyncEmbeddingEngine:
    def __init__(
        self,
        model_name_or_path: Optional[str] = None,
        _show_deprecation_warning=True,
        **kwargs,
    ) -> None:
        """Creating a Async EmbeddingEngine object.
        preferred way to create an engine is via `from_args` method.
        """
        # TODO: remove _show_deprecation_warning and __init__ option.
        if _show_deprecation_warning:
            logger.warning(
                "AsyncEmbeddingEngine() is deprecated since 0.0.25. "
                "Use `AsyncEmbeddingEngine.from_args()` instead"
            )
        if model_name_or_path is not None:
            kwargs["model_name_or_path"] = model_name_or_path
        self.engine_args = EngineArgs(**kwargs)

        self.running = False
        self._model, self._min_inference_t, self._max_inference_t = select_model(
            self.engine_args
        )

    @classmethod
    def from_args(
        cls,
        engine_args: EngineArgs,
    ) -> "AsyncEmbeddingEngine":
        engine = cls(**asdict(engine_args), _show_deprecation_warning=False)

        return engine

    def __str__(self) -> str:
        return (
            f"AsyncEmbeddingEngine(running={self.running}, "
            f"inference_time={[self._min_inference_t, self._max_inference_t]}, "
            f"{self.engine_args})"
        )

    async def astart(self):
        """startup engine"""
        if self.running:
            raise ValueError(
                "DoubleSpawn: already started `AsyncEmbeddingEngine`. "
                " recommended use is via AsyncContextManager"
                " `async with engine: ..`"
            )
        self.running = True
        self._batch_handler = BatchHandler(
            max_batch_size=self.engine_args.batch_size,
            model=self._model,
            batch_delay=self._min_inference_t / 2,
            vector_disk_cache_path=self.engine_args.vector_disk_cache_path,
            verbose=logger.level <= 10,
            lengths_via_tokenize=self.engine_args.lengths_via_tokenize,
        )
        await self._batch_handler.spawn()

    async def astop(self):
        """stop engine"""
        self._check_running()
        self.running = False
        await self._batch_handler.shutdown()

    async def __aenter__(self):
        await self.astart()

    async def __aexit__(self, *args):
        await self.astop()

    def overload_status(self):
        self._check_running()
        return self._batch_handler.overload_status()

    def is_overloaded(self) -> bool:
        self._check_running()
        return self._batch_handler.is_overloaded()

    @property
    def capabilities(self) -> Set[ModelCapabilites]:
        return self._model.capabilities

    async def embed(
        self, sentences: list[str]
    ) -> tuple[list[EmbeddingReturnType], int]:
        """embed multiple sentences

        Args:
            sentences (list[str]): sentences to be embedded

        Raises:
            ValueError: raised if engine is not started yet
            ModelNotDeployedError: If loaded model does not expose `embed`
                capabilities

        Returns:
            list[EmbeddingReturnType]: embeddings
                2D list-array of shape( len(sentences),embed_dim )
            int: token usage
        """

        self._check_running()
        embeddings, usage = await self._batch_handler.embed(sentences)
        return embeddings, usage

    async def rerank(
        self, *, query: str, docs: list[str], raw_scores: bool = False
    ) -> tuple[list[float], int]:
        """rerank multiple sentences

        Args:
            query (str): query to be reranked
            docs (list[str]): docs to be reranked
            raw_scores (bool): return raw scores instead of sigmoid

        Raises:
            ValueError: raised if engine is not started yet
            ModelNotDeployedError: If loaded model does not expose `embed`
                capabilities

        Returns:
            list[float]: list of scores
            int: token usage
        """
        self._check_running()
        scores, usage = await self._batch_handler.rerank(
            query=query, docs=docs, raw_scores=raw_scores
        )

        return scores, usage

    async def classify(
        self, *, sentences: list[str], raw_scores: bool = False
    ) -> tuple[list[ClassifyReturnType], int]:
        """classify multiple sentences

        Args:
            sentences (list[str]): sentences to be classified
            raw_scores (bool): if True, return raw scores, else softmax

        Raises:
            ValueError: raised if engine is not started yet
            ModelNotDeployedError: If loaded model does not expose `embed`
                capabilities

        Returns:
            list[ClassifyReturnType]: list of class encodings
            int: token usage
        """
        self._check_running()
        scores, usage = await self._batch_handler.classify(sentences=sentences)

        return scores, usage

    def _check_running(self):
        if not self.running:
            raise ValueError(
                "didn't start `AsyncEmbeddingEngine` "
                " recommended use is via AsyncContextManager"
                " `async with engine: ..`"
            )
