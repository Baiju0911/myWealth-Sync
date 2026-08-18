import math
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

logger = logging.getLogger(__name__)


def run_in_parallel(payload_list, worker_func, extra_args=None, max_workers=4):
    """
    ⚡ GENERIC PARALLEL THREADPOOL UTILITY
    Slices payload_list across threads and returns aggregated batch outputs.
    """
    total_items = len(payload_list)
    if total_items == 0:
        return []

    if extra_args is None:
        extra_args = ()
    elif not isinstance(extra_args, tuple):
        extra_args = (extra_args,)

    # Slices total items dynamically across workers
    chunk_size = math.ceil(total_items / max_workers)
    chunks = [
        payload_list[i : i + chunk_size] for i in range(0, total_items, chunk_size)
    ]

    # Partial binding prevents lambda variable closure issues across threads
    worker_wrapper = partial(worker_func, extra_args=extra_args)

    aggregated_results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        try:
            # Pass extra_args unpack cleanly to worker function
            results = executor.map(
                lambda chunk: worker_func(chunk, *extra_args), chunks
            )

            for result in results:
                if result is not None:
                    aggregated_results.append(result)

        except Exception as e:
            logger.error(
                f"❌ Parallel execution failed inside mapper track: {str(e)}",
                exc_info=True,
            )
            raise e

    return aggregated_results
